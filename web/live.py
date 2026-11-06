"""Local temperature-only adapter. Provider JSON and clock are injectable; no CLI IO."""
from collections import Counter
from datetime import date, datetime, time, timedelta
import importlib.util
import json
import math
from pathlib import Path
from statistics import median
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from web.fixtures import BERLIN, CITIES, window

_spec = importlib.util.spec_from_file_location('clothing_core', Path(__file__).parents[1] / 'experiments/clothing-rules/validate_clothing_rules.py')
_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_core)
level = _core.level
GEO = 'https://geocoding-api.open-meteo.com/v1/'
FORECAST = 'https://api.open-meteo.com/v1/forecast'
IDS = {
    'berlin': 2950159, 'munich': 2867714, 'hamburg': 2911298,
    'frankfurt': 2925533, 'cologne': 2886242, 'dresden': 2935022,
    'heidelberg': 2907911, 'nuremberg': 2861650, 'dusseldorf': 2934246,
    'leipzig': 2879139, 'freiburg': 2925177, 'frankfurt-oder': 2925535,
    'stuttgart': 2825297, 'hannover': 2910831, 'bremen': 2944388, 'bonn': 2946447,
    'potsdam': 2852458, 'wurzburg': 2805615, 'regensburg': 2849483, 'lubeck': 2875601,
    'garmisch-partenkirchen': 2922530,
}
OUTER = {1:'穿轻薄透气衣物，无需厚外套', 2:'轻薄即可，不必带厚外套', 3:'建议带一件方便脱下的薄外套', 4:'建议带适中外套，里面可叠穿薄毛衣', 5:'建议带保暖夹克或轻羽绒，可叠穿抓绒', 6:'建议带冬季保暖外套和保暖内搭'}

INNER = {
    1: '短袖和轻薄透气下装为主。',
    2: '短袖或薄长袖为主，方便增减。',
    3: '短袖或薄长袖，搭配可脱的薄外套。',
    4: '长袖搭配薄毛衣，进室内可脱外层。',
    5: '长袖搭配毛衣或抓绒，保暖外套方便脱下。',
    6: '保暖内搭搭配毛衣或抓绒，外出加冬季外套。',
}


class Unavailable(LookupError):
    code = "temporarily_unavailable"


class HistoryIncomplete(Unavailable):
    code = "history_incomplete"


def fetch_json(url, params):
    try:
        with urlopen(url + '?' + urlencode(params), timeout=8) as response:
            data = json.load(response)
        if not isinstance(data, dict) or data.get('error'):
            raise Unavailable('上游数据无效，暂时无法生成建议。')
        return data
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise Unavailable('天气或城市服务暂不可用，请稍后重试。') from exc


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def location(raw):
    if not isinstance(raw, dict) or raw.get('country_code') != 'DE' or not str(raw.get('feature_code', '')).startswith('P'):
        raise ValueError('请选择可确认的德国城市。')
    if type(raw.get('id')) is not int or raw['id'] <= 0 or not isinstance(raw.get('name'), str) or not raw['name'] or not isinstance(raw.get('admin1'), str) or not raw['admin1']:
        raise Unavailable('城市资料不完整，请重试。')
    if not all(number(raw.get(k)) for k in ('latitude','longitude')) or not (-90 <= raw['latitude'] <= 90 and -180 <= raw['longitude'] <= 180):
        raise Unavailable('城市坐标不可用。')
    alias = next((c for c in CITIES if IDS[c['id']] == raw['id']), None)
    return dict(id=alias['id'] if alias else str(raw['id']), zh=alias['zh'] if alias else raw['name'], name=raw['name'], state=raw['admin1'], latitude=raw['latitude'], longitude=raw['longitude'])


def public_city(city):
    return {k:v for k,v in city.items() if k not in ('latitude','longitude')}


