#!/usr/bin/env python3
"""Berlin 14-day weather-to-clothing demo. Live API, optional offline JSON fixture.

No deployment, scheduler, provider lock-in, or forecast accuracy claim is implied.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from validate_clothing_rules import LEVEL_NAMES, level

TIMEZONE = 'Europe/Berlin'
API_URL = 'https://api.open-meteo.com/v1/forecast'
SOURCE = 'https://open-meteo.com/'
DAILY_FIELDS = ('precipitation_probability_max', 'precipitation_sum', 'snowfall_sum', 'wind_gusts_10m_max')


def forecast_url():
    params = {
        'latitude': 52.52,
        'longitude': 13.41,
        'timezone': TIMEZONE,
        'forecast_days': 14,
        'temperature_unit': 'celsius',
        'wind_speed_unit': 'kmh',
        'precipitation_unit': 'mm',
        'hourly': 'temperature_2m',
        'daily': ','.join(DAILY_FIELDS),
    }
    return API_URL + '?' + urlencode(params)


def fetch_forecast():
    with urlopen(forecast_url(), timeout=20) as response:
        return json.load(response)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and -10000 < float(value) < 10000


def format_date_groups(rows):
    """Readable groups of consecutive travel dates (never hides multiple cold days)."""
    days = sorted({dt.date.fromisoformat(row['date']) for row in rows})
    if not days:
        return ''
    groups = []
    first = last = days[0]
    for day in days[1:]:
        if day == last + dt.timedelta(days=1):
            last = day
        else:
            groups.append((first, last))
            first = last = day
    groups.append((first, last))
    def show(start, end):
        if start == end:
            return f'{start.month}月{start.day}日'
        if start.year == end.year and start.month == end.month:
            return f'{start.month}月{start.day}～{end.day}日'
        return f'{start.month}月{start.day}日至{end.month}月{end.day}日'
    return '、'.join(show(a, b) for a, b in groups)


def process(payload, now=None, preference='normal'):
    if payload.get('timezone') != TIMEZONE:
        raise ValueError('Forecast timezone must be Europe/Berlin')
    tz = ZoneInfo(TIMEZONE)
    now = now or dt.datetime.now(tz)
    if now.tzinfo is None:
        raise ValueError('Reference time must include a UTC offset')
    now = now.astimezone(tz)
    daily = payload.get('daily') or {}
    hourly = payload.get('hourly') or {}
    dates = daily.get('time') or []
    timestamps = hourly.get('time') or []
    hourly_temps = hourly.get('temperature_2m') or []
    if not (len(dates) == 14 and len(timestamps) == len(hourly_temps)):
        raise ValueError('Expected 14 daily dates and matching hourly temperatures')
    if not all(dates[i] == (now.date() + dt.timedelta(days=i)).isoformat() for i in range(14)):
        raise ValueError('Forecast dates are not 14 consecutive days starting today')
    for field in DAILY_FIELDS:
        if len(daily.get(field, [])) != 14:
            raise ValueError('Missing/incomplete daily field: ' + field)
    obs = {}
    for stamp, val in zip(timestamps, hourly_temps):
        at = dt.datetime.fromisoformat(stamp)
        if at.tzinfo is None:
            # API returns local wall-clock timestamps without offset
            at = at.replace(tzinfo=tz)
        else:
            at = at.astimezone(tz)
        if numeric(val) and at >= now:
            obs.setdefault(at.date().isoformat(), []).append((at.hour, float(val)))
    rows = []
    for i, day in enumerate(dates):
        hours = obs.get(day, [])
        daytemps = [t for hour, t in hours if 9 <= hour <= 18]
        edge = [t for hour, t in hours if 6 <= hour <= 8 or 19 <= hour <= 22]
        if i > 0 and not daytemps:
            raise ValueError('Missing daytime forecast for ' + day)
        daytemp = round(median(daytemps), 1) if daytemps else None
        rows.append({
            'date': day,
            'daytemp': daytemp,
            'evening_morning_min': round(min(edge), 1) if edge else None,
            'level': level(daytemp) if daytemp is not None else None,
            'rain_probability': daily['precipitation_probability_max'][i],
            'precip_mm': daily['precipitation_sum'][i],
            'snow_cm': daily['snowfall_sum'][i],  # actual unit snowfall_sum: centimeters
            'gust_kmh': daily['wind_gusts_10m_max'][i],
        })
    # Skip current partial day if daytime has already passed. Do not treat previous
    # hours of today as the future traveler's exposure.
    candidates = [r for r in rows if r['level'] is not None]
    if not candidates:
        raise ValueError('No usable future daytime forecast')
    common = round(median([r['daytemp'] for r in candidates]), 1)
    main = level(common)
    colddays = [r for r in candidates if r['level'] > main and r['level'] >= 4]
    warmdays = [r for r in candidates if r['level'] < main]
    # A past partial day cannot be treated as a forecast of the remaining day:
    # Open-Meteo daily totals/probabilities are whole-day values.
    future_day_rows = [r for r in rows if r['daytemp'] is not None]
    rain_days = [r for r in future_day_rows if (numeric(r['rain_probability']) and r['rain_probability'] >= 60) or
                 (numeric(r['precip_mm']) and r['precip_mm'] >= 2)]
    wind_days = [r for r in future_day_rows if numeric(r['gust_kmh']) and r['gust_kmh'] >= 45]
    snow_days = [r for r in future_day_rows if numeric(r['snow_cm']) and r['snow_cm'] > 0]
    edge_low = [r for r in rows if numeric(r['evening_morning_min']) and r['evening_morning_min'] < common - 6]
    advice = [LEVEL_NAMES[main]]
    if colddays:
        # Do not single out the coldest day in week two while hiding a
        # multi-day cooler spell in week one.
        for indices, prefix, suffix in (
            (range(7), '近期（第1～7天）', '适当备一层可加的保暖衣物；不必每天都穿最厚。'),
            (range(7, 14), '后期（第8～14天）', '后期预报有较大不确定性，先留意，临近再确认。'),
        ):
            group = [r for i, r in enumerate(rows) if i in indices and r in colddays]
            if not group:
                continue
            coldest = min(r['daytemp'] for r in group)
            warmest = max(r['daytemp'] for r in group)
            range_text = (f'{coldest:g}°C' if coldest == warmest
                          else f'{coldest:g}～{warmest:g}°C')
            count = f'（共{len(group)}天）' if len(group) > 1 else ''
            advice.append(f'{prefix} {format_date_groups(group)}{count}偏冷，'
                          f'白天约 {range_text}（L{max(r["level"] for r in group)}），{suffix}')
    if warmdays:
        advice.append('部分日子白天更暖，备可脱的外层或轻薄上衣。')
    if edge_low:
        advice.append('部分早晚明显更凉，注意可穿脱的分层；公交、商场和室内便于脱下。')
    if rain_days:
        count = f'（共{len(rain_days)}天）' if len(rain_days) > 1 else ''
        advice.append(f'预计 {format_date_groups(rain_days)}{count}有较明显降水信号，考虑雨具或防雨外层；较远日期请临近复查。')
    if wind_days:
        advice.append(f'预计 {format_date_groups(wind_days)} 有较强阵风信号，注意外层挡风。')
    if snow_days:
        advice.append('部分日期可能降雪，注意适当的鞋和外套。')
    if preference == 'cold' and main >= 3:
        advice.append('比较怕冷：偏凉时段多备一件容易脱的保暖层。')
    elif preference == 'hot' and main <= 5:
        advice.append('比较怕热：可减少一件中间层，但风雨防护仍需考虑。')
    if main <= 2 and not colddays:
        advice.append('整体偏暖，不需要仅因某天比最热一天略凉就带厚羽绒服。')
    return {'dates': dates, 'days': rows, 'main_level': main,
            'preference': preference,
            'cold_dates': [r['date'] for r in colddays],
            'rain_dates': [r['date'] for r in rain_days],
            'wind_dates': [r['date'] for r in wind_days],
            'snow_dates': [r['date'] for r in snow_days],
            'edge_cool': bool(edge_low),
            'typical_daytime': common, 'advice': advice,
            'source': SOURCE, 'source_kind': 'weather forecast',
            'generated_at': now.isoformat()}


USER_CLOTHING = {
    1: '以短袖、透气的轻薄衣物为主。',
    2: '短袖或薄长袖为主，可根据早晚温差备用轻薄外层。',
    3: '薄长袖或短袖，备一件方便穿脱的薄外套。',
    4: '建议准备长袖、抓绒或毛衣，以及一件适合秋季的外套。',
    5: '建议准备长袖、保暖中间层，以及保暖外套或轻羽绒。',
    6: '建议准备保暖内搭、毛衣或抓绒，以及适合冬季的较厚外套。',
}


def format_user_advice(result):
    """Short traveler-facing copy; internal levels and full day table stay in --details."""
    active = [row for row in result['days'] if row['daytemp'] is not None]
    if not active:
        raise ValueError('No remaining daytime forecast')
    year = dt.date.fromisoformat(active[0]['date']).year
    first = dt.date.fromisoformat(active[0]['date'])
    last = dt.date.fromisoformat(active[-1]['date'])
    if first.year == last.year:
        period = f'{year}年{format_date_groups(active)}'
    else:
        period = f'{first.year}年{first.month}月{first.day}日至{last.year}年{last.month}月{last.day}日'
    lines = [f'柏林 · {period}穿衣建议',
             '',
             USER_CLOTHING[result['main_level']],
             f'多数白天约 {result["typical_daytime"]:g}°C，衣服建议采用可增减的搭配。']
    by_date = {row['date']: row for row in result['days']}
    cold = set(result['cold_dates'])
    for start, end, long_range in ((0, 7, False), (7, 14, True)):
        subset = [row for i, row in enumerate(result['days'])
                  if start <= i < end and row['date'] in cold]
        if not subset:
            continue
        lo, hi = min(r['daytemp'] for r in subset), max(r['daytemp'] for r in subset)
        degrees = f'{lo:g}°C' if lo == hi else f'{lo:g}～{hi:g}°C'
        when = format_date_groups(subset)
        if long_range:
            lines.append(f'后期留意：{when}白天可能约 {degrees}，建议临近日期再确认是否需要更厚的外套。')
        else:
            lines.append(f'降温提醒：{when}白天约 {degrees}，建议额外备一层保暖衣物。')
    if result['edge_cool']:
        lines.append('早晚可能更凉，分层穿着方便随时穿脱。')
    rainy = [by_date[day] for day in result['rain_dates']]
    if rainy:
        far_only = all(result['days'].index(row) >= 7 for row in rainy)
        note = '；日期较远，临近再确认' if far_only else ''
        lines.append(f'降雨提醒：{format_date_groups(rainy)}可能下雨，备雨具或防雨外套{note}。')
    windy = [by_date[day] for day in result['wind_dates']]
    if windy:
        lines.append(f'大风提醒：{format_date_groups(windy)}可能风较大，外套注意挡风。')
    snowy = [by_date[day] for day in result['snow_dates']]
    if snowy:
        lines.append(f'降雪提醒：{format_date_groups(snowy)}可能下雪，注意保暖和鞋底防滑。')
    if result['preference'] == 'cold' and result['main_level'] >= 3:
        lines.append('比较怕冷：在偏凉时段可以再多备一件轻便保暖层。')
    elif result['preference'] == 'hot' and result['main_level'] <= 5:
        lines.append('比较怕热：中间层可以少穿一件，仍要留意风雨。')
    if (result['main_level'] in (3, 4)
            and min(row['daytemp'] for row in active) >= 9
            and not snowy
            and min((r['evening_morning_min'] for r in result['days']
                     if r['evening_morning_min'] is not None), default=9) >= 0):
        lines.append('按当前预报，一般不必优先准备厚冬季羽绒服，但只带薄衣服也不合适。')
    updated = dt.datetime.fromisoformat(result['generated_at']).astimezone(ZoneInfo(TIMEZONE))
    lines.extend(['', f'预报查询：{updated.month}月{updated.day}日 {updated:%H:%M}（柏林时间）'
                     f' · 来源：Open-Meteo',
                  '较远日期的天气可能变化；个人冷热感受不同，临近出发再查看。'])
    return '\n'.join(lines)


def format_advice(result):
    lines = [f"柏林未来14个日历日穿衣建议｜{result['dates'][0]}—{result['dates'][-1]}",
             f"典型白天约 {result['typical_daytime']:g}°C → L{result['main_level']}（推荐厚度，不是必须穿齐的衣物清单）",
             '建议：']
    lines.extend('• ' + line for line in result['advice'])
    lines.append('每日预报（白天 09–18 点中位气温）：')
    for i, row in enumerate(result['days']):
        temp = '今日白天已过' if row['daytemp'] is None else f"{row['daytemp']:g}°C"
        mark = '' if row['level'] is None else f"L{row['level']}"
        flag = ' · 后期预报需复查' if i >= 7 else ''
        lines.append(f"{row['date']}: {temp} {mark}{flag}")
    lines.append('第8～14天的不确定性较高，请在接近出发时复查；每个人对冷热的感受也不同。')
    lines.append(f"数据：Open-Meteo（{result['source']}），读取/计算时间 {result['generated_at']}；建议由规则推算，并非天气服务商的穿衣建议。")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, help='Run with a saved API JSON instead of making an HTTP request')
    parser.add_argument('--now', help='Reference ISO datetime with offset, only for offline fixture replay')
    parser.add_argument('--preference', choices=['normal', 'cold', 'hot'], default='normal')
    parser.add_argument('--details', action='store_true', help='Show technical daily levels and forecast trace instead of the short traveler summary')
    args = parser.parse_args()
    if args.now and not args.fixture:
        parser.error('--now is only allowed with --fixture')
    data = json.loads(args.fixture.read_text(encoding='utf-8')) if args.fixture else fetch_forecast()
    now = dt.datetime.fromisoformat(args.now) if args.now else None
    result = process(data, now=now, preference=args.preference)
    print(format_advice(result) if args.details else format_user_advice(result))


if __name__ == '__main__':
    main()
