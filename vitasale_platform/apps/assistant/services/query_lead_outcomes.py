"""
The assistant's flexible PER-LEAD cross-tab tool -- the lead-level counterpart to
query_metric.py, which only ever answers hourly/org-wide aggregate questions
(sales_intelligence_timeseries). This one answers questions shaped like "which car models
close test drives fastest" or "which city converts best" -- grouped by up to 2 dimensions
(apps.assistant.catalog.LEAD_DIMENSIONS), against an outcome RATE
(apps.assistant.catalog.LEAD_METRICS), computed over sales_intelligence_feature_snapshot rows
joined with the real (not simulated) test_drive_scheduled outcome from call_decision.

⚠️ FIXED 2026-09-18: this used to pull only hyperlocal (Meta)-sourced rows, scoping EVERY
dimension to that channel even for ones with nothing to do with it. Now pulls the WHOLE real
lead base (feature_snapshot_repo.lead_outcome_rows()) -- GENERAL dimensions
(apps.assistant.catalog.GENERAL_LEAD_DIMENSIONS: product/city/email_domain_type/
purchase_timeline/response_speed_bucket) are real for any lead. HYPERLOCAL-ONLY dimensions
(meta_response_window_bucket/meta_buying_timeline/meta_platform/meta_is_organic/
meta_campaign_name) genuinely don't exist for non-Meta leads -- the existing skip-on-None-for-
THIS-dimension logic below already handles a mixed population correctly, nothing new needed
there, it just was never given non-hyperlocal rows to apply that logic to before.

⚠️ ADDED 2026-09-22: metrics were previously ALWAYS a rate of a boolean outcome (rate_pct).
Confirmed live: asked "which car model responds fastest", the model had no way to answer a pure
timing question and substituted test_drive_interest_rate instead -- a real but unrelated number
(outcome rate within a response-time bucket, not response speed itself), presented as if it
answered the question asked. AVERAGE_LEAD_METRICS (apps.assistant.catalog) now marks metrics
that aggregate a continuous per-lead VALUE instead -- run() branches on this, producing
avg_minutes/"fastest"/"slowest" instead of rate_pct/"highest"/"lowest". Add new average metrics
to AVERAGE_METRIC_FIELDS below (metric -> source column), not a new code branch.

⚠️ ADDED 2026-09-22 (second fix, same day): a "share_pct" field (each group's share of the total
leads in the result) was added to every metric's output, specifically for "what % of leads have
X" questions. Confirmed this did NOT fix the underlying problem: even with the correct
share_pct=0.0 sitting right next to an unrelated rate_pct=50.0 in the same tool result, and an
explicit system-prompt instruction naming share_pct directly, the model still read rate_pct.
SHARE_ONLY_METRICS (apps.assistant.catalog) is the real fix -- lead_share is a metric with NO
rate_pct field in its result at all, so there is no wrong number sitting next to the right one to
grab by mistake. Removing the distractor, not just labeling the right answer more clearly, is
what actually closes this failure mode.
"""
from collections import defaultdict

from apps.analytics.services.response_window import WINDOWS, _bucket
from apps.assistant.catalog import (
    AVERAGE_LEAD_METRICS, EXTREME_LEAD_METRICS, GENERAL_LEAD_DIMENSIONS, LEAD_DIMENSIONS,
    LEAD_METRICS, MAX_LEAD_GROUP_BY_DIMENSIONS, SHARE_ONLY_METRICS,
)
from apps.datastore.repositories import (
    call_decision_repo, catalog_repo, feature_snapshot_repo, lead_repo, meta_lead_repo,
)

# metric -> the raw feature_snapshot column it averages. Only avg_meta_response_minutes today;
# add here (not a new branch) if a general average metric (e.g. avg response_speed) is ever added.
AVERAGE_METRIC_FIELDS = {"avg_meta_response_minutes": "meta_to_first_contact_mins"}

# metric -> (raw feature_snapshot column, "max"/"min") -- see catalog.EXTREME_LEAD_METRICS.
EXTREME_METRIC_FIELDS = {
    "max_meta_response_minutes": ("meta_to_first_contact_mins", "max"),
    "min_meta_response_minutes": ("meta_to_first_contact_mins", "min"),
}


def _fmt_response_minutes(mins: float | None) -> str | None:
    # ⚠️ ADDED 2026-09-22: a raw minutes value over an hour (e.g. 20154.4, the real Saumil
    # outlier) is hard to read as-is. Converting is real arithmetic (divide by 60) -- following
    # this project's own established lesson (see true_count's docstring), that's precomputed
    # here in Python, not left for the model to do in its head. avg_minutes/extreme_minutes stay
    # in raw minutes (existing sort/comparison code depends on a plain comparable number); this
    # is an ADDITIONAL display-only field alongside them.
    if mins is None:
        return None
    if mins <= 60:
        return f"{round(mins, 1)} min"
    return f"{round(mins / 60, 1)} hours"