def parse_hours(data, now):
    """Validate original order before indexing; UTC instants handle both DST folds."""
    try:
        if not isinstance(data, dict) or data.get('error') or data.get('timezone') != 'Europe/Berlin' or not isinstance(data.get('hourly_units'), dict) or not isinstance(data.get('hourly'), dict) or data['hourly_units'].get('temperature_2m') != '°C':
            raise ValueError()
        times, temps = data['hourly']['time'], data['hourly']['temperature_2m']
        if not isinstance(times, list) or not isinstance(temps, list) or not times or len(times) != len(temps):
            raise ValueError()
        if any(type(t) is not int or t % 3600 for t in times) or any(b-a != 3600 for a,b in zip(times, times[1:])):
            raise ValueError()
        if any(not number(t) or not -90 <= t <= 65 for t in temps):
            raise ValueError()
        hours = [(datetime.fromtimestamp(t, BERLIN), v) for t,v in zip(times,temps)]
        today = now.date()
        midnight = datetime.combine(today, time(), BERLIN)
        evening = datetime.combine(today, time(23), BERLIN)
        # Open-Meteo fixes daily boundaries to the request-time UTC offset.
        # After a DST change the first epoch is autumn 01:00 or spring's
        # preceding-day 23:00 in Berlin. Required 06–22 coverage is checked below.
        fixed_offset_start = midnight.timestamp() + (midnight.utcoffset() - evening.utcoffset()).total_seconds()
        valid_starts = {int(midnight.timestamp()), int(fixed_offset_start)}
        if times[0] not in valid_starts or hours[-1][0].date() < today + timedelta(days=13):
            raise ValueError()
        indexed = dict(zip(times, temps))
        # Require all daytime and edge hours, including elapsed hours in stored sources.
        for n in range(14):
            day = today + timedelta(days=n)
            for h in range(6,23):
                instant = datetime.combine(day, time(h), BERLIN)
                if int(instant.timestamp()) not in indexed:
                    raise ValueError()
        return hours
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise Unavailable('气温数据不完整、日期已过期或时区无效，暂不提供穿衣建议。') from exc


def packing(days, presentation_events=None):
    """Modal observed level, independent range test; suppress <=1.5°C boundary noise."""
    events = presentation_events if presentation_events is not None else []
    values = [v for _,v in days]
    levels = [level(v) for v in values]
    counts = Counter(levels)
    main, count = counts.most_common(1)[0]
    meaningful = max(levels) != min(levels) and max(values)-min(values) > 1.5
    if count <= len(days)/2 and meaningful:
        main = None
    notice = summary = None
    if meaningful:
        if main is None:
            coldest, warmest = max(levels), min(levels)
            notice = (f'{days[values.index(min(values))][0]}较冷：{OUTER[coldest]}；'
                      f'{days[values.index(max(values))][0]}较暖：{OUTER[warmest]}，按当天增减。')
            events.extend([dict(kind='cold', level=coldest, when=days[values.index(min(values))][0]),
                           dict(kind='warm', level=warmest, when=days[values.index(max(values))][0])])
            summary = f'冷暖分化，冷时{OUTER[coldest]}，暖时减薄。'
        else:
            colder = [(d,v) for d,v in days if level(v)>main and median(values)-v>1.5]
            warmer = [(d,v) for d,v in days if level(v)<main and v-median(values)>1.5]
            parts = []
            if colder:
                d,v = min(colder, key=lambda x:x[1])
                when = f'{d}等{len(colder)}天' if len(colder)>1 else d
                events.append(dict(kind='cold', level=level(v), when=when))
                parts.append(f'{when}偏冷：{OUTER[level(v)]}，按时段增减保暖层')
            if warmer:
                d,v = max(warmer, key=lambda x:x[1])
                when = f'{d}等{len(warmer)}天' if len(warmer)>1 else d
                events.append(dict(kind='warm', level=level(v), when=when))
                parts.append(f'{when}偏暖：内搭轻薄、外套方便脱下')
            notice = '；'.join(parts) + '。' if parts else None
            summary = ('有冷暖变化，备轻薄内搭和可增减保暖层。' if colder and warmer else '有偏冷日，另备外套或可叠穿保暖层。' if colder else '有偏暖日，内搭轻薄、外套方便脱下。') if parts else None
    return main, notice, summary


def variation_kind(events):
    """Presentation direction of the existing significant cross-day packing events."""
    kinds = {event['kind'] for event in events if event['kind'] in ('cold', 'warm')}
    return 'mixed' if len(kinds) == 2 else next(iter(kinds), None)


