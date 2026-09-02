"""
数据源多级fallback模块
yfinance → 新浪美股 → 东方财富 → 新浪期货 → 腾讯外汇 → CBOE → FRED → 代理因子 八层降级，逐ticker独立处理
（解决中国IP被Yahoo限流问题：美股ETF/个股走新浪日K，VIX走FRED；
 COMEX金/铜走新浪期货（真期货价，不再依赖ETF代理）；
 外汇/美元指数走腾讯（真DXY、T+0；FRED外汇序列发布滞后约一周且DTWEXBGS≠ICE DXY）；
 波动率指数走CBOE官方CSV（T+0，VIX9D唯一来源）；
 yfinance连续限流2次后熔断跳过；东财限流敏感需节流）
"""
import io
import json
import time
import csv
import zipfile
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path

try:
    from gold_model.paths import COT_CACHE_DIR
except ImportError:  # 单独调试本模块时兜底
    COT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / 'data' / 'cot_cache'


def _period_years(period='5y'):
    """从period字符串(如'5y'/'10y')解析年数，异常时回退5"""
    digits = ''.join(c for c in (period or '') if c.isdigit())
    return int(digits) if digits else 5

try:
    from curl_cffi import requests as _curl_requests  # 东财按TLS指纹封Python请求，需Chrome指纹
except ImportError:
    _curl_requests = None

# ── ticker到名称的映射（与V4脚本TICKERS一致）──
TICKER_NAMES = {
    'GC=F':    '黄金期货',
    'GLD':     'GLD基金',
    'IAU':     'IAU基金',
    'SGOL':    'SGOL基金',
    'DX-Y.NYB':'美元指数',
    'TIP':     'TIPS(实际利率替代)',
    'IEF':     '7-10年国债(名义利率替代)',
    'TLT':     '20+年国债',
    'SLV':     '白银',
    'GDX':     '金矿股',
    'GDXJ':    '金矿小盘',
    'SIL':     '白银矿企',
    '^VIX':    'VIX恐慌',
    '^GVZ':    '黄金VIX',
    'NEM':     '纽蒙特矿业',
    'EUR=X':   '欧元/美元',
    'JPY=X':   '美元/日元',
    'UUP':     '美元指数ETF',
    'HG=F':    '铜期货',
    'BTC-USD': '比特币',
    '^VIX9D':  'VIX9D',
    '^IRX':    '13周国债',
    '^FVX':    '5年国债',
    '^TNX':    '10年国债名义',
    '^TYX':    '30年国债',
}

# ── FRED替代映射（yfinance ticker → FRED series ID）──
FRED_ALTERNATIVES = {
    '^TNX':    'DGS10',    # 10年国债收益率
    '^TYX':    'DGS30',    # 30年国债收益率
    '^IRX':    'DGS3MO',   # 13周国债→3个月国债
    '^FVX':    'DGS5',     # 5年国债
    '^VIX':    'VIXCLS',   # VIX恐慌指数
    '^GVZ':    'GVZCLS',   # 黄金VIX
    'DX-Y.NYB':'DTWEXBGS', # 美元指数→贸易加权美元
    'EUR=X':   'DEXUSEU',  # 欧元/美元
    'JPY=X':   'DEXJPUS',  # 美元/日元（FRED是反向标价）
    'BTC-USD': 'CBBTCUSD', # 比特币
}

# ── 腾讯外汇映射（wh=外汇；T+0当日数据，1400条≈5.5年，无key无明显限流）──
# 腾讯美股K线接口实测只返回最近1日数据，不可用；外汇接口正常
TENCENT_FOREX = {
    'DX-Y.NYB': 'whDINIW',   # 美元指数（真·ICE DXY，优于FRED的DTWEXBGS贸易加权指数）
    'EUR=X':    'whEURUSD',  # 欧元/美元（与Yahoo EUR=X同向：1欧元兑多少美元）
    'JPY=X':    'whUSDJPY',  # 美元/日元（与Yahoo JPY=X同向：1美元兑多少日元）
}