class InvalidQuerySpec(Exception):
    pass


def validate(spec: dict) -> None:
    errors = []
    if spec.get("metric") not in LEAD_METRICS:
        errors.append(f"metric must be one of {sorted(LEAD_METRICS)}, got {spec.get('metric')!r}")
    group_by = spec.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append("group_by must be a non-empty list of dimensions")
    elif len(group_by) > MAX_LEAD_GROUP_BY_DIMENSIONS:
        errors.append(f"group_by supports at most {MAX_LEAD_GROUP_BY_DIMENSIONS} dimensions "
                       f"at once, got {len(group_by)}")
    elif any(d not in LEAD_DIMENSIONS for d in group_by):
        errors.append(f"group_by entries must all be one of {sorted(LEAD_DIMENSIONS)}, "
                       f"got {group_by}")
    if errors:
        raise InvalidQuerySpec("; ".join(errors))


def _dimension_value(dim: str, row: dict, model_by_product_id: dict, lead_extra: dict,
                      channel_extra: dict, purchase_timeline: dict) -> str | None:
    if dim == "is_hyperlocal":
        # channel_extra is {} for a lead with no sales_intelligence_meta_lead row at all, and a
        # non-empty dict (platform/is_organic/campaign_name keys, even if all None) for one that
        # has a real row -- bool() on it is exactly "does this lead have a real hyperlocal
        # record", independent of whether any specific channel field within it is populated.
        return str(bool(channel_extra))
    if dim == "product":
        pid = row.get("product_id")
        return model_by_product_id.get(str(pid)) if pid else None
    if dim == "city":
        return lead_extra.get("city")
    if dim == "email_domain_type":
        return lead_extra.get("email_domain_type")
    if dim == "purchase_timeline":
        return purchase_timeline.get(row.get("source_call_decision_id"))
    if dim == "response_speed_bucket":
        mins = row.get("time_to_first_response_minutes")
        return _bucket(mins) if mins is not None else None
    if dim == "meta_response_window_bucket":
        mins = row.get("meta_to_first_contact_mins")
        return _bucket(mins) if mins is not None else None
    if dim == "meta_buying_timeline":
        return row.get("meta_buying_timeline")
    if dim == "meta_platform":
        return channel_extra.get("platform")
    if dim == "meta_is_organic":
        v = channel_extra.get("is_organic")
        return None if v is None else str(v)  # bool -> "True"/"False" string, consistent group keys
    if dim == "meta_campaign_name":
        return channel_extra.get("campaign_name")
    raise InvalidQuerySpec(f"unhandled group_by dimension {dim!r}")


def _outcome_true(metric: str, row: dict, test_drive_booked: dict) -> bool | None:
    if metric == "test_drive_scheduled_rate":
        cid = row.get("source_call_decision_id")
        return test_drive_booked.get(cid) if cid in test_drive_booked else None
    if metric == "test_drive_interest_rate":
        return bool(row.get("test_drive_interest_flag"))
    if metric == "purchase_interest_rate":
        return row.get("purchase_interest_latest") == "YES"
    raise InvalidQuerySpec(f"unhandled metric {metric!r}")


