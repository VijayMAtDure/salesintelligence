"""
The assistant's one flexible historical-data tool. The LLM supplies a validated spec
(metric, group_by, aggregation, date_range) -- this module validates it against the catalog,
then computes the answer in Python over the same safely-fetched dataset apps.datastore's
timeseries_repo already uses (all_sorted()), rather than constructing dynamic SurrealQL.

At this pilot's data volume (a few hundred real hourly rows) that's both simpler and safer
than dynamic query construction -- it sidesteps SurrealDB's known quirks (silent ORDER BY
truncation, datetime WHERE-clause casting) entirely rather than needing to re-encode them for
arbitrary group-bys. If data volume grows enough to make full-table fetches impractical, this
is the place to introduce real filtered SurrealQL -- not before.

Real org-level series use item_id containing "UNKNOWN" -- same convention as
forecast_evidence.py / train_forecast.py's load().
"""
from collections import defaultdict
from datetime import datetime, timedelta

from apps.assistant.catalog import (
    AGGREGATIONS, DATE_RANGE_PRESETS, DIMENSIONS, METRICS, RATE_METRICS,
)
from apps.datastore.repositories import timeseries_repo
from apps.datastore.timeutil import parse_iso

IST_OFFSET = timedelta(hours=5, minutes=30)

_AGG_FUNCS = {
    "sum": sum,
    "avg": lambda v: sum(v) / len(v),
    "max": max,
    "min": min,
    "count": len,
}

# ⚠️ ADDED 2026-09-22: metric -> (raw numerator count field, raw denominator count field), from
# aggregates.py's exact formulas (connect_rate = calls_connected/calls_attempted, etc.). Used to
# compute a volume-weighted "pooled_value" alongside the naive per-hour-average "value" for
# RATE_METRICS when aggregation="avg". Confirmed live: comparing business-hours vs non-business-
# hours connect_rate, "value" (a simple mean of each hour's own rate) showed 31.5% vs 35% -- a
# real-looking ~3.5pp gap -- while business hours actually had ~11x the call volume per hour
# (17,244 calls over 154 hours vs 1,520 over 145), so a handful of noisy low-volume off-hours
# buckets (e.g. 1 call that happened to connect = 100% for that hour) skewed the unweighted
# average upward. The true combined rate (total connects / total attempts) is 28.8% vs 29.2% --
# nearly identical, a completely different picture. "value" is kept as-is (some questions
# genuinely want "the average hour"), pooled_value is the one that answers "what's our overall
# rate" correctly when comparing groups with very different volume per bucket.
_RATE_METRIC_COUNT_FIELDS = {
    "connect_rate": ("calls_connected", "calls_attempted"),
    "purchase_interest_rate": ("purchase_interest_yes_count", "decisions_scored"),
    "test_drive_interest_rate": ("test_drive_interest_yes_count", "decisions_scored"),
}


class InvalidQuerySpec(Exception):
    pass


def validate(spec: dict) -> None:
    errors = []
    if spec.get("metric") not in METRICS:
        errors.append(f"metric must be one of {sorted(METRICS)}, got {spec.get('metric')!r}")
    if spec.get("group_by") not in DIMENSIONS:
        errors.append(f"group_by must be one of {sorted(DIMENSIONS)}, got {spec.get('group_by')!r}")
    if spec.get("aggregation") not in AGGREGATIONS:
        errors.append(f"aggregation must be one of {sorted(AGGREGATIONS)}, got {spec.get('aggregation')!r}")
    if spec.get("date_range") not in DATE_RANGE_PRESETS:
        errors.append(f"date_range must be one of {sorted(DATE_RANGE_PRESETS)}, got {spec.get('date_range')!r}")
    # ⚠️ Enforced here, not just nudged via tool description -- see catalog.RATE_METRICS'
    # docstring for why a prompt-level hint alone wasn't reliable enough.
    if spec.get("metric") in RATE_METRICS and spec.get("aggregation") == "sum":
        errors.append(
            f"{spec.get('metric')!r} is a rate (0-1 proportion), not a count -- summing it "
            f"across time periods isn't a meaningful number. Use aggregation='avg' for a "
            f"typical rate, or 'max'/'min' for the highest/lowest period."
        )
    if errors:
        raise InvalidQuerySpec("; ".join(errors))


def _dimension_key(group_by: str, row: dict, ist_ts: datetime):
    if group_by == "total":
        # every row lands in the same bucket -- see catalog.DIMENSIONS["total"] for why this
        # exists (a single aggregated number, no per-day/per-hour breakdown).
        return "total"
    if group_by == "hour_of_day":
        return row.get("hour_of_day")
    if group_by == "weekday":
        return row.get("weekday")
    if group_by == "date":
        return ist_ts.date().isoformat()
    if group_by == "is_business_hours":
        return bool(row.get("is_business_hours"))
    raise InvalidQuerySpec(f"unhandled group_by {group_by!r}")


