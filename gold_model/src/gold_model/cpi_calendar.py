"""
CPI发布日历动态获取模块
多级fallback：cpiinflationcalculator.com抓取 → 硬编码历史 → 模式估算
BLS官网封锁爬虫，改用第三方聚合站
"""
import json
import os
import re
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

from gold_model.paths import CPI_CACHE

CACHE_FILE = str(CPI_CACHE)

# ── 硬编码历史CPI发布日期（已从BLS/搜索结果验证）──
# 格式：{年份: [发布日期列表]}
HISTORICAL_CPI = {
    2021: ['2021-01-13', '2021-02-10', '2021-03-10', '2021-04-13',
           '2021-05-12', '2021-06-10', '2021-07-13', '2021-08-11',
           '2021-09-14', '2021-10-13', '2021-11-10', '2021-12-10'],
    2022: ['2022-01-12', '2022-02-10', '2022-03-10', '2022-04-12',
           '2022-05-11', '2022-06-10', '2022-07-13', '2022-08-10',
           '2022-09-13', '2022-10-13', '2022-11-10', '2022-12-13'],
    2023: ['2023-01-12', '2023-02-14', '2023-03-14', '2023-04-12',
           '2023-05-10', '2023-06-13', '2023-07-12', '2023-08-10',
           '2023-09-13', '2023-10-12', '2023-11-14', '2023-12-12'],
    2024: ['2024-01-11', '2024-02-13', '2024-03-12', '2024-04-10',
           '2024-05-15', '2024-06-12', '2024-07-11', '2024-08-14',
           '2024-09-11', '2024-10-10', '2024-11-13', '2024-12-11'],
    2025: ['2025-01-13', '2025-02-12', '2025-03-12', '2025-04-10',
           '2025-05-13', '2025-06-11', '2025-07-15', '2025-08-12',
           '2025-09-11', '2025-10-24', '2025-11-13', '2025-12-10'],
    2026: ['2026-01-13', '2026-02-11', '2026-03-11', '2026-04-10',
           '2026-05-13', '2026-06-11', '2026-07-14', '2026-08-12',
           '2026-09-11', '2026-10-14', '2026-11-10', '2026-12-10'],
}

MONTHS_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5,
    'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


def fetch_cpi_from_web():
    """
    从cpiinflationcalculator.com抓取CPI发布日历
    该站展示当前年+下一年的发布日程
    """
    url = 'https://cpiinflationcalculator.com/cpi-release-schedule'
    try:
        resp = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        if resp.status_code != 200:
            print(f"  [CPI] HTTP {resp.status_code}, 使用fallback")
            return {}
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        result = {}  # {year: [timestamp, ...]}
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                # 格式: "January 2025 | February 12, 2025 | 08:30 AM"
                ref_text = cells[0].get_text(strip=True)
                release_text = cells[1].get_text(strip=True)
                
                # 解析参考月："January 2025" → year=2025
                ref_match = re.match(r'(\w+)\s+(\d{4})', ref_text)
                if not ref_match:
                    continue
                ref_year = int(ref_match.group(2))
                
                # 发布日期通常在下月，年份可能=ref_year或ref_year+1
                # 解析 "February 12, 2025"
                rel_match = re.match(r'(\w+)\s+(\d+),?\s*(\d{4})', release_text)
                if not rel_match:
                    continue
                rel_month = MONTHS_MAP.get(rel_match.group(1).lower())
                rel_day = int(rel_match.group(2))
                rel_year = int(rel_match.group(3))
                
                if not rel_month:
                    continue
                
                try:
                    ts = pd.Timestamp(year=rel_year, month=rel_month, day=rel_day)
                    if rel_year not in result:
                        result[rel_year] = []
                    result[rel_year].append(ts)
                except ValueError:
                    continue
        
        # 去重+排序
        for y in result:
            result[y] = sorted(set(result[y]))
        
        total = sum(len(v) for v in result.values())
        if total > 0:
            print(f"  [CPI] 网络抓取成功: {len(result)}年 {total}个发布日期")
        return result
        
    except Exception as e:
        print(f"  [CPI] 抓取失败: {e}, 使用fallback")
        return {}