class Service:
    def __init__(self, fetch=fetch_json, clock=lambda: datetime.now(BERLIN), *, history=None, history_downloader=None, history_max_missing=0, forecast_cache=None, trusted_records=None, independent_cities=True, featured_records=None):
        self.featured_cities = {location(r)["id"]: location(r) for r in (featured_records or [])}
        self.independent_cities = independent_cities
        self.fetch, self.clock = fetch, clock
        self.offline_cities = None
        if trusted_records is not None:
            cities = [location(record) for record in trusted_records]
            if len({c['id'] for c in cities}) != len(cities):
                raise ValueError('Duplicate trusted city')
            self.offline_cities = {c['id']: c for c in cities}
        self.history = history
        self.history_downloader = history_downloader
        self.history_max_missing = history_max_missing
        from web.forecasts import Cache, MemoryStore
        self.forecasts = forecast_cache if forecast_cache is not None else Cache(MemoryStore(), clock)

    def get(self, url, params):
        try:
            data = self.fetch(url, params)
            if not isinstance(data, dict) or data.get('error'):
                raise Unavailable('上游响应无效，请稍后重试。')
            return data
        except (TimeoutError, OSError, ValueError) as exc:
            raise Unavailable('天气或城市服务暂不可用，请稍后重试。') from exc

    def resolve(self, city_id):
        provider_id = IDS.get(city_id, city_id)
        if not isinstance(provider_id, int) and (not isinstance(provider_id,str) or not provider_id.isascii() or not provider_id.isdigit() or len(provider_id)>10):
            raise ValueError('请选择列表中的德国城市。')
        if self.offline_cities is not None:
            city = next((c for c in self.offline_cities.values()
                         if str(IDS.get(c['id'], c['id'])) == str(provider_id)), None)
            if city is None:
                raise Unavailable('这个城市不在已准备的城市范围内，暂不可用。')
            return dict(city)
        raw = self.get(GEO+'get', dict(id=provider_id))
        city = location(raw)
        if raw['id'] != int(provider_id):
            raise Unavailable('城市标识不匹配。')
        return city

    def cities(self, q):
        if self.offline_cities is not None:
            if len(q) > 100:
                raise ValueError('城市搜索文字过长。')
            def matches(city):
                alias = next((c for c in CITIES if c['id'] == city['id']), {})
                return any(q.casefold() in str(v).casefold() for v in
                           [city['id'], city['zh'], city['name'], *alias.get('aliases', [])])
            return dict(cities=[public_city(c) for c in self.offline_cities.values() if matches(c)],
                        fixture=False, source='Open-Meteo / GeoNames（预先验证的离线城市）')
        if not q:
            return dict(cities=[public_city(c) for c in CITIES], fixture=False)
        if len(q)>100:
            raise ValueError('城市搜索文字过长。')
        matches = [c for c in CITIES if q.casefold() in [c['zh'].casefold(), c['id'], *[a.casefold() for a in c['aliases']]]]
        query = matches[0]['name'] if len(matches)==1 else q
        raw = self.get(GEO+'search', dict(name=query, count=100, language='de', countryCode='DE'))
        results = raw.get('results', [])
        if not isinstance(results, list):
            raise Unavailable('城市服务响应不完整。')
        cities = {}
        for item in results:
            try:
                c = location(item)
                cities[c['id']] = public_city(c)
            except (ValueError, Unavailable):
                # A bad candidate must not discard other validated locations.
                continue
        if results and not cities:
            raise Unavailable('城市搜索结果缺少可用的德国城市资料，请换个名称重试。')
        return dict(cities=list(cities.values()), fixture=False, source='Open-Meteo / GeoNames')

    def featured(self):
        return self.city_references() if self.independent_cities else self.forecasts.featured(self)

    def city_advice(self, p):
        if not p.get('city_id') or set(p) - {'view', 'city_id', 'start', 'end', 'preference'}:
            raise ValueError('查询参数无效。')
        return self.city_references(p.get('city_id')) if self.independent_cities else self.forecasts.featured(self, p.get('city_id'))

    def _city_record(self, city_id, now):
        """Validated city metadata without downloads (shared by city_references and pal)."""
        # Offline metadata is validated at dataset loading. Local workers
        # can also leave validated city metadata in the daily manifest.
        city = (self.offline_cities or self.featured_cities).get(city_id)
        if city is None and self.offline_cities is None:
            from web.forecasts import manifest_key, unpack
            body = unpack(self.forecasts.store.get(manifest_key(now.date())))
            city = next(e['city'] for e in body['entries'] if e['city']['id'] == city_id)
        if city is None:
            raise Unavailable('城市资料暂缺。')
        return city

    def pal(self, city_id='berlin'):
        """穿衣小伙伴: latest usable snapshot of one featured city, read-only; never downloads."""
        from web.forecasts import FEATURED
        if city_id not in FEATURED:
            raise ValueError('请选择列表中的精选城市。')
        if not self.independent_cities:
            raise Unavailable('此部署模式暂不提供穿衣小伙伴。')
        from web.pal import build
        try:
            now = self.clock().astimezone(BERLIN)
            city = self._city_record(city_id, now)
            cached = None
            # Local worker mode (no offline_cities) only supports today's snapshot.
            for back in range(3 if self.offline_cities is not None else 1):
                cached = self.forecasts.read_snapshot(city, now.date() - timedelta(days=back))
                if cached is not None:
                    break
            if cached is None or now - cached[1] > timedelta(hours=48):
                raise Unavailable('穿衣小伙伴暂时没有可用的预报数据。')
            generated = self.clock().astimezone(BERLIN)
            if generated.date() != now.date() or generated < cached[1]:
                raise Unavailable('数据日期已变化，请重新查询。')
            return build(city, cached, now, generated)
        except Unavailable:
            raise
        except (OSError, ValueError, KeyError, TypeError, StopIteration, OverflowError) as exc:
            raise Unavailable('穿衣小伙伴暂时没有可用的预报数据。') from exc

    def city_references(self, city_id=None):
        """Independent read-only city results; never download on the homepage."""
        from web.forecasts import FEATURED
        if city_id is not None and city_id not in FEATURED:
            raise ValueError('该城市不在精选城市列表中。')
        now = self.clock().astimezone(BERLIN)
        w = window(now)
        results = []
        for catalog in CITIES[:10]:
            if city_id is not None and catalog['id'] != city_id:
                continue
            p = dict(view='city', start=w['today'], end=w['forecast_end'], preference='normal')
            result = None
            try:
                city = self._city_record(catalog['id'], now)
                try:
                    result = self.forecasts.render(self, city, now, self.forecasts.read(city, now.date()))
                except (Unavailable, OSError, ValueError, KeyError, TypeError):
                    if self.history is not None:
                        from web.historical_advice import advise
                        result = advise(self.history, city, p, now, self.clock)
                        result['view'] = 'city'
            except (Unavailable, OSError, ValueError, KeyError, TypeError, StopIteration):
                pass
            if result is None:
                result = dict(city=public_city(catalog), **p, mode='unavailable',
                              data_status='unavailable', headline='数据暂缺',
                              warmth_indicator_level=None, fixture=False)
            results.append(result)
        self.forecasts.current(now.date())
        if city_id is not None:
            if results[0]['mode'] == 'unavailable':
                raise Unavailable('数据暂缺')
            return results[0]
        return dict(**w, fixture=False, data_status='fresh', cities=results)

    def advice(self, p):
        if set(p) - {'view','city_id','start','end','preference'} or p.get('view','trip') != 'trip' or p.get('preference') not in ('cold','normal','hot'):
            raise ValueError('查询参数或体感无效。')
        now = self.clock().astimezone(BERLIN)
        w = window(now)
        try:
            start, end = p['start'], p['end']
            if date.fromisoformat(start).isoformat()!=start or date.fromisoformat(end).isoformat()!=end or not w['today']<=start<=end<=w['max_date']:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ValueError('请选择德国今天起30天内的有效日期，离开日期不能早于到达日期。')
        if end>w['forecast_end']:
            if self.history is None:
                raise HistoryIncomplete('这个查询的过去五年同期历史资料尚未齐备，暂不提供穿衣建议。')
            from web.historical_advice import advise
            city = self.resolve(p.get('city_id'))
            return advise(self.history, city, p, now, self.clock, self.history_downloader, self.history_max_missing)
        city = self.resolve(p.get('city_id'))
        try:
            cached = self.forecasts.obtain(city, now, self.fetch)
            return self.forecast_advice(city, p, now, cached)
        except Unavailable:
            # Managed whole-publication readers retain their operational errors;
            # only independent city/local readers fall back to historical advice.
            if not self.independent_cities or self.history is None:
                raise
            from web.historical_advice import advise
            return advise(self.history, city, p, now, self.clock,
                          self.history_downloader, self.history_max_missing)

    def forecast_advice(self, city, p, now, cached, *, generated=None):
        """Same packing path for personal ranges and read-only featured views."""
        start, end = p['start'], p['end']
        w = window(now)
        data, acquired, version = cached
        generated = generated or self.clock().astimezone(BERLIN)
        if generated.date()!=now.date() or generated<acquired:
            raise Unavailable('数据日期已变化，请重新查询。')
        hours = [(d,v) for d,v in parse_hours(data, generated) if start<=d.date().isoformat()<=end and d>=generated]
        days = []
        edges = []
        for n in range((date.fromisoformat(end)-date.fromisoformat(start)).days+1):
            day = date.fromisoformat(start)+timedelta(days=n)
            daytime = [v for d,v in hours if d.date()==day and 9<=d.hour<=18]
            edges.extend((d,v) for d,v in hours if d.date()==day and (6<=d.hour<=8 or 19<=d.hour<=22))
            if daytime:
                days.append((day.isoformat(), median(daytime)))
        if not days and not edges:
            raise Unavailable('今天可用的白天及早晚时段均已过去，请选择明天起的日期。')
        copy_events = []
        main, notice, summary = packing(days, copy_events) if days else (None,None,None)
        # Classify only cross-day packing events, before independent morning/evening notes.
        notice_kind = variation_kind(copy_events) if summary else None
        copy_split = (level(min(v for _,v in days)), level(max(v for _,v in days))) if days and main is None else None
        copy_level = main if days else level(min(v for _,v in edges))
        copy_boundary = False
        ref = round(median(v for _,v in days),1) if days and main is not None else None
        span = [round(min(v for _,v in days)), round(max(v for _,v in days))] if days else None
        if main is not None:
            headline = OUTER[main]
        elif days:
            headline = f'冷热分化，冷时{OUTER[level(min(v for _,v in days))]}，暖时减薄'
        else:
            headline = '今天白天已过，仅参考剩余晚间时段备衣'
        notes = []
        if ref is not None and main in (4,5) and abs(ref-13)<=0.75:
            copy_boundary = True
            headline = '建议带保暖程度适中的外套；怕冷可用轻羽绒替代'
            notes.append('气温接近13°C厚度分界，长袖搭配薄毛衣或抓绒，按体感增减。')
        if edges:
            by_day = dict(days)
            cooler = [(d,v) for d,v in edges if d.date().isoformat() not in by_day or
                      (by_day[d.date().isoformat()]-v>1.5 and level(v)>level(by_day[d.date().isoformat()]))]
            if cooler:
                d,v = min(cooler,key=lambda x:x[1])
                copy_events.append(dict(kind='edge', level=level(v), when=f'{d:%m月%d日 %H时}前后'))
                notes.append(f'{d:%m月%d日 %H时}前后较凉：{OUTER[level(v)]}，外出可随身携带。')
            else:
                notes.append('有效早晚时段与当天白天保暖需求接近，按实际体感增减。')
        if start==w['today']:
            notes.append('今天仅使用查询时刻之后的小时；已过去的时段不计入建议。')
        if main is None and days:
            # Packing coverage uses observed extremes, not a representative level.
            coldest = level(min(v for _,v in days))
            warmest = level(max(v for _,v in days))
            layers = f'较冷时：{INNER[coldest]}较暖时：{INNER[warmest]}'
        else:
            layers = INNER[main if days else level(min(v for _,v in edges))]
        caveat = '仅依据气温的备衣参考，未评估雨、雪、风或个人舒适度；出发前请复查。'
        if end> (now.date()+timedelta(days=6)).isoformat():
            caveat += '第8–14天预报不确定性更大，偏冷偏暖日期也可能改变。'
        from web.advice_copy import packing_copy
        clipboard = packing_copy(copy_level, copy_events, split=copy_split, evening_only=not days, boundary=copy_boundary, preference=p['preference'])
        return dict(packing_copy=clipboard, city=public_city(city), start=start, end=end, preference=p['preference'], view=p.get('view', 'trip'), mode='forecast', headline=headline, layers=layers, notices=notes, reference_temperature_c=ref, daytime_temperature_range_c=span, warmth_indicator_level=main, packing_variation_notice=notice, packing_variation_summary=summary, packing_variation_kind=notice_kind, weather_fetched_at=acquired.isoformat(timespec='seconds'), advice_generated_at=generated.isoformat(timespec='seconds'), source='Open-Meteo（气温预报）；GeoNames（城市）', data_status='fresh', data_version='temperature-v1-'+version, caveat=caveat, fixture=False)