def run(spec: dict) -> dict:
    validate(spec)
    metric, group_by = spec["metric"], spec["group_by"]
    is_average = metric in AVERAGE_LEAD_METRICS
    is_share_only = metric in SHARE_ONLY_METRICS
    is_extreme = metric in EXTREME_LEAD_METRICS

    rows = feature_snapshot_repo.lead_outcome_rows()
    test_drive_booked = call_decision_repo.test_drive_booked_by_id()
    model_by_product_id = catalog_repo.model_by_product_id()
    lead_extras = lead_repo.city_and_email_by_id()
    channel_extras = meta_lead_repo.channel_fields_by_lead_id()
    purchase_timeline = call_decision_repo.purchase_timeline_by_id()

    groups: dict[tuple, dict] = defaultdict(
        lambda: {"n": 0, "true": 0, "unknown": 0, "sum": 0.0, "count": 0, "extreme": None})
    for row in rows:
        lead_extra = lead_extras.get(str(row.get("lead_id")), {})
        channel_extra = channel_extras.get(str(row.get("lead_id")), {})
        key_parts = tuple(
            _dimension_value(d, row, model_by_product_id, lead_extra, channel_extra,
                              purchase_timeline)
            for d in group_by
        )
        if None in key_parts:
            continue  # this row has no value for one of the requested dimensions -- skip it,
            # don't fold it into a misleading "unknown" bucket that mixes real groups together
        g = groups[key_parts]
        g["n"] += 1
        if is_share_only:
            pass  # just counting leads per group -- no outcome/value to track at all
        elif is_average:
            val = row.get(AVERAGE_METRIC_FIELDS[metric])
            if val is None:
                g["unknown"] += 1
            else:
                g["sum"] += val
                g["count"] += 1
        elif is_extreme:
            field, kind = EXTREME_METRIC_FIELDS[metric]
            val = row.get(field)
            if val is None:
                g["unknown"] += 1
            else:
                g["count"] += 1
                if g["extreme"] is None:
                    g["extreme"] = val
                elif kind == "max":
                    g["extreme"] = max(g["extreme"], val)
                else:
                    g["extreme"] = min(g["extreme"], val)
        else:
            outcome = _outcome_true(metric, row, test_drive_booked)
            if outcome is None:
                g["unknown"] += 1
            elif outcome:
                g["true"] += 1

    if not groups:
        uses_hyperlocal_only = any(d not in GENERAL_LEAD_DIMENSIONS for d in group_by)
        # ⚠️ FIXED 2026-09-22: real hyperlocal leads exist now (133, backfilled and validated
        # earlier this session) -- but meta_platform/meta_campaign_name/meta_is_organic are
        # still genuinely blank for all of them (never available from the backfill source, an
        # Excel export with no ad-attribution columns). The old blanket "no hyperlocal lead data
        # has flowed through the pipeline yet" was TRUE before that backfill and is FALSE now --
        # confirmed live: asked "which campaign is producing the most interest", it still claimed
        # zero hyperlocal data exists, when 133 real leads do, just not that specific field.
        # channel_extras is already fetched above from the real sales_intelligence_meta_lead
        # table -- non-empty means real hyperlocal leads exist, regardless of whether THIS
        # dimension's specific field is populated on any of them.
        if uses_hyperlocal_only:
            if channel_extras:
                note = (
                    f"{len(channel_extras)} real hyperlocal (Meta) leads exist, but none have "
                    "this specific field recorded -- it wasn't available from the data source "
                    "used to identify them (a client-provided export with no ad-attribution "
                    "columns), not because no hyperlocal leads exist. This will populate once "
                    "the real inbound API captures it directly."
                )
            else:
                note = (
                    "no hyperlocal (Meta) lead data has flowed through the pipeline yet -- this "
                    "will populate once real leads with source=meta start being called"
                )
        else:
            note = (
                "no leads matched this combination of dimensions -- unusual for general "
                "dimensions (product/city/email/purchase timeline/response speed), since those "
                "are real for the whole lead base; double check the requested dimensions "
                "actually apply here"
            )
        return {"metric": metric, "group_by": group_by, "provenance": "REAL", "results": [],
                "note": note}

    results = []
    for key_parts, g in groups.items():
        if is_share_only:
            # deliberately NO rate_pct/avg_minutes key here -- see module docstring's second
            # 2026-09-22 fix note for why a bare n-only result exists as its own metric.
            results.append({"group": dict(zip(group_by, key_parts)), "n": g["n"]})
        elif is_average:
            avg = round(g["sum"] / g["count"], 1) if g["count"] else None
            results.append({
                "group": dict(zip(group_by, key_parts)),
                "avg_minutes": avg, "avg_display": _fmt_response_minutes(avg),
                "n": g["n"], "n_with_known_value": g["count"],
            })
        elif is_extreme:
            results.append({
                "group": dict(zip(group_by, key_parts)),
                "extreme_minutes": g["extreme"], "extreme_display": _fmt_response_minutes(g["extreme"]),
                "extreme_kind": EXTREME_METRIC_FIELDS[metric][1],
                "n": g["n"], "n_with_known_value": g["count"],
            })
        else:
            known = g["n"] - g["unknown"]
            rate = round(100 * g["true"] / known, 1) if known else None
            results.append({
                "group": dict(zip(group_by, key_parts)),
                "rate_pct": rate, "n": g["n"], "n_with_known_outcome": known,
                # ⚠️ ADDED 2026-09-22: confirmed live, asked "how many leads expressed
                # interest", the model narrated "n" (32, the GROUP size) as if it were the count
                # that achieved the outcome, alongside a correct rate_pct=12.5 -- a real count
                # (~4) computed as n*rate_pct/100 was never in the data, so the model substituted
                # the wrong field instead of doing that multiplication itself. true_count is that
                # exact number, precomputed, so there's no arithmetic left to get wrong.
                "true_count": g["true"],
            })

    # share_pct = this group's own "n" / total "n" across every group in this result -- always
    # computed, even for outcome-rate metrics (as a convenience), but it's the ONLY numeric field
    # lead_share results carry, which is the actual point of that metric existing.
    total_n = sum(r["n"] for r in results)
    for r in results:
        r["share_pct"] = round(100 * r["n"] / total_n, 1) if total_n else None

    hyperlocal_note = None
    if "is_hyperlocal" in group_by:
        hyperlocal_rows = [r for r in results if r["group"].get("is_hyperlocal") == "True"]
        hyperlocal_total_n = sum(r["n"] for r in hyperlocal_rows)
        if hyperlocal_total_n:
            # ⚠️ ADDED 2026-09-22: "share_pct" above is this row's share of the WHOLE cross-tab
            # (hyperlocal AND non-hyperlocal rows combined) -- confirmed live, the model read that
            # as "X% of hyperlocal leads" for a product breakdown, which is a different, much
            # smaller number than X's real share among hyperlocal leads specifically (e.g. XC60
            # was 13 of 16 total hyperlocal-with-product leads = 81.2%, not the cross-tab's 9.2%).
            # This field is the correct, ready-to-use denominator-restricted share.
            for r in hyperlocal_rows:
                r["share_pct_of_hyperlocal"] = round(100 * r["n"] / hyperlocal_total_n, 1)
        else:
            # ⚠️ ADDED 2026-09-22: confirmed live -- asked "which city has the most hyperlocal
            # leads", the model silently fell back to group_by=["city"] alone (the WHOLE lead
            # base) and presented that overall count as if it were hyperlocal-specific, because
            # group_by=["city","is_hyperlocal"] genuinely returns zero real hyperlocal rows (no
            # hyperlocal lead has a city on file) and nothing said so explicitly. This note makes
            # that gap explicit instead of leaving it to be inferred from an empty subset.
            hyperlocal_note = (
                "no hyperlocal (Meta) leads have a value for the non-is_hyperlocal dimension(s) "
                f"in this query ({[d for d in group_by if d != 'is_hyperlocal']}) -- every result "
                "row below is for non-hyperlocal leads only. Do not present this as an answer "
                "about hyperlocal leads; say plainly that this data isn't available for "
                "hyperlocal leads specifically."
            )

    out = {
        "metric": metric, "group_by": group_by, "provenance": "REAL",
        "results": results,
        "response_window_buckets": [w[0] for w in WINDOWS],  # so the model can name them correctly
    }
    if hyperlocal_note:
        out["note"] = hyperlocal_note
    # ⚠️ FIXED 2026-09-22: a group with NO known value (avg_minutes/rate_pct is null -- e.g. EC40
    # had 10 leads but 0 with a real response-time value) was still eligible to be picked as
    # "slowest"/"lowest" by the naive sort below, since None sorts last either way -- null isn't
    # a real value to compare, so it must never win an extremum slot. Full `results` (nulls
    # included) is unaffected; only the fastest/slowest/highest/lowest/largest/smallest picks
    # are filtered.
    if is_share_only:
        results.sort(key=lambda r: -r["share_pct"])
        out["largest_group"], out["smallest_group"] = results[0], results[-1]
    elif is_average:
        with_value = [r for r in results if r["avg_minutes"] is not None]
        # lower avg_minutes = faster response -- "fastest"/"slowest", not "highest"/"lowest",
        # since those names would read backwards for a "smaller is better" metric.
        with_value.sort(key=lambda r: r["avg_minutes"])
        results.sort(key=lambda r: (r["avg_minutes"] is None, r["avg_minutes"] or float("inf")))
        if with_value:
            out["fastest"], out["slowest"] = with_value[0], with_value[-1]
    elif is_extreme:
        with_value = [r for r in results if r["extreme_minutes"] is not None]
        with_value.sort(key=lambda r: -r["extreme_minutes"])
        results.sort(key=lambda r: (r["extreme_minutes"] is None, -(r["extreme_minutes"] or 0)))
        if with_value:
            out["highest"], out["lowest"] = with_value[0], with_value[-1]
    else:
        with_value = [r for r in results if r["rate_pct"] is not None]
        with_value.sort(key=lambda r: -r["rate_pct"])
        results.sort(key=lambda r: (r["rate_pct"] is None, -(r["rate_pct"] or 0)))
        if with_value:
            out["highest"], out["lowest"] = with_value[0], with_value[-1]
    return out