# ── CBOE官方指数CSV（T+0当日收盘，VIX9D唯一可用源；新浪不覆盖指数、FRED的VIXCLS/GVZCLS滞后1天）──
CBOE_INDICES = {
    '^VIX':   'VIX',
    '^VIX9D': 'VIX9D',
    '^GVZ':   'GVZ',
}

# ── 新浪全球期货（COMEX金/铜真期货价，T+0，10年历史；Yahoo长期不可用时金价/铜价的首选源）──
# 映射: ticker → (新浪symbol, 单位缩放)。GC报USD/盎司与Yahoo同单位；HG新浪报美分/磅需×0.01
SINA_FUTURES = {
    'GC=F': ('GC', 1.0),    # 纽约金期货（替代 GLD×10.75 代理，消除ETF费率拖累）
    'HG=F': ('HG', 0.01),   # 纽约铜期货（替代 CPER×1.0 代理，真实期货价位）
}

# ── 东财替代（美股ETF/个股；secid market：107=Arca 105=Nasdaq 106=NYSE）──
# 东财限流敏感：已知market直接给出减少请求数，未知才探测；调用间强制节流
EASTMONEY_MARKET_HINT = {
    'GLD': 107, 'IAU': 107, 'SGOL': 107, 'TIP': 107, 'SLV': 107,
    'GDX': 107, 'GDXJ': 107, 'SIL': 107, 'UUP': 107, 'CPER': 107,
    'IEF': 105, 'TLT': 105,
    'NEM': 106,
}
_EM_MIN_INTERVAL = 1.5   # 两次东财请求最小间隔（秒）
_EM_MAX_RETRY = 3        # 被断连/限流时重试次数
_em_last_call = [0.0]

# yfinance限流熔断：连续2次YFRateLimitError后跳过后续yfinance尝试（省2-3分钟无效重试）
_yf_rate_limit_streak = [0]
_yf_last_fail_time = [0.0]
_YF_CIRCUIT_THRESHOLD = 2
_YF_CIRCUIT_RESET_SECONDS = 300  # 熔断5分钟后自动复位重试(限流常为短暂性)


def _em_get(url, headers):
    """带节流+退避重试的东财请求"""
    for attempt in range(_EM_MAX_RETRY):
        wait = _EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
        if wait > 0:
            time.sleep(wait)
        _em_last_call[0] = time.time()
        try:
            r = _curl_requests.get(url, headers=headers, timeout=15, impersonate='chrome')
            if r.status_code == 200 and r.text:
                return r
        except Exception:
            pass
        time.sleep(4 * (attempt + 1))  # 退避：4s/8s
    return None


