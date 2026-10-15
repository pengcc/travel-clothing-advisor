#!/usr/bin/env python3
"""Germany clothing prototype: 14-day forecast or 30-day historical outlook.

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

from forecast_advice import (forecast_url, process, format_user_advice, format_advice,
                             USER_CLOTHING, NEAR_THIRTEEN_TOLERANCE_C)
from validate_clothing_rules import level

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


def historic_url(city, start, end, *, model=None):
    params = {
        'latitude': city['latitude'], 'longitude': city['longitude'],
        'timezone': 'Europe/Berlin', 'start_date': start.isoformat(),
        'end_date': end.isoformat(), 'hourly': 'temperature_2m',
        'daily': 'precipitation_sum,snowfall_sum',
        'temperature_unit': 'celsius', 'precipitation_unit': 'mm'}
    if model is not None:
        params['models'] = model
    return HISTORY_URL + '?' + urlencode(params)


def historical_summary(payload, start, end, *, require_edges=False):
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
    # Use explicit local-hour sample windows, not a daily all-hours minimum.
    # These are historical ERA5 temperature samples, never a room-temperature
    # estimate or a prediction for the upcoming trip.
    edges = {d: {'morning': [], 'evening': []} for d in expected}
    for stamp, temp in zip(hours, temps):
        date, _, clock = stamp.partition('T')
        if date not in by_day or not isinstance(temp, (int, float)) or isinstance(temp, bool):
            continue
        hour = int(clock[:2])
        if 9 <= hour <= 18:
            by_day[date].append(temp)
        elif 6 <= hour <= 8:
            edges[date]['morning'].append(temp)
        elif 19 <= hour <= 22:
            edges[date]['evening'].append(temp)
    if any(not by_day[day] for day in expected):
        raise ValueError('Historical daytime temperatures are incomplete')
    # A year lacking an entire morning or evening window is not a valid
    # baseline for a claim about morning/evening temperatures.
    complete_edges = all(edges[day]['morning'] and edges[day]['evening'] for day in expected)
    if require_edges and not complete_edges:
        raise ValueError('Historical morning/evening temperatures are incomplete')
    daytemps = [round(median(by_day[day]), 1) for day in expected]
    edgetemps = ([value for day in expected for group in ('morning', 'evening')
                  for value in edges[day][group]] if complete_edges else [])
    return {
        'start': start.isoformat(), 'end': end.isoformat(),
        'typical_daytime': round(median(daytemps), 1),
        'coldest_daytime': min(daytemps),
        'warmest_daytime': max(daytemps),
        'typical_edge': round(median(edgetemps), 1) if edgetemps else None,
        'coldest_edge': round(min(edgetemps), 1) if edgetemps else None,
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


def validate_month_trip(start, end, now):
    """Allow complete trips in the next 30 calendar days, never a partial estimate."""
    if start > end:
        raise ValueError('旅行结束日期不能早于开始日期')
    if start < now.date():
        raise ValueError('请使用今天或之后的旅行日期')
    if end > now.date() + dt.timedelta(days=29):
        raise ValueError('本版最长支持从今天起30个日历日；不能用同期历史资料冒充更远的旅行预报')


def build(city_name, start, end, preference='normal', *, now=None, fetch=get_json):
    now = (now or dt.datetime.now(ZONE)).astimezone(ZONE)
    forecast_covered = end <= now.date() + dt.timedelta(days=13)
    if forecast_covered:
        validate_trip(start, end, now)
    else:
        validate_month_trip(start, end, now)

    place = select_city(fetch(geocode_url(city_name)), city_name)
    if not forecast_covered:
        # Fixed ERA5 model, not the provider's mixed "best match" models.
        # Eight individual past trip windows, with no forecast request or
        # pseudo-precision for days beyond the live 14-day horizon.
        histories = []
        for years in range(1, 9):
            past_start, past_end = year_earlier(start, years), year_earlier(end, years)
            payload = fetch(historic_url(place, past_start, past_end, model='era5'))
            histories.append(historical_summary(payload, past_start, past_end, require_edges=True))
        typical = round(median(h['typical_daytime'] for h in histories), 1)
        return {
            'kind': 'historical_outlook', 'city': place['name'],
            'start': start.isoformat(), 'end': end.isoformat(),
            'main_level': level(typical), 'typical_daytime': typical,
            'preference': preference,
        }, histories

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


def format_month_outlook(outlook, histories, *, details=False):
    """A packing decision first, then only weather caveats that change packing."""
    if len(histories) != 8:
        raise ValueError('需要八个完整历史年份才能生成提前准备参考')

    typical = outlook['typical_daytime']
    lower = min(h['typical_daytime'] for h in histories)
    upper = max(h['typical_daytime'] for h in histories)
    coldest_day = min(h['coldest_daytime'] for h in histories)
    edge_typical = round(median(h['typical_edge'] for h in histories), 1)
    edge_lower = min(h['typical_edge'] for h in histories)
    edge_upper = max(h['typical_edge'] for h in histories)
    edge_coldest = min(h['coldest_edge'] for h in histories)
    precip_years = sum(h['precipitation_days'] > 0 for h in histories)
    snow_years = sum(h['snow_days'] > 0 for h in histories)
    level_no = outlook['main_level']

    near_thirteen = level_no in (4, 5) and abs(typical - 13) <= NEAR_THIRTEEN_TOLERANCE_C
    if near_thirteen:
        garment_advice = ('带保暖程度适中的外套；怕冷可用轻羽绒替代外套。'
                          '搭配长袖＋毛衣或抓绒，室内可脱外层。')
    else:
        # Put the thickness decision first and avoid listing the same
        # outerwear twice under "what to pack" and "what to wear".
        garment_advice = {
            1: '短袖及透气轻薄衣物为主，不需要保暖外套。',
            2: '短袖或薄长袖为主，早晚可加一件轻薄外层。',
            3: '带薄外套，搭配短袖或薄长袖，方便随时穿脱。',
            4: '带保暖适中的外套，内搭长袖＋毛衣或抓绒，室内可脱外层。',
            5: '带轻羽绒或同等保暖外套，内搭长袖＋毛衣或抓绒，室内可脱外层。',
            6: '带较厚冬季外套，内搭保暖衣＋毛衣或抓绒，室内可脱外层。',
        }[level_no]
    lines = [
        f"{outlook['city']} · {outlook['start']}～{outlook['end']}",
        '提前备衣参考（历史同期，不是今年的具体预报）',
        '',
        f'主要建议：{garment_advice}',
    ]

    # Absolute chilly temperatures matter even if daytime and early/evening
    # medians are similar (e.g. 7.7°C vs 6.6°C in the observed Berlin case).
    # 10°C is a conservative, candidate copy threshold, not a comfort law.
    if edge_typical < 10:
        note = (f'早晚偏冷：历史同期早晚约 {edge_typical:g}°C，'
                '早出晚归注意保暖。')
        if edge_coldest <= 0:
            note = note.removesuffix('。') + ('；历史上较冷时段曾接近或低于0°C，'
                                            '长时间在室外可加帽子或围巾。')
        lines.append(note)
    elif typical - edge_typical >= 5:
        lines.append(f'早晚温差：历史同期早晚通常比白天凉约 {typical-edge_typical:g}°C，'
                     '外出可随身带一件薄外套。')

    # Historical precipitation totals do not identify liquid rain: they can
    # include snow. Keep the label as precipitation, not forecast rain.
    if precip_years >= 2:
        lines.append('降水提醒：历史同期多次出现较明显降水，建议带折叠伞或防水外层。')
    if snow_years:
        lines.append('降雪提醒：历史同期曾出现降雪；临近出发如果预报有雪，'
                     '注意保暖和鞋底防滑。')

    if outlook['preference'] == 'cold':
        lines.append('比较怕冷：可额外带一件可脱的抓绒或毛衣。')
    elif outlook['preference'] == 'hot':
        lines.append('比较怕热：尽量使用方便脱下的中间层。')

    lines.extend([
        '',
        f'参考依据：过去8年同期白天代表气温约 {typical:g}°C。'
        '出发前两周内，按最新预报再确认衣物厚度。',
    ])
    if details:
        lines.extend([
            '',
            f'数据依据：过去8年同期各年份白天代表温度 {lower:g}～{upper:g}°C，'
            f'早晚代表温度 {edge_lower:g}～{edge_upper:g}°C；'
            f'个别历史白天代表值最低 {coldest_day:g}°C，'
            f'早晚单小时采样最低 {edge_coldest:g}°C。'
            f'对应行程有明显降水的历史年份 {precip_years}/8、'
            f'有降雪的历史年份 {snow_years}/8。',
            '时间窗：白天09–18时，早晚06–08时及19–22时。'
            '这些是ERA5历史再分析值，不是实际气象站逐小时观测，'
            '不能据此推算今年每天的天气概率。城市位置来源：GeoNames。',
            '逐年历史参考：',
        ])
        for h in histories:
            lines.append(f"• {h['start']}～{h['end']}："
                         f"白天代表 {h['typical_daytime']:g}°C、最凉白天 {h['coldest_daytime']:g}°C；"
                         f"早晚代表 {h['typical_edge']:g}°C、早晚最低样本 {h['coldest_edge']:g}°C；"
                         f"明显降水 {h['precipitation_days']} 天，降雪 {h['snow_days']} 天。")
    return '\n'.join(lines)


def format_trip(recommendation, histories, *, details=False):
    if recommendation.get('kind') == 'historical_outlook':
        return format_month_outlook(recommendation, histories, details=details)
    # When real forecasts cover the trip, put the decision and the current
    # date-specific alerts first. The extra two past-year rows are evidence
    # for curious users, not the default answer to "what should I pack?".
    if not details:
        return format_user_advice(recommendation)
    parts = [format_advice(recommendation),
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