def estimate_future_cpi(start_year, end_year):
    """
    基于历史模式估算未来CPI发布日期
    CPI通常在参考月的次月10-15日发布，优先周二/三
    """
    estimated = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            # 次月10-15日附近找周二/三
            for day in range(10, 16):
                try:
                    # 参考月=month，发布月=month+1（如果month=12则发布月=次年1月）
                    if month == 12:
                        d = pd.Timestamp(year=year + 1, month=1, day=day)
                    else:
                        d = pd.Timestamp(year=year, month=month + 1, day=day)
                    if d.weekday() in [1, 2]:  # 周二/三
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
        print(f"  [CPI] 缓存保存失败: {e}")


def load_cache():
    """从本地缓存加载"""
    try:
        if not os.path.exists(CACHE_FILE):
            return None
        with open(CACHE_FILE) as f:
            data = json.load(f)
        dates = [pd.Timestamp(d) for d in data['dates']]
        print(f"  [CPI] 缓存加载: {len(dates)}个日期 (更新于{data.get('updated', 'unknown')[:10]})")
        return dates
    except Exception:
        return None


def get_cpi_dates(end_year=None):
    """
    获取CPI发布日期，多级fallback:
    1. cpiinflationcalculator.com抓取
    2. 硬编码历史(2021-2026)
    3. 本地缓存
    4. 模式估算（未来年份）
    
    参数:
        end_year: 需要覆盖到哪一年（默认当前年+2）
    返回:
        pd.DatetimeIndex，排序后的CPI发布日期
    """
    if end_year is None:
        end_year = datetime.now().year + 2
    
    print("[CPI] 获取CPI发布日历...")
    
    # Level 1: 尝试从网络抓取
    fetched = fetch_cpi_from_web()
    
    # Level 2: 合并硬编码历史 + 抓取结果（按月去重，网络优先）
    monthly_dates = {}  # {(year, month): timestamp}，同月只保留一个
    
    # 先放硬编码历史
    for year, dates in HISTORICAL_CPI.items():
        for d in dates:
            ts = pd.Timestamp(d)
            key = (ts.year, ts.month)
            monthly_dates[key] = ts
    
    # 网络抓取覆盖硬编码（同月取网络版本）
    if fetched:
        for year, dates in fetched.items():
            for d in dates:
                key = (d.year, d.month)
                monthly_dates[key] = d
    
    all_dates = set(monthly_dates.values())
    
    # Level 4: 网络失败时用缓存+估算补齐
    current_year = datetime.now().year
    if not fetched:
        print("  [CPI] 抓取失败，使用缓存+模式估算")
        cached = load_cache()
        cached_years = set()
        if cached:
            for d in cached:
                all_dates.add(d)
                cached_years.add(d.year)
        for y in range(current_year, end_year + 1):
            if y not in cached_years and y not in HISTORICAL_CPI:
                estimated = estimate_future_cpi(y, y)
                for d in estimated:
                    all_dates.add(d)
                print(f"  [CPI] {y}年估算: {len(estimated)}个日期")
    else:
        # 抓取成功，检查是否有未来年份缺口
        fetched_years = set(fetched.keys())
        for y in range(max(fetched_years) + 1, end_year + 1):
            estimated = estimate_future_cpi(y, y)
            for d in estimated:
                all_dates.add(d)
            print(f"  [CPI] {y}年估算: {len(estimated)}个日期")
    
    result = pd.DatetimeIndex(sorted(all_dates))
    
    # 保存缓存
    save_cache(list(result), source='web' if fetched else 'fallback')
    
    # 统计
    year_counts = {}
    for d in result:
        y = d.year
        year_counts[y] = year_counts.get(y, 0) + 1
    
    print(f"  [CPI] 最终结果: {len(result)}个日期, 覆盖{result[0].year}-{result[-1].year}")
    for y in sorted(year_counts):
        print(f"    {y}: {year_counts[y]}次")
    
    return result


if __name__ == '__main__':
    # 测试
    dates = get_cpi_dates()
    print(f"\n前5个: {dates[:5].tolist()}")
    print(f"后5个: {dates[-5:].tolist()}")
    
    # 验证2026年
    d2026 = [d for d in dates if d.year == 2026]
    print(f"\n2026年CPI发布日期: {[d.strftime('%Y-%m-%d') for d in d2026]}")
    
    # 验证距下次CPI天数
    now = pd.Timestamp.now()
    future = dates[dates >= now]
    if len(future) > 0:
        print(f"\n当前: {now.strftime('%Y-%m-%d')}")
        print(f"下次CPI: {future[0].strftime('%Y-%m-%d')} (距今{(future[0] - now).days}天)")
