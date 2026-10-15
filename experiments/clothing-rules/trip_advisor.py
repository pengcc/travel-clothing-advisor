#!/usr/bin/env python3
"""Germany trip clothing prototype: selected dates + current forecast + two past years.

Standard-library experiment. Historical data are reanalysis, not observations
at a particular station and not a forecast of the trip.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
from statistics import median
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from forecast_advice import forecast_url, process, format_user_advice, format_advice

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
HISTORY_URL = 'https://archive-api.open-meteo.com/v1/archive'
ZONE = ZoneInfo('Europe/Berlin')


def get_json(url):
    with urlopen(url, timeout=25) as response:
        data = json.load(response)
    if not isinstance(data, dict) or data.get('error'):
        raise ValueError('Weather data service rejected the request: ' + str(data))
    return data


def geocode_url(name):
    # A federal-state qualifier is interpreted locally after lookup.
    # Query by settlement here to inspect all exact-name candidates, even
    # if an API result is a smaller namesake in another state.
    lookup_name = name.partition(',')[0].strip()
    return GEOCODE_URL + '?' + urlencode({
        'name': lookup_name, 'count': 30, 'language': 'de', 'countryCode': 'DE'})


def select_city(payload, requested):
    # Open-Meteo may return places with the exact same name in different
    # German states (for example the capital Berlin and Berlin, Schleswig-Holstein).
    # Use provider metadata only when it safely distinguishes the destination.
    name, separator, qualifier = requested.strip().partition(',')
    name, qualifier = name.strip(), qualifier.strip()
    if not name or (separator and not qualifier):
        raise ValueError('请输入德国城市名称；可选在逗号后加州名，例如 Berlin, Land Berlin')
    candidates = [v for v in payload.get('results', [])
                  if v.get('country_code') == 'DE'
                  and isinstance(v.get('latitude'), (int, float))
                  and not isinstance(v.get('latitude'), bool)
                  and isinstance(v.get('longitude'), (int, float))
                  and not isinstance(v.get('longitude'), bool)
                  and v.get('timezone') == 'Europe/Berlin']
    exact = [v for v in candidates if isinstance(v.get('name'), str)
             and v['name'].casefold() == name.casefold()]
    if separator and qualifier.casefold() not in ('de', 'deutschland', 'germany'):
        # The same federal state may be written "Land Berlin" or "Berlin"
        # depending on the API's localized administrative display name.
        def normalize_admin1(value):
            return value.casefold().removeprefix('land ').strip()
        exact = [v for v in exact if isinstance(v.get('admin1'), str)
                 and normalize_admin1(v['admin1']) == normalize_admin1(qualifier)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1 and (not separator or qualifier.casefold() in ('de', 'deutschland', 'germany')):
        # Distinguish nationally/state-significant cities from namesakes
        # without assuming all smaller places publish a population. Unique
        # PPLC is a national capital (Berlin), unique PPLA a state capital
        # (München). Lesser administrative seats are *not* automatically
        # selected ahead of potentially larger cities.
        for code in ('PPLC', 'PPLA'):
            seats = [v for v in exact if v.get('feature_code') == code]
            if len(seats) == 1:
                return seats[0]
            if len(seats) > 1:
                places = ', '.join(sorted({str(v.get('admin1') or '?') for v in seats}))
                raise ValueError(
                    f'城市名称不唯一：{requested}（{places}）；请用「城市, 州名」指定地点。'
                )
        # Otherwise only select a clearly dominant large city when every
        # exact match has a credible reported population. Missing data,
        # close rivals and ties remain ambiguous.
        populations = [v.get('population') for v in exact]
        if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0
               for n in populations):
            ranked = sorted(exact, key=lambda v: v['population'], reverse=True)
            if (ranked[0]['population'] >= 100_000
                    and ranked[0]['population'] >= 10 * max(1, ranked[1]['population'])):
                return ranked[0]
    if exact:
        places = ', '.join(sorted({str(v.get('admin1') or '?') for v in exact}))
        raise ValueError(f'城市名称不唯一：{requested}（{places}）；请用「城市, 州名」指定地点。')
    # Never silently choose a prefix result or a different state.
    choices = ', '.join(v.get('name', '') for v in candidates[:5] if isinstance(v.get('name'), str))
    raise ValueError(f'找不到唯一匹配的德国城市「{requested}」。候选：{choices or "无"}')


def year_earlier(day, years):
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        # 29 February has no counterpart in non-leap years.
        return day.replace(year=day.year - years, day=28)


def historic_url(city, start, end):
    return HISTORY_URL + '?' + urlencode({
        'latitude': city['latitude'], 'longitude': city['longitude'],
        'timezone': 'Europe/Berlin', 'start_date': start.isoformat(),
        'end_date': end.isoformat(), 'hourly': 'temperature_2m',
        'daily': 'precipitation_sum,snowfall_sum',
        'temperature_unit': 'celsius', 'precipitation_unit': 'mm'})


def historical_summary(payload, start, end):
    if payload.get('timezone') != 'Europe/Berlin':
        raise ValueError('Historical data must use Europe/Berlin timezone')
    daily = payload.get('daily') or {}
    hourly = payload.get('hourly') or {}
    expected = [(start + dt.timedelta(days=i)).isoformat()
                for i in range((end-start).days + 1)]
    if daily.get('time') != expected:
        raise ValueError('Historical daily dates do not cover the requested range')
    for field in ('precipitation_sum', 'snowfall_sum'):
        if len(daily.get(field, [])) != len(expected):
            raise ValueError('Historical daily field missing: ' + field)
    hours = hourly.get('time') or []
    temps = hourly.get('temperature_2m') or []
    if len(hours) != len(temps):
        raise ValueError('Historical hourly temperatures are incomplete')
    by_day = {d: [] for d in expected}
    for stamp, temp in zip(hours, temps):
        date, _, clock = stamp.partition('T')
        if date in by_day and 9 <= int(clock[:2]) <= 18 and isinstance(temp, (int, float)):
            by_day[date].append(temp)
    if any(not by_day[day] for day in expected):
        raise ValueError('Historical daytime temperatures are incomplete')
    daytemps = [round(median(by_day[day]), 1) for day in expected]
    return {
        'start': start.isoformat(), 'end': end.isoformat(),
        'typical_daytime': round(median(daytemps), 1),
        'coldest_daytime': min(daytemps),
        'warmest_daytime': max(daytemps),
        'precipitation_days': sum(isinstance(v, (int, float)) and v >= 2
                                  for v in daily['precipitation_sum']),
        'snow_days': sum(isinstance(v, (int, float)) and v > 0
                         for v in daily['snowfall_sum']),
    }


def validate_trip(start, end, now):
    if start > end:
        raise ValueError('旅行结束日期不能早于开始日期')
    if start < now.date():
        raise ValueError('请使用今天或之后的旅行日期')
    if end > now.date() + dt.timedelta(days=13):
        raise ValueError('本版只支持未来14个日历日内的旅行，超过该范围不能用短期预报冒充长期预测')


def build(city_name, start, end, preference='normal', *, now=None, fetch=get_json):
    now = (now or dt.datetime.now(ZONE)).astimezone(ZONE)
    validate_trip(start, end, now)
    place = select_city(fetch(geocode_url(city_name)), city_name)
    forecast = fetch(forecast_url(place['latitude'], place['longitude']))
    recommendation = process(forecast, now=now, preference=preference,
                             start_date=start.isoformat(), end_date=end.isoformat(),
                             city=place['name'])
    summaries = []
    for years in (1, 2):
        past_start, past_end = year_earlier(start, years), year_earlier(end, years)
        historical = fetch(historic_url(place, past_start, past_end))
        summaries.append(historical_summary(historical, past_start, past_end))
    return recommendation, summaries


def format_trip(recommendation, histories, *, details=False):
    parts = [format_advice(recommendation) if details else format_user_advice(recommendation),
             '', '过去两年同期参考（历史再分析数据，不是未来天气预报）：']
    for h in histories:
        parts.append(f"• {h['start']}～{h['end']}：白天典型约 {h['typical_daytime']:g}°C，"
                     f"其中较凉的一天约 {h['coldest_daytime']:g}°C；"
                     f"降水较明显 {h['precipitation_days']} 天，降雪信号 {h['snow_days']} 天。")
    if any(h['coldest_daytime'] <= recommendation['typical_daytime'] - 5 for h in histories):
        parts.append('历史对照：过去两年同期出现过明显更凉的白天，'
                     '可考虑保留易加减的衣物层；是否需要穿着仍以临近出发时的预报为主。')
    parts.append('注：只有两年的同期记录，不能据此确定未来天气概率或气候常态。'
                 '天气数据：Open-Meteo Forecast + Historical Weather；城市数据：GeoNames。')
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--city', default='Berlin', help='German city name, e.g. Berlin or München')
    parser.add_argument('--start', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--end', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--preference', choices=['normal','cold','hot'], default='normal')
    parser.add_argument('--details', action='store_true')
    args = parser.parse_args()
    try:
        forecast, histories = build(args.city, args.start, args.end, args.preference)
        print(format_trip(forecast, histories, details=args.details))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f'无法生成穿衣建议：{error}\n')


if __name__ == '__main__':
    main()
