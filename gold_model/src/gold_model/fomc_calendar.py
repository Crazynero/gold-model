"""
FOMC日历动态获取模块
多级fallback：Fed官网抓取 → 本地缓存 → 硬编码历史 → 模式估算
"""
import json
import os
import re
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

from gold_model.paths import FOMC_CACHE

CACHE_FILE = str(FOMC_CACHE)

# ── 硬编码历史日期（已验证，作为baseline和fallback）──
# 使用announcement date（2天会议的第2天，即公布利率决议的日子）
# 注(D2修复): 2020-03-15/03-23 为疫情紧急会议,非预先排期的例行会议——若纳入会污染
#   "距下次FOMC天数/FOMC周"这类前视特征(会议当天之前无人知道)。故此处只保留例行会议。
HISTORICAL_FOMC = {
    2020: ['2020-01-29', '2020-04-29', '2020-06-10', '2020-07-29',
           '2020-09-16', '2020-11-05', '2020-12-16'],
    2021: ['2021-01-27', '2021-03-17', '2021-04-28', '2021-06-16',
           '2021-07-28', '2021-09-22', '2021-11-03', '2021-12-15'],
    2022: ['2022-01-26', '2022-03-16', '2022-05-04', '2022-06-15',
           '2022-07-27', '2022-09-21', '2022-11-02', '2022-12-14'],
    2023: ['2023-02-01', '2023-03-22', '2023-05-03', '2023-06-14',
           '2023-07-26', '2023-09-20', '2023-11-01', '2023-12-13'],
    2024: ['2024-01-31', '2024-03-20', '2024-05-01', '2024-06-12',
           '2024-07-31', '2024-09-18', '2024-11-07', '2024-12-18'],
    2025: ['2025-01-29', '2025-03-19', '2025-04-30', '2025-06-18',
           '2025-07-30', '2025-09-17', '2025-10-29', '2025-12-10'],
}

# FOMC模式估算：8次/年，各会议的大致月份和日期中位数（基于2020-2025历史）
FOMC_PATTERN = [
    (1, 28),   # 1月下旬
    (3, 17),   # 3月中旬
    (4, 29),   # 4月下旬/5月初
    (6, 15),   # 6月中旬
    (7, 28),   # 7月下旬
    (9, 18),   # 9月中旬
    (10, 29),  # 10月下旬/11月初
    (12, 11),  # 12月中旬
]

MONTHS_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5,
    'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def parse_meeting_date(month_str, date_str, year):
    """
    解析FOMC会议日期，返回announcement date（第2天）
    
    格式示例:
      month='January', date='27-28' → (year, 1, 28)
      month='Jan/Feb', date='31-1' → (year, 2, 1)  跨月
      month='Apr/May', date='30-1' → (year, 5, 1)  跨月
      month='August', date='22 (notation vote)' → None  非正式会议
    """
    # 排除notation vote等非正式会议
    if 'notation' in date_str.lower() or 'notation' in month_str.lower():
        return None
    
    # 解析月份
    if '/' in month_str:
        # 跨月，如 "Jan/Feb" 或 "Apr/May"
        parts = month_str.split('/')
        month1 = MONTHS_MAP.get(parts[0].strip().lower())
        month2 = MONTHS_MAP.get(parts[1].strip().lower())
    else:
        month1 = MONTHS_MAP.get(month_str.strip().lower())
        month2 = month1
    
    if not month1:
        return None
    
    # 解析日期 "27-28" → day1=27, day2=28
    date_clean = re.sub(r'\*.*', '', date_str).strip()  # 去掉*号和后续文字
    date_parts = date_clean.split('-')
    
    try:
        day1 = int(date_parts[0].strip())
        day2 = int(date_parts[1].strip()) if len(date_parts) > 1 else day1
    except (ValueError, IndexError):
        return None
    
    # announcement date = 第2天
    # 判断第2天在哪个月：如果day2 < day1，说明跨月了，第2天在month2
    if day2 < day1 and month2:
        announcement_month = month2
    else:
        announcement_month = month1
    
    try:
        return pd.Timestamp(year=year, month=announcement_month, day=day2)
    except ValueError:
        return None


def fetch_fomc_from_web():
    """从Fed官网抓取FOMC会议日期"""
    url = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        if resp.status_code != 200:
            print(f"  [FOMC] HTTP {resp.status_code}, 使用fallback")
            return {}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        result = {}  # {year: [timestamp, ...]}
        
        # 查找所有年份标题
        for h4 in soup.find_all('h4'):
            text = h4.get_text(strip=True)
            match = re.match(r'(\d{4})\s+FOMC\s+Meetings', text, re.I)
            if not match:
                continue
            year = int(match.group(1))
            
            # 找该年份下的所有会议行
            # 年份标题后通常跟着一个panel，里面有fomc-meeting rows
            panel = h4.find_parent('div', class_='panel') or h4.find_parent('div')
            if not panel:
                continue
            
            meetings = panel.find_all('div', class_='fomc-meeting')
            dates = []
            for m in meetings:
                month_div = m.find('div', class_='fomc-meeting__month')
                date_div = m.find('div', class_='fomc-meeting__date')
                if not month_div or not date_div:
                    continue
                month_str = month_div.get_text(strip=True)
                date_str = date_div.get_text(strip=True)
                ts = parse_meeting_date(month_str, date_str, year)
                if ts:
                    dates.append(ts)
            
            if dates:
                result[year] = sorted(dates)
        
        total = sum(len(v) for v in result.values())
        print(f"  [FOMC] Fed官网抓取成功: {len(result)}年 {total}个会议日期")
        return result
        
    except Exception as e:
        print(f"  [FOMC] 抓取失败: {e}, 使用fallback")
        return {}


