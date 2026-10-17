"""Compact copy presentation of already-decided clothing levels/events; no weather rules."""

COATS = {
    1: '不必带厚外套', 2: '不必带厚外套', 3: '可脱的薄外套',
    4: '适中外套', 5: '保暖夹克或轻羽绒', 6: '冬季保暖外套',
}
INNERS = {
    1: ('短袖', '轻薄透气下装'), 2: ('短袖或薄长袖',),
    3: ('短袖或薄长袖',), 4: ('长袖', '薄毛衣'),
    5: ('长袖', '毛衣或抓绒'), 6: ('保暖内搭', '毛衣或抓绒'),
}


def covered(items):
    result = set(items)
    if '短袖或薄长袖' in result:
        result.update(('短袖', '长袖'))
    return result


def packing_copy(main, events, *, split=None, evening_only=False, boundary=False):
    """Events carry the original trigger's level and date, never inferred here.

    Only suppress repeated garment names in the export, not an event or its timing.
    Split conditions retain both full outfits; later events refer to those outfits.
    """
    covered_coats, covered_inners = set(), set()
    if split:
        cold, warm = split
        outer = f'冷时：{COATS[cold]}；暖时：{COATS[warm]}' if COATS[cold] != COATS[warm] else COATS[cold]
        cold_inner = '、'.join(INNERS[cold])
        warm_inner = '、'.join(INNERS[warm])
        inner = f'冷时：{cold_inner}；暖时：{warm_inner}' if cold_inner != warm_inner else cold_inner
        covered_coats.update((cold, warm))
        covered_inners.update(covered((*INNERS[cold], *INNERS[warm])))
        title = '分情况准备'
    else:
        outer, inner = COATS[main], '、'.join(INNERS[main])
        covered_coats.add(main)
        covered_inners.update(covered(INNERS[main]))
        title = '剩余晚间准备' if evening_only else '通常准备'
    if boundary:
        # Preserve the existing near-13°C outerwear alternative without repeating layers.
        outer = '保暖程度适中的外套；怕冷可用轻羽绒替代'
    risks = []
    for event in events:
        when, kind, lev = event['when'], event['kind'], event['level']
        if kind == 'warm':
            extra = [item for item in INNERS[lev] if item not in covered_inners]
            action = '可换' + '、'.join(extra) + '，' if extra else ''
            risks.append(f'{when}偏暖：{action}减薄内搭、脱下外层。')
            covered_inners.update(covered(extra))
            continue
        extra_coat = COATS[lev] if lev not in covered_coats else None
        extra_inner = [item for item in INNERS[lev] if item not in covered_inners]
        garments = ([extra_coat] if extra_coat else []) + extra_inner
        action = '另备' + '、'.join(garments) if garments else '外出带上已备的保暖层'
        risks.append(f'{when}{"较凉" if kind == "edge" else "偏冷"}：{action}。')
        covered_coats.add(lev)
        covered_inners.update(covered(extra_inner))
    return dict(title=title, outer=outer, inner=inner, risks=risks,
                boundary='接近13°C厚度分界，按体感增减中间层。' if boundary else None)
