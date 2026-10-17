"""Compact copy presentation of already-decided clothing levels/events; no weather rules."""

# Positive packable garments are separate from 'no coat needed' conclusions.
COAT_ITEMS = {3: '可脱的薄外套', 4: '适中外套', 5: '保暖夹克或轻羽绒', 6: '冬季保暖外套'}
COATS = {1: '不必带厚外套', 2: '不必带厚外套', **COAT_ITEMS}
INNERS = {
    1: ('短袖', '轻薄透气下装'), 2: ('短袖或薄长袖',),
    3: ('短袖或薄长袖',), 4: ('长袖', '薄毛衣'),
    5: ('长袖', '毛衣或抓绒'), 6: ('保暖内搭', '毛衣或抓绒'),
}


def covered(items):
    result = set(items)
    if '短袖或薄长袖' in result:
        result.update(('短袖', '薄长袖', '长袖'))
    return result


def extra_inners(lev, existing):
    extra = []
    for item in INNERS[lev]:
        if item in existing:
            continue
        # A short sleeve already packed leaves only the optional thin long sleeve.
        if item == '短袖或薄长袖' and '短袖' in existing:
            item = '薄长袖'
        if item not in existing:
            extra.append(item)
    return extra


def packing_copy(main, events, *, split=None, evening_only=False, boundary=False, preference='normal'):
    """Events carry the original trigger's level and date, never inferred here.

    Only suppress repeated garment names in the export, not an event or its timing.
    Split conditions retain both full outfits; later events refer to those outfits.
    """
    selected = list(split) if split else [main]
    required = selected + [event['level'] for event in events if event['kind'] != 'warm']
    coldest = max(required)
    alternative = ''
    if main == 5 and not split and not boundary and coldest < 6:
        alternative = '如果已有三合一外套加抓绒，且实际保暖能力适合预计活动，可替代主外套方案，不必再多带一套。'
    if preference == 'cold':
        if coldest >= 5:
            personal_layer = '怕冷可把已建议的中间层选厚一些，较冷时穿上，进入较暖室内可脱下外层。'
        elif coldest == 4:
            personal_layer = '怕冷可把已建议的薄毛衣换成较厚的中间层，较凉时穿、较暖室内脱下。'
        elif coldest <= 2:
            personal_layer = '怕冷可按体感选择薄长袖作为轻薄内搭。'
        else:
            personal_layer = '怕冷可随身备一层可脱的薄毛衣，较凉时再穿。'
    elif preference == 'hot':
        if coldest >= 4:
            coverage = ('已提醒的较冷时段仍需保留相应保暖覆盖。'
                        if any(event['kind'] in ('cold', 'edge') for event in events)
                        else '仍需保留上述保暖衣物，按体感增减。')
            personal_layer = '怕热可减薄中间层，进入较暖室内脱下外层；' + coverage
        else:
            personal_layer = '怕热可选更薄的内搭，外层方便脱下。'
    else:
        personal_layer = '按上述内搭准备，进入较暖室内可脱下外层，较冷时再穿上。' if coldest >= 3 else ''
    trousers_shoes = ''
    if coldest >= 4:
        lower = '较冷时需保暖下装覆盖，按体感选择保暖裤。' if coldest == 6 else ('怕冷可按体感备保暖裤。' if preference == 'cold' else '较冷时可按体感备保暖裤。')
        trousers_shoes = '普通长裤、适合步行的鞋；' + lower + '如另查预报提示雨雪，再考虑防水鞋；如有结冰风险注意防滑。'
    guidance = dict(alternative=alternative, personal_layer=personal_layer, trousers_shoes=trousers_shoes)
    covered_coats, covered_inners = set(), set()
    if split:
        cold, warm = split
        outer = f'冷时：{COATS[cold]}；暖时：{COATS[warm]}' if COATS[cold] != COATS[warm] else COATS[cold]
        cold_inner = '、'.join(INNERS[cold])
        warm_inner = '、'.join(INNERS[warm])
        inner = f'冷时：{cold_inner}；暖时：{warm_inner}' if cold_inner != warm_inner else cold_inner
        covered_coats.update(COAT_ITEMS[lev] for lev in (cold, warm) if lev in COAT_ITEMS)
        covered_inners.update(covered((*INNERS[cold], *INNERS[warm])))
        title = '分情况准备'
    else:
        outer, inner = COATS[main], '、'.join(INNERS[main])
        if main in COAT_ITEMS:
            covered_coats.add(COAT_ITEMS[main])
        covered_inners.update(covered(INNERS[main]))
        title = '剩余晚间准备' if evening_only else '通常准备'
    if boundary:
        # Preserve the existing near-13°C outerwear alternative without repeating layers.
        outer = '保暖程度适中的外套；怕冷可用轻羽绒替代'
    risks = []
    for event in events:
        when, kind, lev = event['when'], event['kind'], event['level']
        if kind == 'warm':
            extra = extra_inners(lev, covered_inners)
            action = '可换' + '、'.join(extra) + '，' if extra else ''
            risks.append(f'{when}偏暖：{action}减薄内搭、脱下外层。')
            covered_inners.update(covered(extra))
            continue
        coat_item = COAT_ITEMS.get(lev)
        extra_coat = coat_item if coat_item not in covered_coats else None
        extra_inner = extra_inners(lev, covered_inners)
        garments = ([extra_coat] if extra_coat else []) + extra_inner
        if garments:
            action = '另备' + '、'.join(garments)
        elif lev in COAT_ITEMS:
            action = '外出带上已备的保暖层'
        else:
            action = '可加已备的薄长袖' if '薄长袖' in covered_inners else '按上述轻薄衣物准备'
        risks.append(f'{when}{"较凉" if kind == "edge" else "偏冷"}：{action}。')
        if coat_item:
            covered_coats.add(coat_item)
        covered_inners.update(covered(extra_inner))
    return dict(title=title, outer=outer, inner=inner, risks=risks, guidance=guidance,
                boundary='接近13°C厚度分界，按体感增减中间层。' if boundary else None)