def estimate_future_fomc(start_year, end_year):
    """
    基于历史模式估算未来FOMC日期
    FOMC每年8次会议，announcement date通常在周三
    """
    estimated = []
    for year in range(start_year, end_year + 1):
        for month, approx_day in FOMC_PATTERN:
            # 找该月最接近approx_day的周三
            for day in range(approx_day - 5, approx_day + 5):
                try:
                    d = pd.Timestamp(year=year, month=month, day=day)
                    if d.weekday() == 2:  # 周三
                        estimated.append(d)
                        break
                except ValueError:
                    continue
    return estimated


def save_cache(dates, source='web'):
    """保存到本地缓存"""
    try:
        data = {
            'dates': [d.strftime('%Y-%m-%d') for d in dates],
            'updated': datetime.now().isoformat(),
            'source': source,
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"  [FOMC] 缓存保存失败: {e}")


def load_cache():
    """从本地缓存加载"""
    try:
        if not os.path.exists(CACHE_FILE):
            return None
        with open(CACHE_FILE) as f:
            data = json.load(f)
        dates = [pd.Timestamp(d) for d in data['dates']]
        print(f"  [FOMC] 缓存加载: {len(dates)}个日期 (更新于{data.get('updated', 'unknown')[:10]})")
        return dates
    except Exception:
        return None


def get_fomc_dates(end_year=None):
    """
    获取FOMC announcement dates，多级fallback:
    1. Fed官网抓取（覆盖抓取时点的前后1-2年）
    2. 硬编码历史（2020-2025，已验证）
    3. 本地缓存
    4. 模式估算（未来年份）
    
    参数:
        end_year: 需要覆盖到哪一年（默认当前年+2）
    返回:
        pd.DatetimeIndex，排序后的FOMC日期
    """
    if end_year is None:
        end_year = datetime.now().year + 2
    
    print("[FOMC] 获取FOMC日历...")
    
    # Level 1: 尝试从Fed官网抓取
    fetched = fetch_fomc_from_web()
    
    # Level 2: 合并硬编码历史 + 抓取结果
    all_dates = set()
    
    # 添加硬编码历史
    for year, dates in HISTORICAL_FOMC.items():
        for d in dates:
            all_dates.add(pd.Timestamp(d))
    
    # 添加抓取结果（优先级高于硬编码，覆盖同一年的日期）
    if fetched:
        for year, dates in fetched.items():
            for d in dates:
                all_dates.add(d)
    
    # Level 4: 如果抓取失败，添加未来年份估算
    current_year = datetime.now().year
    if not fetched:
        print("  [FOMC] 抓取失败，使用缓存+模式估算")
        # 加载缓存
        cached = load_cache()
        cached_years = set()
        if cached:
            for d in cached:
                all_dates.add(d)
                cached_years.add(d.year)
        # 只对缓存未覆盖的年份做估算
        estimate_start = current_year
        for y in range(estimate_start, end_year + 1):
            if y not in cached_years:
                estimated = estimate_future_fomc(y, y)
                for d in estimated:
                    all_dates.add(d)
                print(f"  [FOMC] {y}年估算: {len(estimated)}个日期")
    else:
        # 即使抓取成功，也检查是否有未来年份的缺口
        # Fed官网通常只列到下一年，如果需要更远则估算
        fetched_years = set(fetched.keys())
        if end_year > max(fetched_years):
            for y in range(max(fetched_years) + 1, end_year + 1):
                estimated = estimate_future_fomc(y, y)
                for d in estimated:
                    all_dates.add(d)
                print(f"  [FOMC] {y}年估算: {len(estimated)}个日期")
    
    # 转为排序的DatetimeIndex
    result = pd.DatetimeIndex(sorted(all_dates))
    
    # 保存缓存
    save_cache(list(result), source='web' if fetched else 'fallback')
    
    # 统计
    year_counts = {}
    for d in result:
        y = d.year
        year_counts[y] = year_counts.get(y, 0) + 1
    
    print(f"  [FOMC] 最终结果: {len(result)}个日期, 覆盖{result[0].year}-{result[-1].year}")
    for y in sorted(year_counts):
        print(f"    {y}: {year_counts[y]}次")
    
    return result


if __name__ == '__main__':
    # 测试
    dates = get_fomc_dates()
    print(f"\n前5个: {dates[:5].tolist()}")
    print(f"后5个: {dates[-5:].tolist()}")
    
    # 验证2026年
    d2026 = [d for d in dates if d.year == 2026]
    print(f"\n2026年FOMC日期: {[d.strftime('%Y-%m-%d') for d in d2026]}")
    
    # 验证距下次FOMC天数（当前日期）
    now = pd.Timestamp.now()
    future = dates[dates >= now]
    if len(future) > 0:
        print(f"\n当前: {now.strftime('%Y-%m-%d')}")
        print(f"下次FOMC: {future[0].strftime('%Y-%m-%d')} (距今{(future[0] - now).days}天)")
