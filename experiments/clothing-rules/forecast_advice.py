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
        edge = [t for hour, t in hours if hour < 9 or hour >= 19]
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
    rain_days = [r for r in rows if (numeric(r['rain_probability']) and r['rain_probability'] >= 60) or
                 (numeric(r['precip_mm']) and r['precip_mm'] >= 2)]
    wind_days = [r for r in rows if numeric(r['gust_kmh']) and r['gust_kmh'] >= 45]
    snow_days = [r for r in rows if numeric(r['snow_cm']) and r['snow_cm'] > 0]
    edge_low = [r for r in rows if numeric(r['evening_morning_min']) and r['evening_morning_min'] < common - 6]
    advice = [LEVEL_NAMES[main]]
    if colddays:
        coldest = min(colddays, key=lambda r: r['daytemp'])
        advice.append(f"偏冷日 {coldest['date']} 白天约 {coldest['daytemp']:g}°C，建议备可加的保暖层（L{coldest['level']}）；不必每天都穿最厚。")
    if warmdays:
        advice.append('部分日子白天更暖，备可脱的外层或轻薄上衣。')
    if edge_low:
        advice.append('部分早晚明显更凉，注意可穿脱的分层；公交、商场和室内便于脱下。')
    if rain_days:
        advice.append(f'预计 {len(rain_days)} 天有较明显降水信号，考虑雨具或防雨外层。')
    if wind_days:
        advice.append(f'预计 {len(wind_days)} 天有较强阵风，注意外层挡风。')
    if snow_days:
        advice.append('部分日期可能降雪，注意适当的鞋和外套。')
    if preference == 'cold' and main >= 3:
        advice.append('比较怕冷：偏凉时段多备一件容易脱的保暖层。')
    elif preference == 'hot' and main <= 5:
        advice.append('比较怕热：可减少一件中间层，但风雨防护仍需考虑。')
    if main <= 2 and not colddays:
        advice.append('整体偏暖，不需要仅因某天比最热一天略凉就带厚羽绒服。')
    return {'dates': dates, 'days': rows, 'main_level': main,
            'typical_daytime': common, 'advice': advice,
            'source': SOURCE, 'source_kind': 'weather forecast',
            'generated_at': now.isoformat()}


def format_advice(result):
    lines = [f"柏林未来14天穿衣建议｜{result['dates'][0]}—{result['dates'][-1]}",
             f"典型白天约 {result['typical_daytime']:g}°C → L{result['main_level']}（推荐厚度，不是必须穿齐的衣物清单）",
             '建议：']
    lines.extend('• ' + line for line in result['advice'])
    lines.append('每日预报（白天 09–18 点中位气温；— 表示今日白天已过去）：')
    for i, row in enumerate(result['days']):
        temp = '—' if row['daytemp'] is None else f"{row['daytemp']:g}°C"
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
    args = parser.parse_args()
    if args.now and not args.fixture:
        parser.error('--now is only allowed with --fixture')
    data = json.loads(args.fixture.read_text(encoding='utf-8')) if args.fixture else fetch_forecast()
    now = dt.datetime.fromisoformat(args.now) if args.now else None
    print(format_advice(process(data, now=now, preference=args.preference)))


if __name__ == '__main__':
    main()
