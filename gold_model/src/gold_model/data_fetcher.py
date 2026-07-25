"""
数据源多级fallback模块
yfinance → FRED → Stooq 三层降级，逐ticker独立处理
"""
import io
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta

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
    'DX-Y.NYB':'DTWEXBGS', # 美元指数→贸易加权美元
    'EUR=X':   'DEXUSEU',  # 欧元/美元
    'JPY=X':   'DEXJPUS',  # 美元/日元（FRED是反向标价）
    'BTC-USD': 'CBBTCUSD', # 比特币
}

# ── 代理因子fallback（yfinance ticker失败时用其他yfinance ticker替代）──
# Stooq全站JS验证无法直接抓取，改用ETF/相关品种作为代理
PROXY_FALLBACK = {
    'GC=F':    ('GLD', 0.1),      # 黄金期货 → GLD ETF（价格≈1/10期货）
    'HG=F':    ('CPER', 1.0),     # 铜期货 → 铜ETF（方向一致）
    '^GVZ':    ('^VIX', 0.5),     # 黄金VIX → VIX（相关性高，波动幅度调小）
    '^VIX9D':  ('^VIX', 0.9),     # VIX9D → VIX（高度相关）
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


def _fetch_from_fred(series_id, period='5y'):
    """从FRED抓取CSV数据"""
    url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'
    r = requests.get(url, timeout=15)
    if r.status_code != 200 or 'html' in r.text[:50].lower():
        return None
    df = pd.read_csv(io.StringIO(r.text), index_col=0, parse_dates=True)
    df = df.replace('.', np.nan).astype(float)
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=5 * 365)
    df = df[df.index > cutoff]
    if len(df) < 50:
        return None
    s = df.iloc[:, 0]
    return s


def fetch_ticker_with_fallback(ticker, name, period='5y', verbose=True):
    """
    逐层fallback获取ticker数据
    返回: pd.Series 或 None
    """
    # Level 1: yfinance主源
    try:
        s = _safe_yf_download(ticker, period)
        if s is not None and len(s) > 100:
            if verbose:
                print(f"  ✅ {name}({ticker}) {len(s)}行 [yfinance]")
            s.name = name
            return s
    except Exception as e:
        if verbose:
            print(f"  ⚠️ {name}({ticker}) yfinance失败: {e}")
    
    # Level 2: FRED替代
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
    
    # Level 3: 代理因子fallback（用相关ETF/品种替代）
    if ticker in PROXY_FALLBACK:
        proxy_ticker, scale = PROXY_FALLBACK[ticker]
        try:
            s = _safe_yf_download(proxy_ticker, period)
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
