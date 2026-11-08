"""Small shared helpers: money/hours math, dates, names, findings."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path

ZERO = Decimal("0")
CENT = Decimal("0.01")

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def D(value, default=None):
    """Parse a number into Decimal. Accepts '$1,234.50', '(10.00)', '12%'."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip()
    if text == "" or text.lower() in {"none", "null", "n/a", "-"}:
        return default
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    text = text.replace("$", "").replace(",", "").replace("USD", "").strip()
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    if percent:
        number = number / Decimal(100)
    return -number if negative else number


def money(value) -> Decimal:
    return (D(value, ZERO)).quantize(CENT, rounding=ROUND_HALF_UP)


def hrs(value) -> Decimal:
    return (D(value, ZERO)).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(value) -> str:
    value = money(value)
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def parse_date(value, field="date"):
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            return _dt.datetime.strptime(text[:len(text)], fmt).date()
        except ValueError:
            continue
    # ISO datetime
    try:
        return _dt.datetime.fromisoformat(text).date()
    except ValueError as exc:
        raise ValueError(f"{field}: not a date: {value!r}") from exc


def daterange(start, end):
    day = start
    while day <= end:
        yield day
        day += _dt.timedelta(days=1)


def week_start(day, workweek_start="sunday"):
    start_idx = WEEKDAYS[workweek_start.lower()]
    return day - _dt.timedelta(days=(day.weekday() - start_idx) % 7)


def workweeks(period_start, period_end, workweek_start="sunday"):
    """Every workweek (start date) that overlaps the period, including partial ones."""
    weeks = []
    ws = week_start(period_start, workweek_start)
    while ws <= period_end:
        weeks.append(ws)
        ws += _dt.timedelta(days=7)
    return weeks


def norm_name(name: str) -> str:
    """'O'Brien,  Mary-Kate ' -> 'obrien,marykate' (punctuation/space/case-insensitive)."""
    if name is None:
        return ""
    text = str(name)
    if ":" in text:  # POS formats like "NICK: Last, First"
        text = text.split(":")[-1]
    text = text.lower().strip()
    text = re.sub(r"[^a-z,]", "", text)
    return text


def name_variants(name: str):
    """Return normalized forms covering 'Last, First' and 'First Last' orders."""
    base = norm_name(name)
    variants = {base}
    raw = str(name or "")
    if ":" in raw:
        raw = raw.split(":")[-1]
    raw = raw.strip()
    if "," in raw:
        last, first = [p.strip() for p in raw.split(",", 1)]
        variants.add(norm_name(f"{last},{first}"))
        variants.add(norm_name(f"{first}{last}").replace(",", ""))
    else:
        parts = raw.split()
        if len(parts) >= 2:
            first, last = parts[0], " ".join(parts[1:])
            variants.add(norm_name(f"{last},{first}"))
            variants.add(norm_name(f"{first}{last}").replace(",", ""))
    return {v for v in variants if v}


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=_json_default)
        fh.write("\n")


def _json_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"not JSON serializable: {type(obj)}")


class Findings:
    """Collects FAIL / WARN / INFO findings with a code, message and context."""

    SEVERITIES = ("FAIL", "WARN", "INFO")

    def __init__(self):
        self.items = []

    def add(self, severity, code, message, **context):
        if severity not in self.SEVERITIES:
            raise ValueError(severity)
        self.items.append({"severity": severity, "code": code, "message": message, **context})

    def fail(self, code, message, **context):
        self.add("FAIL", code, message, **context)

    def warn(self, code, message, **context):
        self.add("WARN", code, message, **context)

    def info(self, code, message, **context):
        self.add("INFO", code, message, **context)

    def extend(self, other):
        self.items.extend(other.items)

    def of(self, severity):
        return [i for i in self.items if i["severity"] == severity]

    @property
    def has_fail(self):
        return any(i["severity"] == "FAIL" for i in self.items)

    def __len__(self):
        return len(self.items)
