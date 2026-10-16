"""Local temperature-only adapter. Provider JSON and clock are injectable; no CLI IO."""
from collections import Counter
from datetime import date, datetime, time, timedelta
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from statistics import median
from threading import Lock
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
    pass


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
        if hours[0][0].date() != today or hours[0][0].hour != 0 or hours[-1][0].date() < today + timedelta(days=13):
            raise ValueError()
        indexed = dict(zip(times, temps))
        # Require every future daytime and edge hour throughout the whole forecast window.
        for n in range(14):
            day = today + timedelta(days=n)
            for h in range(6,23):
                instant = datetime.combine(day, time(h), BERLIN)
                if instant >= now and int(instant.timestamp()) not in indexed:
                    raise ValueError()
        return hours
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise Unavailable('气温数据不完整、日期已过期或时区无效，暂不提供穿衣建议。') from exc


def packing(days):
    """Modal observed level, independent range test; suppress <=1.5°C boundary noise."""
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
            summary = f'冷暖分化，冷时{OUTER[coldest]}，暖时减薄。'
        else:
            colder = [(d,v) for d,v in days if level(v)>main and median(values)-v>1.5]
            warmer = [(d,v) for d,v in days if level(v)<main and v-median(values)>1.5]
            parts = []
            if colder:
                d,v = min(colder, key=lambda x:x[1])
                when = f'{d}等{len(colder)}天' if len(colder)>1 else d
                parts.append(f'{when}偏冷：{OUTER[level(v)]}，按时段增减保暖层')
            if warmer:
                d,v = max(warmer, key=lambda x:x[1])
                when = f'{d}等{len(warmer)}天' if len(warmer)>1 else d
                parts.append(f'{when}偏暖：内搭轻薄、外套方便脱下')
            notice = '；'.join(parts) + '。' if parts else None
            summary = ('有冷暖变化，备轻薄内搭和可增减保暖层。' if colder and warmer else '有偏冷日，另备外套或可叠穿保暖层。' if colder else '有偏暖日，内搭轻薄、外套方便脱下。') if parts else None
    return main, notice, summary


class Service:
    def __init__(self, fetch=fetch_json, clock=lambda: datetime.now(BERLIN), *, history=None, history_downloader=None, history_max_missing=0):
        self.fetch, self.clock = fetch, clock
        self.history = history
        self.history_downloader = history_downloader
        self.history_max_missing = history_max_missing
        self.cache = {}
        self.lock = Lock()

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
        raw = self.get(GEO+'get', dict(id=provider_id))
        city = location(raw)
        if raw['id'] != int(provider_id):
            raise Unavailable('城市标识不匹配。')
        return city

    def cities(self, q):
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
                raise Unavailable('过去五年同期历史资料尚未齐备，暂不提供穿衣建议。')
            from web.historical_advice import advise
            city = self.resolve(p.get('city_id'))
            return advise(self.history, city, p, now, self.clock, self.history_downloader, self.history_max_missing)
        city = self.resolve(p.get('city_id'))
        key = (city['id'], w['today'])
        with self.lock:
            cached = self.cache.get(key)
            if cached is None:
                data = self.get(FORECAST, dict(latitude=city['latitude'], longitude=city['longitude'], hourly='temperature_2m', forecast_days=14, timezone='Europe/Berlin', timeformat='unixtime', temperature_unit='celsius'))
                acquired = self.clock().astimezone(BERLIN)
                if acquired.date()!=now.date():
                    raise Unavailable('德国日期已变化，请重新查询。')
                parse_hours(data, acquired)
                version = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
                cached = (data, acquired, version)
                if len(self.cache)>=32:
                    self.cache.clear()
                self.cache[key] = cached
        data, acquired, version = cached
        generated = self.clock().astimezone(BERLIN)
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
        main, notice, summary = packing(days) if days else (None,None,None)
        ref = round(median(v for _,v in days),1) if days and main is not None else None
        if main is not None:
            headline = OUTER[main]
        elif days:
            headline = f'冷热分化，冷时{OUTER[level(min(v for _,v in days))]}，暖时减薄'
        else:
            headline = '今天白天已过，仅参考剩余晚间时段备衣'
        notes = []
        if ref is not None and main in (4,5) and abs(ref-13)<=0.75:
            headline = '建议带保暖程度适中的外套；怕冷可用轻羽绒替代'
            notes.append('气温接近13°C厚度分界，长袖搭配薄毛衣或抓绒，按体感增减。')
        if edges:
            by_day = dict(days)
            cooler = [(d,v) for d,v in edges if d.date().isoformat() not in by_day or
                      (by_day[d.date().isoformat()]-v>1.5 and level(v)>level(by_day[d.date().isoformat()]))]
            if cooler:
                d,v = min(cooler,key=lambda x:x[1])
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
        if p['preference'] == 'cold':
            layers += '怕冷：较凉时可多备一层薄长袖或薄毛衣。'
        elif p['preference'] == 'hot':
            layers += '怕热：内搭可减薄，中间层方便脱下。'
        caveat = '仅依据气温的备衣参考，未评估雨、雪、风或个人舒适度；出发前请复查。'
        if end> (now.date()+timedelta(days=6)).isoformat():
            caveat += '第8–14天预报不确定性更大，偏冷偏暖日期也可能改变。'
        return dict(city=public_city(city), start=start, end=end, preference=p['preference'], view='trip', mode='forecast', headline=headline, layers=layers, notices=notes, reference_temperature_c=ref, warmth_indicator_level=main, packing_variation_notice=notice, packing_variation_summary=summary, weather_fetched_at=acquired.isoformat(timespec='seconds'), advice_generated_at=generated.isoformat(timespec='seconds'), source='Open-Meteo（气温预报）；GeoNames（城市）', data_status='fresh', data_version='temperature-v1-'+version, caveat=caveat, fixture=False)