def _fetch_from_eastmoney(ticker, period='5y'):
    """东方财富K线API：美股ETF/个股日线（前复权），自动探测market前缀"""
    if _curl_requests is None:
        return None
    headers = {
        'Referer': 'https://quote.eastmoney.com/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    }
    end = datetime.now().strftime('%Y%m%d')
    beg = (datetime.now() - timedelta(days=int(period.replace('y', '')) * 365 + 30)).strftime('%Y%m%d') \
        if period.endswith('y') else (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
    hint = EASTMONEY_MARKET_HINT.get(ticker)
    markets = ([hint] + [m for m in (107, 105, 106) if m != hint]) if hint else (107, 105, 106)
    for mkt in markets:
        url = (f'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={mkt}.{ticker}'
               f'&fields1=f1,f2,f3&fields2=f51,f53&klt=101&fqt=1&beg={beg}&end={end}')
        r = _em_get(url, headers)
        if r is None:
            continue
        data = r.json().get('data')
        if not data or not data.get('klines'):
            continue
        rows = [k.split(',') for k in data['klines']]
        s = pd.Series(
            [float(x[1]) for x in rows],
            index=pd.to_datetime([x[0] for x in rows]),
            name=ticker,
        )
        if len(s) > 100:
            return s
    return None


def _fetch_from_sina(ticker, period='5y'):
    """新浪财经美股日K（全历史OHLC），对中国IP友好"""
    url = (f'https://stock.finance.sina.com.cn/usstock/api/jsonp_v2.php/'
           f'var%20_x=/US_MinKService.getDailyK?symbol={ticker.lower()}')
    try:
        r = requests.get(url, headers={'Referer': 'https://finance.sina.com.cn/'}, timeout=15)
        text = r.text
        start = text.find('([')
        if start < 0:
            return None
        data = json.loads(text[start + 1:text.rfind(')')])
        if len(data) < 100:
            return None
        s = pd.Series(
            [float(x['c']) for x in data],
            index=pd.to_datetime([x['d'] for x in data]),
            name=ticker,
        )
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=_period_years(period) * 365)
        s = s[s.index > cutoff]
        return s if len(s) > 100 else None
    except Exception:
        return None

# ── 代理因子fallback（yfinance ticker失败时用其他yfinance ticker替代）──
# Stooq全站JS验证无法直接抓取，改用ETF/相关品种作为代理
PROXY_FALLBACK = {
    'GC=F':    ('GLD', 10.75),    # 黄金期货 → GLD ETF（最终兜底；正常走新浪期货真价）
    'HG=F':    ('CPER', 1.0),     # 铜期货 → 铜ETF（最终兜底；正常走新浪期货真价）
    '^GVZ':    ('^VIX', 0.5),     # 黄金VIX → VIX（相关性高，波动幅度调小）
    # 注意：^VIX9D 不可用 ^VIX 代理——下游"VIX期限结构"=VIX/VIX9D 会变成常数（零方差死特征）；
    # 该品种已由 CBOE 官方 CSV 覆盖，无需代理
}


def _safe_yf_download(ticker, period='5y'):
    """yfinance下载，处理MultiIndex列"""
    d = yf.download(ticker, period=period, progress=False, auto_adjust=False)
    if len(d) == 0:
        return None
    if isinstance(d.columns, pd.MultiIndex):
        col = 'Adj Close' if ('Adj Close', ticker) in d.columns else 'Close'
        s = d[col][ticker] if ticker in d[col] else d[col].iloc[:, 0]
    else:
        s = d['Adj Close'] if 'Adj Close' in d.columns else d['Close']
    return s


def _fetch_from_fred(series_id, period='5y', retries=2):
    """从FRED抓取CSV数据（带重试，偶发read timeout）"""
    r = None
    for attempt in range(retries + 1):
        try:
            url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'
            r = requests.get(url, timeout=30)
            break
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))
    if r.status_code != 200 or 'html' in r.text[:50].lower():
        return None
    df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
    df = df.replace('.', np.nan).astype(float)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=_period_years(period) * 365)
    df = df[df.index > cutoff]
    if len(df) < 50:
        return None
    s = df.iloc[:, 0]
    return s


def _fetch_from_tencent_forex(ticker, period='5y'):
    """腾讯外汇日K（proxy.finance.qq.com，需浏览器UA）：行格式 [date, open, close, high, low, vol]"""
    symbol = TENCENT_FOREX.get(ticker)
    if not symbol:
        return None
    try:
        url = ('https://proxy.finance.qq.com/ifzqgtimg/appstock/app/fqkline/get'
               f'?param={symbol},day,,,1400,qfq')
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        d = r.json().get('data', {}).get(symbol, {})
        klines = d.get('qfqday') or d.get('day') or []
        rows = [(k[0], float(k[2])) for k in klines if len(k) >= 3]
        if len(rows) < 100:
            return None
        s = pd.Series(dict(rows), name=ticker)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        if period == '5y':
            s = s[s.index > pd.Timestamp.now() - pd.Timedelta(days=5 * 365)]
        return s if len(s) > 100 else None
    except Exception:
        return None