def _date_bounds(preset: str, real_rows: list[dict]):
    if preset == "all_time" or not real_rows:
        return None, None
    latest = max(parse_iso(r["bucket_start"]) for r in real_rows)
    latest_ist_date = (latest + IST_OFFSET).date()
    if preset == "today":
        return latest_ist_date, latest_ist_date
    if preset == "yesterday":
        d = latest_ist_date - timedelta(days=1)
        return d, d
    if preset == "last_7_days":
        return latest_ist_date - timedelta(days=6), latest_ist_date
    if preset == "previous_7_days":
        # the 7 days immediately BEFORE last_7_days -- adjacent, non-overlapping, so
        # "this week vs last week" needs no cross-row date arithmetic from the model at all.
        return latest_ist_date - timedelta(days=13), latest_ist_date - timedelta(days=7)
    if preset == "last_30_days":
        return latest_ist_date - timedelta(days=29), latest_ist_date
    return None, None


def run(spec: dict) -> dict:
    validate(spec)
    metric, group_by, aggregation, date_range = (
        spec["metric"], spec["group_by"], spec["aggregation"], spec["date_range"])

    all_rows = timeseries_repo.all_sorted()
    real_rows = [r for r in all_rows if "UNKNOWN" in r["item_id"]]

    start, end = _date_bounds(date_range, real_rows)

    is_rate_metric = metric in _RATE_METRIC_COUNT_FIELDS
    buckets: dict = defaultdict(list)
    count_buckets: dict = defaultdict(lambda: {"num": 0.0, "den": 0.0})
    for r in real_rows:
        ist_ts = parse_iso(r["bucket_start"]) + IST_OFFSET
        if start is not None and not (start <= ist_ts.date() <= end):
            continue
        value = r.get(metric)
        if value is None:
            continue
        key = _dimension_key(group_by, r, ist_ts)
        buckets[key].append(float(value))
        if is_rate_metric:
            num_field, den_field = _RATE_METRIC_COUNT_FIELDS[metric]
            num_val, den_val = r.get(num_field), r.get(den_field)
            if num_val is not None and den_val is not None:
                cb = count_buckets[key]
                cb["num"] += num_val
                cb["den"] += den_val

    # ⚠️ ADDED 2026-09-03: "today"/"yesterday" resolve against the latest REAL data point, not
    # wall-clock time (see catalog.DATE_RANGE_PRESETS) -- this pilot's data has a fixed
    # historical range. Surfacing the actual resolved date(s) here means the model can state
    # what date it's really talking about instead of letting "today" silently stand in for a
    # calendar date that may be a week or more stale.
    resolved_dates = {
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
    }

    if not buckets:
        return {
            "metric": metric, "group_by": group_by, "aggregation": aggregation,
            "date_range": date_range, "resolved_dates": resolved_dates,
            "provenance": "REAL", "results": [],
            "note": "no real data found for this metric/date_range combination",
        }

    agg_fn = _AGG_FUNCS[aggregation]
    results = []
    for key, values in buckets.items():
        row = {"group": key, "value": round(agg_fn(values), 4), "n_hours": len(values)}
        if is_rate_metric and aggregation == "avg":
            cb = count_buckets.get(key)
            if cb and cb["den"]:
                row["pooled_value"] = round(cb["num"] / cb["den"], 4)
        results.append(row)
    # sort by pooled_value when it exists (the volume-correct figure) so "highest"/"lowest"
    # below picks the group that's actually highest/lowest, not one that only looks that way
    # because of a naive per-hour average -- see _RATE_METRIC_COUNT_FIELDS docstring above.
    results.sort(key=lambda r: r.get("pooled_value", r["value"]), reverse=True)

    # ⚠️ ADDED 2026-09-03: confirmed the model can misread which row is highest/lowest when it
    # has to scan `results` itself -- asked for the "fewest connects" hour, it picked a
    # near-maximum row and mislabeled which hour it belonged to. Same lesson as
    # forecast_evidence.compare(): don't make the model do arithmetic or list-scanning in its
    # head, hand it the already-correct answer instead.
    return {
        "metric": metric, "group_by": group_by, "aggregation": aggregation,
        "date_range": date_range, "resolved_dates": resolved_dates,
        "provenance": "REAL", "results": results,
        "highest": results[0], "lowest": results[-1],
    }
