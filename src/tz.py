"""Timezone offset helper — MicroPython has no tzdata, so compute it.

open-meteo timezone names like "Europe/Warsaw" all follow the EU rule:
UTC+2 (summer) from the last Sunday of March 01:00 UTC until the last Sunday
of October 01:00 UTC, else UTC+1. Anything else falls back to UTC (0).
Pure integer math, no imports — safe on the board and in the host sim.
"""


def _days_from_civil(y, m, d):
    """Days since 1970-01-01 for a civil date (Howard Hinnant's algorithm)."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _civil_from_days(z):
    """(y, m, d) for days since 1970-01-01."""
    z += 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    return y + (m <= 2), m, d


def _last_sunday_epoch(year, month):
    """Epoch (00:00 UTC) of the last Sunday of the given month."""
    if month == 12:
        nxt = _days_from_civil(year + 1, 1, 1)
    else:
        nxt = _days_from_civil(year, month + 1, 1)
    day = nxt - 1  # day number of the month's last day
    while (day + 4) % 7 != 0:  # 1970-01-01 was a Thursday; (day+4)%7==0 is Sunday
        day -= 1
    return day * 86400


def utc_offset(tz, epoch):
    """Seconds east of UTC for an open-meteo timezone name at `epoch` (UTC)."""
    if not tz.startswith("Europe/"):
        return 0
    year = _civil_from_days(epoch // 86400)[0]
    start = _last_sunday_epoch(year, 3) + 3600   # last Sun of March, 01:00 UTC
    end = _last_sunday_epoch(year, 10) + 3600    # last Sun of October, 01:00 UTC
    if start <= epoch < end:
        return 7200
    return 3600