def _fetch_from_cboe(ticker, period='5y'):
    """CBOE官方历史CSV：Date,Open,High,Low,Close（GVZ仅Close），T+0"""
    symbol = CBOE_INDICES.get(ticker)
    if not symbol:
        return None
    try:
        url = f'https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv'
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = [c.strip().lower() for c in df.columns]
        df['date'] = pd.to_datetime(df['date'], format='%m/%d/%Y')
        value_col = 'close' if 'close' in df.columns else df.columns[1]  # GVZ等只有 DATE,<SYMBOL> 两列
        s = pd.Series(df[value_col].astype(float).values, index=df['date'], name=ticker)
        s = s.sort_index()
        if period == '5y':
            s = s[s.index > pd.Timestamp.now() - pd.Timedelta(days=5 * 365)]
        return s if len(s) > 100 else None
    except Exception:
        return None


def _fetch_from_sina_futures(ticker, period='5y'):
    """新浪全球期货日K：返回 [{'date','open','high','low','close',...}]，T+0"""
    m = SINA_FUTURES.get(ticker)
    if not m:
        return None
    symbol, scale = m
    try:
        url = ('https://stock2.finance.sina.com.cn/futures/api/jsonp_v2.php/'
               f'var=/GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={symbol}')
        r = requests.get(url, timeout=15, headers={'Referer': 'https://finance.sina.com.cn/'})
        t = r.text
        j = json.loads(t[t.index('(') + 1:t.rindex(')')])
        if not j:
            return None
        s = pd.Series({pd.Timestamp(k['date']): float(k['close']) * scale for k in j}, name=ticker)
        s = s.sort_index()
        if period == '5y':
            s = s[s.index > pd.Timestamp.now() - pd.Timedelta(days=5 * 365)]
        return s if len(s) > 100 else None
    except Exception:
        return None


