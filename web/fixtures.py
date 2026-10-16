"""Authored UI fixtures, never weather calculations or live service data."""
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo('Europe/Berlin')
# Stable controlled IDs; Phase 2 replaces this small catalog with resolved city search.
CITIES = [
    dict(id=i, zh=z, name=n, state=s, aliases=a)
    for i, z, n, s, a in [
        ('berlin', '柏林', 'Berlin', 'Berlin', []),
        ('munich', '慕尼黑', 'München', 'Bayern', ['munich', 'munchen']),
        ('hamburg', '汉堡', 'Hamburg', 'Hamburg', []),
        ('frankfurt', '法兰克福', 'Frankfurt am Main', 'Hessen', ['frankfurt']),
        ('cologne', '科隆', 'Köln', 'Nordrhein-Westfalen', ['cologne', 'koln']),
        ('dresden', '德累斯顿', 'Dresden', 'Sachsen', []),
        ('heidelberg', '海德堡', 'Heidelberg', 'Baden-Württemberg', []),
        ('nuremberg', '纽伦堡', 'Nürnberg', 'Bayern', ['nuremberg', 'nurnberg']),
        ('dusseldorf', '杜塞尔多夫', 'Düsseldorf', 'Nordrhein-Westfalen', ['dusseldorf']),
        ('leipzig', '莱比锡', 'Leipzig', 'Sachsen', []),
        ('freiburg', '弗赖堡', 'Freiburg im Breisgau', 'Baden-Württemberg', ['freiburg']),
        ('frankfurt-oder', '法兰克福（奥得河畔）', 'Frankfurt (Oder)', 'Brandenburg', ['frankfurt']),
    ]
]
SCENARIOS = {
    'stable': dict(warmth_indicator_level=4, headline='建议带适中厚度的夹克，里面备一件薄毛衣',
                   packing_variation_notice=None, packing_variation_summary=None, reference_temperature_c=14),
    'colder': dict(warmth_indicator_level=2, headline='通常轻薄即可，另备一件适中厚度的外套',
                   packing_variation_notice='假设第2天明显偏冷，建议额外备一件适中外套或可叠穿的保暖层；其他日子轻薄即可。',
                   packing_variation_summary='有一天偏冷，建议多备一件外套或保暖层。', reference_temperature_c=24),
    'warmer': dict(warmth_indicator_level=4, headline='通常穿适中厚度的外套，内搭方便减薄',
                   packing_variation_notice='假设第2天明显偏暖，内搭可以更轻薄，外套要方便脱下；其他日子仍需适中保暖。',
                   packing_variation_summary='有一天偏暖，内搭轻薄、外套方便脱下。', reference_temperature_c=14),
    'split': dict(warmth_indicator_level=None, headline='轻薄与适中保暖都要准备，衣物方便增减',
                  packing_variation_notice='假设七天轻薄、七天需要适中保暖，没有单一穿法适合多数日子；请备轻薄内搭和可叠穿的外套。',
                  packing_variation_summary='冷热分化明显，请备轻薄内搭和可叠穿外套。', reference_temperature_c=None),
}
DEFAULTS = ['colder', 'stable', 'warmer', 'split'] + ['stable'] * 6


def now_berlin():
    return datetime.now(BERLIN)


def window(now=None):
    today = (now or now_berlin()).astimezone(BERLIN).date()
    return dict(today=today.isoformat(), forecast_end=(today + timedelta(days=13)).isoformat(),
                max_date=(today + timedelta(days=29)).isoformat())


def validate(params, now=None):
    """Canonical input boundary shared by fixture API and future service adapter."""
    w = window(now)
    city = next((c for c in CITIES if c['id'] == params.get('city_id')), None)
    if city is None:
        raise ValueError('请选择列表中的德国城市；当前为有限城市演示目录。')
    view = params.get('view', 'trip')
    if view == 'city':
        if city not in CITIES[:10]:
            raise ValueError('该城市不在精选城市列表中，请按行程查询。')
        return dict(city=city, start=w['today'], end=w['forecast_end'], preference='normal', view=view)
    if view != 'trip' or params.get('preference') not in ('cold', 'normal', 'hot'):
        raise ValueError('查询入口或体感参数无效。')
    from datetime import date
    try:
        start, end = params['start'], params['end']
        if date.fromisoformat(start).isoformat() != start or date.fromisoformat(end).isoformat() != end:
            raise ValueError()
        if not w['today'] <= start <= end <= w['max_date']:
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError('请选择德国今天起30天内的有效日期，离开日期不能早于到达日期。')
    return dict(city=city, start=start, end=end, preference=params['preference'], view=view)


def advice(params, scenario='default', now=None):
    now = now or now_berlin()
    p = validate(params, now)
    index = CITIES.index(p['city'])
    selected = DEFAULTS[index] if scenario == 'default' and index < 10 else ('stable' if scenario == 'default' else scenario)
    if selected not in (*SCENARIOS, 'stale', 'unavailable', 'loading'):
        raise ValueError('未知模拟场景。')
    if selected in ('unavailable', 'loading'):
        raise LookupError('暂时无法获取气温数据，请稍后重试。当前为模拟失败，没有真实天气服务。')
    from datetime import date
    days = (date.fromisoformat(p['end']) - date.fromisoformat(p['start'])).days + 1
    historical = p['end'] > window(now)['forecast_end']
    required_days = 14 if selected == 'split' else 3 if selected in ('colder', 'warmer') else 1
    if not historical and days < required_days:
        if scenario == 'default':
            selected = 'stable'
        else:
            raise ValueError('此模拟场景需要至少%d天，请修改行程或选择其他场景。' % required_days)
    data = deepcopy(SCENARIOS.get(selected, SCENARIOS['stable']))
    # Authored copy variants, not a clothing engine or a temperature threshold.
    layers = {'normal': '里面搭配长袖和薄毛衣，方便在室内脱下外套。',
              'cold': '怕冷示例：里面备长袖和抓绒，冷时再加一层。',
              'hot': '怕热示例：内搭选轻薄长袖，外套方便脱下。'}
    if historical:
        data.update(warmth_indicator_level=4, headline='提前备一件适中外套和可叠穿的薄毛衣',
                    packing_variation_notice=None, packing_variation_summary=None,
                    reference_temperature_c=14)
    data.update(p, mode='historical_reference' if historical else 'forecast', layers=layers[p['preference']],
                notices=['早晚示例：可随身带一层，按实际体感增减。'],
                source='人工编写的 UI fixtures，非 Open-Meteo 数据', weather_fetched_at=None,
                advice_generated_at=(now or now_berlin()).isoformat(timespec='seconds'),
                data_status='stale' if selected == 'stale' else 'fresh',
                fixture=True, fixture_scenario=selected, data_version='ui-fixtures-v1',
                caveat=('依据：过去五年同期气温（模拟）。这是提前备衣参考，不是旅行当天的天气预报。未查询历史数据。'
                        if historical else '演示数据，非真实天气。第8–14天的预报通常存在更大不确定性，出发前请复查；此处尚未接入天气服务。'))
    return data


def featured(scenario='default', now=None):
    now = now or now_berlin()
    w = window(now)
    return dict(**w, fixture=True, weather_fetched_at=None, data_version='ui-fixtures-v1',
                cities=[advice(dict(view='city', city_id=c['id']), scenario, now) for c in CITIES[:10]])
