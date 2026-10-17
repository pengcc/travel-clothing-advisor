"""Five complete annual samples, expressed as packing risk, never future dates."""
from datetime import date, datetime
from statistics import median

from web.fixtures import BERLIN
from web.live import INNER, OUTER, Unavailable, level, packing, public_city


def advise(library, city, p, now, clock, downloader=None, max_missing=0):
    days, edges, blocks = library.sample(city, date.fromisoformat(p['start']),
                                         date.fromisoformat(p['end']), downloader, max_missing)
    generated = clock().astimezone(BERLIN)
    if generated.date() != now.date() or generated < now:
        raise Unavailable('德国日期已变化，请重新查询。')
    main, variation, _ = packing(days)
    values = [v for _,v in days]
    cold, warm = level(min(values)), level(max(values))
    ref = round(median(values),1) if main is not None else None
    usual_coat = {**OUTER, 4: '建议带适中外套', 5: '建议带保暖夹克或轻羽绒', 6: '建议带冬季保暖外套'}
    headline = usual_coat[main] if main is not None else f'历史冷暖分化，冷时{OUTER[cold]}，暖时减薄'
    layers = INNER[main] if main is not None else f'较冷时：{INNER[cold]}较暖时：{INNER[warm]}'
    copy_events = []
    copy_boundary = False
    copy_boundary_note = False
    notice = summary = None
    if variation:
        copy_events = [dict(kind='cold', level=cold, when='历史同期'),
                       dict(kind='warm', level=warm, when='历史同期')]
        # Deliberately discard dated forecast copy, keep the shared packing decision.
        # Presentation-only garment copy: name cold outer and inner coverage once.
        cold_layers = {
            1: '搭配短袖和透气下装', 2: '搭配短袖或薄长袖',
            3: '搭配短袖或薄长袖', 4: '搭配长袖和薄毛衣',
            5: '搭配长袖、毛衣或抓绒', 6: '搭配保暖内搭、毛衣或抓绒',
        }
        warm_option = f'{usual_coat[warm]}，' if main is None or warm < main else ''
        notice = (f'过去五年同期曾出现较冷情况：{usual_coat[cold]}，{cold_layers[cold]}；'
                  f'较暖时{warm_option}内搭减薄、外层方便脱下。不是本次旅行预报。')
        summary = f'过去五年同期有冷暖差异，冷时{OUTER[cold]}，暖时减薄。'
    notes = []
    if ref is not None and main in (4,5) and abs(ref-13)<=0.75:
        copy_boundary_note = True
        # Boundary wording must not erase an observed colder packing requirement.
        if not (variation and cold > main):
            copy_boundary = True
            headline = '建议带保暖程度适中的外套；怕冷可用轻羽绒替代'
        notes.append('历史气温接近13°C厚度分界，长袖搭配薄毛衣或抓绒，按体感增减。')
    by_day = dict(days)
    cooler = [(d,v) for d,v in edges if by_day[d]-v > 1.5 and level(v)>level(by_day[d])]
    if cooler:
        _,v = min(cooler,key=lambda x:x[1])
        copy_events.append(dict(kind='edge', level=level(v), when='历史同期早晚'))
        notes.append(f'过去五年同期的早晚样本曾较凉：{OUTER[level(v)]}，外出可带可脱保暖层。')
    else:
        notes.append('过去五年同期早晚样本与白天保暖需求接近，按体感增减。')
    if p['preference'] == 'cold':
        layers += '怕冷：较凉时可多备一层薄长袖或薄毛衣。'
    elif p['preference'] == 'hot':
        layers += '怕热：内搭可减薄，中间层方便脱下。'
    from web.history import digest
    times = sorted({b['body']['fetched_at'] for b in blocks.values()},
                   key=lambda t: datetime.fromisoformat(t).timestamp())
    if any(datetime.fromisoformat(t)>generated for t in times):
        raise Unavailable('历史资料时间无效，请重试。')
    from web.advice_copy import packing_copy
    clipboard = packing_copy(main, copy_events, split=(cold, warm) if main is None else None, boundary=copy_boundary)
    if copy_boundary_note:
        clipboard['boundary'] = '接近13°C厚度分界，按体感增减中间层。'
    return dict(packing_copy=clipboard, city=public_city(city), start=p['start'], end=p['end'], preference=p['preference'],
                view='trip', mode='historical_reference', headline=headline, layers=layers,
                notices=notes, reference_temperature_c=ref, warmth_indicator_level=main,
                packing_variation_notice=notice, packing_variation_summary=summary,
                weather_fetched_at=times[0], history_fetched_at=times,
                advice_generated_at=generated.isoformat(timespec='seconds'),
                source='Open-Meteo Historical Weather API / ERA5（气温，CC BY 4.0，经衣物规则计算）；GeoNames（城市）',
                data_status='complete', data_version='era5-temp-v1-'+digest({m:b['sha256'] for m,b in blocks.items()}),
                caveat='过去五年同期气温参考，非这趟行程的预报。使用五段连续、等长的历史年度窗口；闰日前后月日可能近似偏移一天。历史冷暖仅为备衣范围，不能预测这次旅行具体哪天冷或暖。仅依据气温，未评估雨、雪、风或个人舒适度；出发前请复查预报。',
                fixture=False)