def fetch_ticker_with_fallback(ticker, name, period='5y', verbose=True):
    """
    逐层fallback获取ticker数据
    返回: pd.Series 或 None
    """
    # 熔断超时复位：距离上次失败超过阈值秒数则重置计数，避免长时间运行中永久跳过yfinance
    if (_yf_rate_limit_streak[0] >= _YF_CIRCUIT_THRESHOLD
            and time.time() - _yf_last_fail_time[0] > _YF_CIRCUIT_RESET_SECONDS):
        _yf_rate_limit_streak[0] = 0

    # Level 1: yfinance主源（限流熔断时跳过）
    if _yf_rate_limit_streak[0] < _YF_CIRCUIT_THRESHOLD:
        try:
            s = _safe_yf_download(ticker, period)
            if s is not None and len(s) > 100:
                _yf_rate_limit_streak[0] = 0
                if verbose:
                    print(f"  ✅ {name}({ticker}) {len(s)}行 [yfinance]")
                s.name = name
                return s
            _yf_rate_limit_streak[0] += 1  # 空数据同样计入熔断（Yahoo软拦截常返回空DF）
            _yf_last_fail_time[0] = time.time()
            if _yf_rate_limit_streak[0] == _YF_CIRCUIT_THRESHOLD and verbose:
                print(f"  ⏩ yfinance连续失败（空数据），后续ticker直接走备用源")
        except Exception as e:
            _yf_rate_limit_streak[0] += 1  # 任何异常都计入熔断（DNS失败/429对全ticker同效）
            _yf_last_fail_time[0] = time.time()
            if _yf_rate_limit_streak[0] == _YF_CIRCUIT_THRESHOLD and verbose:
                print(f"  ⏩ yfinance连续失败（{type(e).__name__}），后续ticker直接走备用源")
            if verbose:
                print(f"  ⚠️ {name}({ticker}) yfinance失败: {type(e).__name__}")
    
    # Level 2: 新浪美股日K（美股ETF/个股；中国IP被Yahoo限流时的主力备份）
    if not ticker.startswith('^') and '=' not in ticker:
        s = _fetch_from_sina(ticker, period)
        if s is not None:
            if verbose:
                print(f"  🔄 {name}({ticker}) {len(s)}行 [新浪]")
            s.name = name
            return s

    # Level 3: 东财替代（美股ETF/个股，限流敏感需节流）
    if not ticker.startswith('^') and '=' not in ticker:
        try:
            s = _fetch_from_eastmoney(ticker, period)
            if s is not None:
                if verbose:
                    print(f"  🔄 {name}({ticker}) {len(s)}行 [东财]")
                s.name = name
                return s
        except Exception as e:
            if verbose:
                print(f"  ⚠️ {name}({ticker}) 东财失败: {e}")

    # Level 4: 新浪全球期货（COMEX金/铜真期货价，优先于代理因子）
    if ticker in SINA_FUTURES:
        s = _fetch_from_sina_futures(ticker, period)
        if s is not None:
            if verbose:
                sym, _ = SINA_FUTURES[ticker]
                print(f"  🔄 {name}({ticker}) {len(s)}行 [新浪期货:{sym}]")
            s.name = name
            return s

    # Level 5: 腾讯外汇（美元指数/EUR/JPY；T+0且是真DXY，优先于FRED外汇）
    if ticker in TENCENT_FOREX:
        s = _fetch_from_tencent_forex(ticker, period)
        if s is not None:
            if verbose:
                print(f"  🔄 {name}({ticker}) {len(s)}行 [腾讯:{TENCENT_FOREX[ticker]}]")
            s.name = name
            return s

    # Level 6: CBOE官方（VIX/VIX9D/GVZ，T+0，优先于FRED滞后1天的替代列）
    if ticker in CBOE_INDICES:
        s = _fetch_from_cboe(ticker, period)
        if s is not None:
            if verbose:
                print(f"  🔄 {name}({ticker}) {len(s)}行 [CBOE:{CBOE_INDICES[ticker]}]")
            s.name = name
            return s

    # Level 7: FRED替代
    if ticker in FRED_ALTERNATIVES:
        fred_id = FRED_ALTERNATIVES[ticker]
        try:
            s = _fetch_from_fred(fred_id, period)
            if s is not None and len(s) > 50:
                if verbose:
                    print(f"  🔄 {name}({ticker}) {len(s)}行 [FRED:{fred_id}]")
                s.name = name
                return s
        except Exception as e:
            if verbose:
                print(f"  ⚠️ {name}({ticker}) FRED({fred_id})失败: {e}")
    
    # Level 8: 代理因子fallback（用相关ETF/品种替代；GC=F/HG=F已有新浪期货真价，此处仅兜底）
    if ticker in PROXY_FALLBACK:
        proxy_ticker, scale = PROXY_FALLBACK[ticker]
        try:
            s = _safe_yf_download(proxy_ticker, period) \
                if _yf_rate_limit_streak[0] < _YF_CIRCUIT_THRESHOLD else None
            if s is None:
                s = _fetch_from_sina(proxy_ticker, period)
            if s is None:
                s = _fetch_from_eastmoney(proxy_ticker, period)
            if s is None and proxy_ticker in FRED_ALTERNATIVES:
                s = _fetch_from_fred(FRED_ALTERNATIVES[proxy_ticker], period)
            if s is not None and len(s) > 100:
                s = s * scale  # 按比例缩放
                if verbose:
                    print(f"  🔄 {name}({ticker}) {len(s)}行 [代理:{proxy_ticker}×{scale}]")
                s.name = name
                return s
        except Exception as e:
            if verbose:
                print(f"  ⚠️ {name}({ticker}) 代理({proxy_ticker})失败: {e}")
    
    if verbose:
        print(f"  ❌ {name}({ticker}) 所有数据源失败")
    return None


