#!/usr/bin/env python3
"""Replay a candidate clothing model against observed weather (standard library only).

The CSV is a manually transcribed subset of daily DWD station 00433 records
displayed by Blick aufs Wetter: NOT a live forecast or weather API integration.
"""
import argparse
import csv
import datetime as dt
from pathlib import Path
from statistics import median

LEVEL_NAMES = {
    1: 'L1 清凉：短袖、轻薄透气衣物',
    2: 'L2 轻薄：短袖或薄长袖',
    3: 'L3 轻外层：薄上衣或长袖，薄外套可选',
    4: 'L4 中等保暖：长袖，按时段增加毛衣、抓绒或适中外套',
    5: 'L5 加强保暖：抓绒+防风外套，或轻型保暖夹克/轻羽绒',
    6: 'L6 冬季保暖：保暖内搭、保暖外套，必要时帽子手套',
}


def level(t: float) -> int:
    if t >= 28: return 1
    if t >= 23: return 2
    if t >= 18: return 3
    if t >= 13: return 4
    if t >= 6: return 5
    return 6


def load(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as file:
        items = list(csv.DictReader(file))
    if not items:
        raise ValueError('Empty weather sample')
    for row in items:
        dt.date.fromisoformat(row['date'])
        for field in ('tmax_c', 'tmin_c', 'precip_mm', 'snow_cm', 'wind_gust_kmh'):
            row[field] = float(row[field])
        if row['tmin_c'] > row['tmax_c']:
            raise ValueError('Tmin exceeds Tmax: ' + row['date'])
    return sorted(items, key=lambda row: row['date'])


def select_rows(rows: list[dict], start: str, end: str) -> list[dict]:
    start_day, end_day = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    if start_day > end_day:
        raise ValueError('Start date must be on or before end date')
    selected = [row for row in rows if start <= row['date'] <= end]
    wanted = (end_day - start_day).days + 1
    if len(selected) != wanted or len({row['date'] for row in selected}) != wanted:
        raise ValueError(f'Data is not complete for {start} to {end}: expected {wanted} daily records, found {len(selected)}')
    return selected


def recommend(rows: list[dict], preference='normal') -> dict:
    if not rows:
        raise ValueError('No matching weather data')
    highs = [row['tmax_c'] for row in rows]
    lows = [row['tmin_c'] for row in rows]
    typical = median(highs)  # proxy only: daily maximum != typical outdoor-hour temperature
    main = level(typical)
    lower = [row for row in rows if level(row['tmax_c']) > main]
    higher = [row for row in rows if level(row['tmax_c']) < main]
    result = {
        'date_range': f"{rows[0]['date']} — {rows[-1]['date']}",
        'n_days': len(rows),
        'tmax_range': [min(highs), max(highs)],
        'tmin_range': [min(lows), max(lows)],
        'median_daily_high': typical,
        'main_level': main,
        'advice': LEVEL_NAMES[main],
        'notices': [],
    }
    notes = result['notices']
    for boundary in (6, 13, 18, 23, 28):
        if abs(typical - boundary) <= 0.75:
            adjacent = sorted({level(boundary - 0.01), level(boundary + 0.01)})
            notes.append(
                f"典型气温接近 {boundary}°C 分档边界，L{adjacent[0]} / L{adjacent[1]} "
                "都可作为相邻搭配参考，不需因不到 1°C 的差异换整套衣服。"
            )
            break
    cold_days = [row for row in lower if level(row['tmax_c']) >= 4]
    if cold_days:
        coldest = min(cold_days, key=lambda row: row['tmax_c'])
        notes.append(
            f"有 {len(cold_days)} 天白天变得偏凉/寒冷（最低日最高 "
            f"{coldest['tmax_c']:g}°C，{coldest['date']}，"
            f"对应 L{level(coldest['tmax_c'])}），准备可增加的保暖层；"
            "不必每天穿最厚的一套。"
        )
    elif lower and main <= 2:
        notes.append('部分日子不像最热的日子那么热，但白天仍温暖；不需要因此额外携带保暖厚外套。')
    if higher:
        warmest = max(higher, key=lambda row: row['tmax_c'])
        notes.append(
            f"有 {len(higher)} 天白天最高温高于主要档次（最高 "
            f"{warmest['tmax_c']:g}°C，{warmest['date']}），"
            "准备容易脱下的衣物或轻薄上衣。"
        )
    if any(row['tmax_c'] - row['tmin_c'] >= 8 for row in rows):
        notes.append('部分日最高/最低温差较大，外出早晚可备可穿脱一层；日最低未必发生在外出时段。')
    if min(lows) < 0 and main < 6:
        notes.append('记录存在低于 0°C 的日最低温；仅在清晨/深夜实际外出时考虑额外保暖，不因此把整段行程升级为厚冬装。')
    rainy = [row for row in rows if row['precip_mm'] >= 2.0]
    if rainy:
        notes.append(
            f"有 {len(rainy)} 天历史日降水达到 2mm 或以上，考虑可防雨的外层或雨具"
            "（历史日雨量不等于特定时段下雨）。"
        )
    windy = [row for row in rows if row['wind_gust_kmh'] >= 45]
    if windy:
        notes.append(
            f"有 {len(windy)} 天历史最大阵风达到 45 km/h 或以上，"
            "考虑挡风外层，不强制增加保暖档次。"
        )
    if any(row['snow_cm'] >= 1 for row in rows):
        notes.append('记录有地面积雪，考虑保暖及防滑鞋。')
    if preference == 'cold' and main >= 3:
        notes.append('个人偏怕冷：在较凉时段优先多备一层易脱的保暖衣物。')
    if preference == 'hot' and main <= 5:
        notes.append('个人偏怕热：中间层可以轻一点，保留需要的外层挡风/防雨功能。')
    return result


def pretty(result: dict) -> str:
    result_lines = [
        f"【{result['date_range']}】{result['n_days']} 天",
        f"日最高 {result['tmax_range'][0]:g}～{result['tmax_range'][1]:g}°C；"
        f"日最低 {result['tmin_range'][0]:g}～{result['tmin_range'][1]:g}°C",
        f"典型日最高(中位数) {result['median_daily_high']:g}°C → {result['advice']}",
    ]
    return '\n'.join(result_lines + ['- ' + note for note in result['notices']])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(__file__).with_name('berlin_tempelhof_2025_sample.csv'))
    parser.add_argument('--start', required=True)
    parser.add_argument('--end', required=True)
    parser.add_argument('--preference', choices=['normal', 'cold', 'hot'], default='normal')
    args = parser.parse_args()
    days = select_rows(load(args.data), args.start, args.end)
    print(pretty(recommend(days, args.preference)))
