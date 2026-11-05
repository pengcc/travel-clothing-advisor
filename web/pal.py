"""穿衣小伙伴 data: pure, temperature-only, no IO. See Issue #101 (Plan v4.2)."""
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
from statistics import median

from web.fixtures import BERLIN
from web.live import level, parse_hours, public_city

# Same windows as forecast_advice: morning 6–8, midday 9–18, evening 19–22.
SLOTS = (('morning', '06–08', '07:00', 6, 8),
         ('midday', '09–18', '13:00', 9, 18),
         ('evening', '19–22', '20:00', 19, 22))
CAVEAT = '仅依据气温，未评估雨、雪、风；与主页同一套冷热档位，未针对儿童调校。'


def display_temperature(value):
    """Integer for display with level(result) == level(value), always."""
    rounded = int(Decimal(repr(float(value))).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return rounded if level(rounded) == level(value) else math.floor(value)


def _slot(spec, hours, day, generated):
    name, window, label, low, high = spec
    inside = [(d, v) for d, v in hours if d.date() == day and low <= d.hour <= high]
    left = [v for d, v in inside if d >= generated]
    base = dict(slot=name, window=window, label_time=label)
    if not left:
        return dict(base, temperature_c=None, level=None, past=True, partial=False)
    middle = median(left)
    return dict(base, temperature_c=display_temperature(middle), level=level(middle),
                past=False, partial=len(left) < len(inside))


def build(city, cached, now, generated):
    """cached = (hourly provider data, acquired, version) of one snapshot.

    The snapshot is anchored on its own Berlin day; only `generated` (the
    clock) decides which hours are already past.
    """
    data, acquired, version = cached
    snapshot_day = acquired.astimezone(BERLIN).date()
    hours = parse_hours(data, datetime.combine(snapshot_day, time(), BERLIN))
    today = now.astimezone(BERLIN).date()
    days = []
    for n in range(7):
        day = today + timedelta(days=n)
        slots = [_slot(spec, hours, day, generated) for spec in SLOTS]
        levels = [s['level'] for s in slots if s['level'] is not None]
        days.append(dict(date=day.isoformat(), slots=slots,
                         swing='large' if levels and max(levels) - min(levels) >= 2 else 'none'))
    return dict(city=public_city(city), days=days, fixture=False,
                stale=snapshot_day != today,
                weather_fetched_at=acquired.isoformat(timespec='seconds'),
                advice_generated_at=generated.isoformat(timespec='seconds'),
                data_version='temperature-v1-' + version, caveat=CAVEAT)