def fetch_cot_net_positions(period='10y', verbose=True):
    """
    CFTC持仓报告(COT)：COMEX黄金(GOLD - COMMODITY EXCHANGE INC., 合约码088691)
    非商业净多头持仓序列——市场投机仓位拥挤度（经典黄金情绪/反转指标）。

    数据源: www.cftc.gov年度压缩包 deacot{YEAR}.zip（publicreporting.cftc.gov Socrata API
    对部分地区403，主站文件可直连）。按年缓存到 data/cot_cache/，当年文件每6天刷新。

    因果性: 报告"as of"周二收盘仓位，周五约15:30 ET发布 → 发布日期=as_of+3个交易日，
    用发布日期做索引避免前视（周二当日仓位在周三/周四模型上还不可见）。

    返回: pd.Series(索引=发布日, 值=非商业净多头手数)，失败返回None
    """
    this_year = datetime.now().year
    years = list(range(this_year - _period_years(period) + 1, this_year + 1))
    rows = []  # (as_of_date, net_long)
    for y in years:
        cache_file = COT_CACHE_DIR / f'deacot{y}.txt'
        need_refresh = (not cache_file.exists()) or (
            y == this_year
            and time.time() - cache_file.stat().st_mtime > 6 * 86400)
        if need_refresh:
            try:
                url = f'https://www.cftc.gov/files/dea/history/deacot{y}.zip'
                r = requests.get(url, timeout=60,
                                 headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code != 200 or len(r.content) < 10000:
                    if verbose:
                        print(f"  ⚠️ COT({y}) 下载失败: HTTP {r.status_code}")
                    continue
                zf = zipfile.ZipFile(io.BytesIO(r.content))
                text = zf.read(zf.namelist()[0]).decode('latin-1')
                COT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(text, encoding='latin-1')
            except Exception as e:
                if verbose:
                    print(f"  ⚠️ COT({y}) 下载异常: {type(e).__name__}")
                continue
        try:
            with open(cache_file, encoding='latin-1') as f:
                for row in csv.DictReader(f):
                    if (row.get('CFTC Contract Market Code', '').strip() == '088691'):
                        try:
                            as_of = pd.Timestamp(row['As of Date in Form YYYY-MM-DD'])
                            longs = float(row['Noncommercial Positions-Long (All)'])
                            shorts = float(row['Noncommercial Positions-Short (All)'])
                            rows.append((as_of, longs - shorts))
                        except (KeyError, ValueError, TypeError):
                            continue
        except Exception as e:
            if verbose:
                print(f"  ⚠️ COT({y}) 缓存解析失败: {type(e).__name__}")
    if len(rows) < 60:
        if verbose:
            print(f"  ❌ COT非商业净多头: 有效数据不足({len(rows)}条)")
        return None
    s = (pd.Series(dict(rows)).sort_index())
    # 因果对齐: as_of(周二) → 发布(周五)=+3交易日
    s.index = s.index + pd.tseries.offsets.BDay(3)
    s = s[~s.index.duplicated(keep='last')]
    if verbose:
        print(f"  ✅ COT非商业净多头 {len(s)}周 ({s.index[0].date()}~{s.index[-1].date()}) [CFTC]")
    return s


def fetch_all_tickers(tickers_dict, period='5y'):
    """
    批量获取所有ticker，逐ticker独立fallback
    参数:
        tickers_dict: {ticker: name} 映射
        period: 数据周期
    返回:
        {name: pd.Series} 字典（只包含成功的ticker）
    """
    raw = {}
    success = 0
    failed = 0
    
    for ticker, name in tickers_dict.items():
        s = fetch_ticker_with_fallback(ticker, name, period)
        if s is not None:
            raw[name] = s
            success += 1
        else:
            failed += 1
    
    print(f"\n  数据采集汇总: 成功{success}/失败{failed}")
    return raw


if __name__ == '__main__':
    # 测试fallback
    print("测试逐层fallback...")
    
    # 正常情况
    print("\n--- GC=F (黄金期货, yfinance主源) ---")
    s = fetch_ticker_with_fallback('GC=F', '黄金期货')
    if s is not None:
        print(f"  最新值: {s.iloc[-1]:.2f} ({s.index[-1].strftime('%Y-%m-%d')})")
    
    # 测试Stooq fallback（模拟yfinance失败）
    print("\n--- HG=F (铜期货, 模拟yfinance失败) ---")
    import data_fetcher
    data_fetcher._safe_yf_download = lambda *a, **k: None  # 模拟失败
    s = fetch_ticker_with_fallback('HG=F', '铜期货')
    if s is not None:
        print(f"  最新值: {s.iloc[-1]:.2f} ({s.index[-1].strftime('%Y-%m-%d')})")
