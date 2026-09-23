"""
Phase 1 of the generate -> validate -> correct loop (2026-09-22, user-approved after a session
of finding real numeric-hallucination and dropped-disclosure bugs one live test at a time --
"we cannot add condition for each query"). This module is the automated replacement for that
manual testing: it checks the model's OWN drafted answer against the raw tool JSON it was given,
catching the exact failure classes found today (a fabricated percentage not present anywhere in
the data; a SIMULATED/PREVIEW result narrated with no disclosure) without needing a human to
have already thought of that specific question.

Deliberately NOT trying to verify the draft is semantically correct (that's a much harder,
open-ended problem) -- only that every number in it is traceable to the data, and that known,
rule-based required disclosures are present. Both are mechanical checks, not another LLM call,
so this is nearly free to run on every turn.
"""
import re


# Numbers below this are common in ordinary phrasing (list positions, small counts spoken
# conversationally) and would produce too many false positives if required to trace back to a
# specific tool-JSON field -- e.g. "here are the top 3 cities" or "2 groups compared here".
_SKIP_GROUNDING_BELOW = 3

# Percent/decimal tolerance for matching a narrated number against a raw JSON number -- accounts
# for the model rounding "334.7" to "about 335" or "12.5" to "12.5%"/"about 12%".
_ABS_TOLERANCE = 0.6
_REL_TOLERANCE = 0.02  # 2% relative, for larger numbers (e.g. 9962 narrated as "about 9,960")


# No "-?" prefix -- deliberately does not parse negative numbers. Confirmed 2026-09-22: a range
# label like "2-24h" (a real response-window bucket name) parsed the "-24" as a negative number,
# a false positive that would trigger an unnecessary corrective retry. None of this domain's real
# metrics (counts, rates, minutes) are ever legitimately negative, so there's nothing lost by not
# recognizing a leading minus sign as negation.
_NUMBER_RE = re.compile(r"\d[\d,]*\.?\d*")


# ⚠️ ADDED 2026-09-22: confirmed live -- a markdown numbered list ("8. **Ahemdabad** ...") over
# a ~40-group breakdown had its own LIST MARKERS ("8.", "9.", "13.") parsed as data numbers by
# _NUMBER_RE, then flagged as fabricated since a list index obviously isn't in the tool JSON.
# Only strips a digit+"."/")" at the very START of a line (followed by whitespace) -- real data
# is never the first token of a markdown list line in this domain's answers, so this doesn't
# risk hiding a genuine number. Used only for validation parsing, never applied to the actual
# reply text returned to the user.
_LIST_MARKER_RE = re.compile(r"(?m)^\s*\d+[.)]\s+")


def _strip_list_markers(text: str) -> str:
    return _LIST_MARKER_RE.sub("", text)


def _parse_numbers(text: str) -> list[float]:
    out = []
    for raw in _NUMBER_RE.findall(text):
        cleaned = raw.replace(",", "")
        if cleaned in ("", "-", "."):
            continue
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def _collect_tool_numbers(tool_jsons: list[dict]) -> set[float]:
    numbers: set[float] = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            numbers.add(float(node))
        elif isinstance(node, str):
            # ⚠️ FIXED 2026-09-22: a bucket LABEL like "2h - 24h" or "< 30 min" carries a real
            # number inside a string value, not a numeric JSON leaf -- missing this produced a
            # false positive (flagging a correctly-quoted "24" from that label as fabricated).
            numbers.update(_parse_numbers(node))

    for tj in tool_jsons:
        walk(tj)
        # ⚠️ FIXED 2026-09-22: query_metric's rate metrics (connect_rate etc.) are 0-1
        # proportions, and the model is REQUIRED to convert them ×100 for display (see
        # check_unconverted_rate_metric below) -- but this function only ever recognized the
        # raw, unconverted value as "grounded", so a CORRECT conversion (0.319 -> "31.9%") was
        # wrongly flagged as a fabricated number. Add the ×100 form too, so a properly-converted
        # percentage is recognized as grounded, not penalized for doing the conversion right.
        if tj.get("metric") in _RATE_METRIC_NAMES:
            for r in tj.get("results") or []:
                # ⚠️ ADDED 2026-09-22: pooled_value (query_metric.py's volume-weighted rate,
                # alongside the naive per-hour-average "value") is ALSO a 0-1 proportion needing
                # the same ×100 conversion -- same reasoning as "value" below.
                for field in ("value", "pooled_value"):
                    v = r.get(field)
                    if isinstance(v, (int, float)):
                        numbers.add(round(v * 100, 4))
                        numbers.add(round(v * 100, 1))  # the more common display rounding
        # ⚠️ ADDED 2026-09-22: get_forecast's shape ("target"/"expected_total"/"peak_hour", no
        # "metric"/"results") was never covered by the block above at all -- confirmed live, a
        # deliberately-constructed unconverted forecast rate ("about 0.17 tomorrow" instead of
        # "17%") passed validate() with zero problems. Same ×100-grounding treatment as the
        # query_metric case, applied to expected_total and peak_hour's value.
        if tj.get("target") in _RATE_METRIC_NAMES:
            for field_path in (("expected_total",), ("peak_hour", "value")):
                node = tj
                for key in field_path:
                    node = node.get(key) if isinstance(node, dict) else None
                if isinstance(node, (int, float)):
                    numbers.add(round(node * 100, 4))
                    numbers.add(round(node * 100, 1))
    return numbers


def _is_grounded(n: float, tool_numbers: set[float]) -> bool:
    for t in tool_numbers:
        if abs(n - t) <= _ABS_TOLERANCE:
            return True
        if t != 0 and abs(n - t) / abs(t) <= _REL_TOLERANCE:
            return True
    return False


def find_ungrounded_numbers(draft: str, tool_jsons: list[dict]) -> list[float]:
    """Numbers in `draft` that don't correspond (within rounding tolerance) to any numeric
    value anywhere in the raw tool result JSON for this turn. Non-empty return means the draft
    likely contains a fabricated or miscomputed figure."""
    if not tool_jsons:
        return []
    tool_numbers = _collect_tool_numbers(tool_jsons)
    if not tool_numbers:
        return []
    bad = []
    for n in _parse_numbers(_strip_list_markers(draft)):
        if abs(n) < _SKIP_GROUNDING_BELOW:
            continue
        if not _is_grounded(n, tool_numbers):
            bad.append(n)
    return bad


# ⚠️ UPDATED 2026-09-22 (POC, user-requested): the system prompt now tells the model to use
# soft language ("preview"/"early estimate"/"still refining this") instead of clinical words
# like "simulated"/"fabricated"/"demo" -- this list must match that vocabulary, or a correctly
# soft-worded disclosure would get wrongly flagged as missing.
_SIMULATED_DISCLOSURE_WORDS = ("preview", "early estimate", "still refining", "not final",
                               "not yet final", "estimate")


# ⚠️ ADDED 2026-09-22: check_missing_disclosures only ever checked that a SOFT word was present --
# nothing stopped a draft from ALSO using a banned clinical word alongside it (confirmed live:
# "This is an early estimate and is based on simulated data" passed the missing-disclosure check
# because "early estimate" is present, even though "simulated" -- explicitly banned by the
# POC language constraint -- is right there too). Absence of the banned words is a separate,
# independently-necessary check, not implied by presence of the soft ones.
_BANNED_WORDS = ("simulated", "simulation", "fabricated", "fabrication", "fake", "synthetic",
                  "made up", "made-up", "demo", "not real")


def check_banned_language(draft: str) -> list[str]:
    draft_lower = draft.lower()
    issues = []
    for w in _BANNED_WORDS:
        if w in draft_lower:
            issues.append(
                f"the answer uses the word '{w}', which the POC language rules forbid -- rewrite "
                f"using a softer word instead, like 'preview'/'early estimate'/'still refining'"
            )
    return issues


def check_missing_disclosures(draft: str, tool_jsons: list[dict]) -> list[str]:
    """Rule-based, deterministic -- each rule fires from a field already present in the raw
    tool JSON, not from guessing at the draft's meaning."""
    issues = []
    draft_lower = draft.lower()

    for tj in tool_jsons:
        if tj.get("provenance") == "SIMULATED" and not any(
                w in draft_lower for w in _SIMULATED_DISCLOSURE_WORDS):
            issues.append(
                "a SIMULATED result was used but the draft doesn't disclose that "
                "(no word like 'simulated'/'preview'/'estimate' found)"
            )

    return issues


# ⚠️ ADDED 2026-09-22: a correctly-GROUNDED number can still be semantically MISUSED -- found
# live, after Phase 1-3 were already deployed: "26.2%" is real (Mumbai's share_pct, its share of
# all leads compared to other cities), but the draft called it "26.2% of those leads expressed
# interest in booking a test drive" -- describing a POPULATION SHARE with OUTCOME language.
# Grounding alone can't catch this (the number genuinely is in the data); this checks whether a
# share_pct-matching number appears in the same sentence as outcome-implying words.
_OUTCOME_WORDS = ("interest", "book", "convert", "schedul", "express")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# ⚠️ ADDED 2026-09-22: the original sentence-level check flagged a share_pct number even when it
# was EXPLICITLY and CORRECTLY labeled right next to it (e.g. "...0 expressed interest, share of
# all leads: 3.0%)" -- confirmed live, a multi-dimension breakdown (city x purchase_timeline)
# with mostly-zero outcome rates was forced into the raw-data fallback on every retry because
# "interest" appeared elsewhere in the same sentence as a correctly-labeled share_pct figure.
# A number immediately next to an explicit "of (all) leads" / "share of" label is demonstrably
# NOT being misused as an outcome number, regardless of what else the sentence mentions --
# proximity to the label, not just sentence co-occurrence with an outcome word, is what actually
# distinguishes correct use from misuse.
_SHARE_LABEL_RE = re.compile(r"share\s+of|of\s+(?:all\s+)?leads\b|population\s+share", re.IGNORECASE)
_LABEL_WINDOW = 45  # chars to look either side of the number for an explicit share label


def check_share_pct_misuse(draft: str, tool_jsons: list[dict]) -> list[str]:
    share_values = set()
    other_values = set()  # rate_pct/avg_minutes -- anything that's a LEGITIMATE outcome number
    for tj in tool_jsons:
        for r in tj.get("results") or []:
            if r.get("share_pct") is not None:
                share_values.add(round(r["share_pct"], 1))
            if r.get("rate_pct") is not None:
                other_values.add(round(r["rate_pct"], 1))
            if r.get("avg_minutes") is not None:
                other_values.add(round(r["avg_minutes"], 1))
    if not share_values:
        return []

    # ⚠️ FIXED 2026-09-22: a number that is BOTH a share_pct value AND a legitimate rate_pct/
    # avg_minutes value somewhere in the SAME tool results (a real coincidence -- confirmed live:
    # 0.3 was genuinely both a group's share_pct and a different group's real rate_pct in the
    # same answer) is ambiguous, not provably wrong. Only flag numbers that are UNIQUELY a
    # share_pct value and nothing else -- better to miss a real misuse in a rare coincidence than
    # block a correct answer over an unresolvable ambiguity.
    unambiguous_share_values = share_values - other_values

    issues = []
    for sentence in _SENTENCE_SPLIT_RE.split(_strip_list_markers(draft)):
        sentence_lower = sentence.lower()
        if not any(w in sentence_lower for w in _OUTCOME_WORDS):
            continue
        for m in _NUMBER_RE.finditer(sentence):
            cleaned = m.group().replace(",", "")
            if cleaned in ("", "-", "."):
                continue
            try:
                n = float(cleaned)
            except ValueError:
                continue
            if round(n, 1) not in unambiguous_share_values:
                continue
            window = sentence[max(0, m.start() - _LABEL_WINDOW):m.end() + _LABEL_WINDOW]
            if _SHARE_LABEL_RE.search(window):
                continue  # explicitly labeled as a share right next to the number -- not a misuse
            issues.append(
                f"the number {n} matches a share_pct value (a group's share of all leads) "
                f"but is described with outcome language ('{sentence.strip()}') -- share_pct "
                f"is population share, never an outcome/interest/booking rate"
            )
    return issues


# query_metric's rate-type metrics (connect_rate, purchase_interest_rate,
# test_drive_interest_rate) are 0-1 proportions, unlike query_lead_outcomes's rate_pct
# (already 0-100). Hardcoded here rather than imported from apps.assistant.catalog to keep this
# module dependency-free -- update this set if RATE_METRICS there ever changes.
_RATE_METRIC_NAMES = {"connect_rate", "purchase_interest_rate", "test_drive_interest_rate"}


def check_unconverted_rate_metric(draft: str, tool_jsons: list[dict]) -> list[str]:
    """⚠️ ADDED 2026-09-22: confirmed live (2/2, deterministic), asked to compare connect_rate
    week over week, the draft printed the raw 0-1 proportion ("about 0.2866") instead of
    converting to a percentage ("about 28.7%") -- a real violation of an EXISTING system-prompt
    rule that the number-grounding check can't catch, since 0.2866 genuinely IS in the data; the
    problem is presentation, not fabrication. Flags any raw sub-1 decimal value from a
    RATE_METRICS query_metric result appearing unconverted in the draft.

    ⚠️ EXTENDED 2026-09-22: get_forecast results (target/expected_total/peak_hour shape) were
    never covered here at all -- confirmed live, a deliberately-unconverted forecast rate ("about
    0.17 tomorrow") passed with zero problems. Same check, applied to expected_total/peak_hour's
    value too."""
    raw_values = set()
    for tj in tool_jsons:
        if tj.get("metric") in _RATE_METRIC_NAMES:
            for r in tj.get("results") or []:
                for field in ("value", "pooled_value"):
                    v = r.get(field)
                    if isinstance(v, (int, float)) and 0 < v < 1:
                        raw_values.add(round(v, 4))
        if tj.get("target") in _RATE_METRIC_NAMES:
            for field_path in (("expected_total",), ("peak_hour", "value")):
                node = tj
                for key in field_path:
                    node = node.get(key) if isinstance(node, dict) else None
                if isinstance(node, (int, float)) and 0 < node < 1:
                    raw_values.add(round(node, 4))
    if not raw_values:
        return []

    issues = []
    for n in _parse_numbers(_strip_list_markers(draft)):
        if 0 < n < 1 and round(n, 4) in raw_values:
            issues.append(
                f"the number {n} is a raw 0-1 proportion from a rate metric (connect_rate/"
                f"purchase_interest_rate/test_drive_interest_rate) shown without converting to "
                f"a percentage -- multiply by 100 and add a % sign (e.g. {n} -> {round(n*100, 1)}%)"
            )
    return issues


_HYPERLOCAL_WORDS = ("hyperlocal", "meta lead", "meta-lead")


def check_unscoped_hyperlocal_claim(draft: str, tool_jsons: list[dict]) -> list[str]:
    """⚠️ ADDED 2026-09-22: confirmed live -- asked "which city has the most hyperlocal leads",
    the model called query_lead_outcomes with group_by=["city"] alone (the WHOLE lead base, no
    is_hyperlocal scoping at all) and presented that real-but-unscoped number (Mumbai, 43 leads,
    26.2% of ALL leads) as if it specifically answered about hyperlocal leads. The number is
    genuinely grounded (it's real data), so grounding checks can't catch this -- it's a routing/
    scope mistake, not a fabrication. Only flags when NONE of this turn's query_lead_outcomes
    calls included is_hyperlocal in group_by, to avoid false positives on legitimate compound
    questions where at least one call IS properly scoped."""
    draft_lower = draft.lower()
    if not any(w in draft_lower for w in _HYPERLOCAL_WORDS):
        return []
    lead_outcome_calls = [
        tj for tj in tool_jsons
        if isinstance(tj.get("group_by"), list) and "results" in tj
    ]
    if not lead_outcome_calls:
        return []
    if any("is_hyperlocal" in tj["group_by"] for tj in lead_outcome_calls):
        return []
    return [
        "the answer discusses hyperlocal/Meta leads, but none of this turn's query_lead_outcomes "
        "calls included 'is_hyperlocal' in group_by -- this is very likely answering from the "
        "WHOLE lead base while claiming to describe hyperlocal leads specifically. Re-call "
        "query_lead_outcomes with 'is_hyperlocal' included in group_by, then use the hyperlocal-"
        "scoped numbers (or the honest decline if that combination has no real hyperlocal rows)"
    ]


# ⚠️ ADDED 2026-09-22: query_metric NEVER has hyperlocal scoping at all (it operates on org-wide
# hourly aggregates, sales_intelligence_timeseries -- no per-lead source information survives
# into that table). Confirmed live, TWO rounds of system-prompt guidance failed to stop the model
# from labeling a query_metric result "hyperlocal" when a question mixed a hyperlocal ask with a
# date-scoped one (e.g. "hyperlocal test-drive interest rate this week vs last week" -- the real
# weekly numbers are org-wide, not hyperlocal-specific, but the model called them "hyperlocal"
# anyway, deterministically, across retries). Same lesson as pooled_value: a prompt instruction
# alone isn't reliable enough here, verify mechanically instead.
_ORGWIDE_DISAMBIGUATION_WORDS = (
    "overall", "org-wide", "organisation-wide", "organization-wide", "all leads",
    "non-hyperlocal", "everyone else", "other leads", "whole lead base", "across all",
    "non-meta", "entire lead base", "org wide",
)


def check_query_metric_mislabeled_hyperlocal(draft: str, tool_jsons: list[dict]) -> list[str]:
    qm_numbers: set[float] = set()
    for tj in tool_jsons:
        if "aggregation" not in tj:
            continue  # only query_metric results carry this key -- see catalog.py's distinct
            # query_metric vs query_lead_outcomes grains
        for r in tj.get("results") or []:
            for field in ("value", "pooled_value"):
                v = r.get(field)
                if isinstance(v, (int, float)):
                    qm_numbers.add(round(v, 4))
                    if tj.get("metric") in _RATE_METRIC_NAMES:
                        qm_numbers.add(round(v * 100, 4))
                        qm_numbers.add(round(v * 100, 1))
    if not qm_numbers:
        return []

    issues = []
    for sentence in _SENTENCE_SPLIT_RE.split(_strip_list_markers(draft)):
        sentence_lower = sentence.lower()
        if not any(w in sentence_lower for w in _HYPERLOCAL_WORDS):
            continue
        if any(w in sentence_lower for w in _ORGWIDE_DISAMBIGUATION_WORDS):
            continue  # already correctly disambiguated as org-wide/overall
        for n in _parse_numbers(sentence):
            if _is_grounded(n, qm_numbers):
                issues.append(
                    f"the number {n} comes from query_metric, which is NEVER scoped to "
                    f"hyperlocal leads (it's an org-wide/all-leads aggregate) -- but it's "
                    f"described with hyperlocal wording here ('{sentence.strip()}') with no "
                    f"'overall'/'org-wide' disambiguation. Either relabel it as the overall/"
                    f"all-leads figure, or say plainly there's no hyperlocal-scoped number "
                    f"available for this date range."
                )
    return issues


def check_unpooled_rate_metric(draft: str, tool_jsons: list[dict]) -> list[str]:
    """⚠️ ADDED 2026-09-22: confirmed live -- even with an EXPLICIT system-prompt instruction to
    prefer "pooled_value" over "value" for connect_rate/purchase_interest_rate/test_drive_
    interest_rate averages, the model kept using "value" anyway (3/3 retests, deterministic).
    Same lesson as every other check in this module: a prompt instruction alone is not reliable
    enough to trust on its own, verify mechanically instead. Flags a draft number that matches
    the naive per-hour-average "value" when that same result ALSO has a pooled_value that's
    meaningfully different -- see query_metric.py's _RATE_METRIC_COUNT_FIELDS for why the two
    can diverge (business-hours vs non-business-hours connect rate: value 31.5%/35.0%, pooled
    28.8%/28.8% -- a completely different conclusion)."""
    unpooled_values = set()
    for tj in tool_jsons:
        if tj.get("metric") not in _RATE_METRIC_NAMES:
            continue
        for r in tj.get("results") or []:
            v, pv = r.get("value"), r.get("pooled_value")
            if (isinstance(v, (int, float)) and isinstance(pv, (int, float))
                    and round(v, 3) != round(pv, 3)):
                unpooled_values.add(round(v * 100, 1))
    if not unpooled_values:
        return []

    issues = []
    for n in _parse_numbers(_strip_list_markers(draft)):
        if round(n, 1) in unpooled_values:
            issues.append(
                f"the number {n}% is the naive per-hour-average rate ('value'), not the "
                f"volume-weighted overall rate ('pooled_value') -- use pooled_value instead "
                f"(converted to a %), since this result's pooled_value is meaningfully different"
            )
    return issues


def validate(draft: str, tool_jsons: list[dict]) -> list[str]:
    """Returns a list of human-readable problems found, empty if the draft looks clean."""
    problems = []
    ungrounded = find_ungrounded_numbers(draft, tool_jsons)
    if ungrounded:
        problems.append(
            f"these numbers appear in the answer but not in the real tool data: {ungrounded} "
            f"-- every number in the answer must come from the tool result, not be computed or "
            f"guessed independently"
        )
    problems.extend(check_missing_disclosures(draft, tool_jsons))
    problems.extend(check_banned_language(draft))
    problems.extend(check_share_pct_misuse(draft, tool_jsons))
    problems.extend(check_unconverted_rate_metric(draft, tool_jsons))
    problems.extend(check_unpooled_rate_metric(draft, tool_jsons))
    problems.extend(check_unscoped_hyperlocal_claim(draft, tool_jsons))
    problems.extend(check_query_metric_mislabeled_hyperlocal(draft, tool_jsons))
    return problems


# ---------------------------------------------------------------------------------------------
# Phase 3 (2026-09-22): deterministic fallback -- if the ONE corrective retry (agent.py's
# _validate_and_correct) still doesn't pass validate(), don't hand back a second-guess answer
# that might just be wrong in a different way. Render the real tool JSON directly instead: less
# natural-sounding, but built by plain string formatting, not generation, so it cannot contain a
# fabricated number or a dropped disclosure -- the two failure classes this whole loop exists for.
# Covers the tool result shapes actually in use (query_lead_outcomes/get_forecast/
# get_lead_propensity/query_metric); anything unrecognized falls through to a raw-but-honest dump
# rather than silently producing nothing.
# ---------------------------------------------------------------------------------------------

def _fmt_group(group) -> str:
    # ⚠️ FIXED 2026-09-22: this crashed outright (AttributeError, no fallback text produced at
    # all -- worse than the bug it exists to guard against) the first time a query_metric result
    # reached it. query_lead_outcomes's "group" is always a dict ({"dimension": "value"});
    # query_metric's is a plain string (a date, e.g. "2026-09-15") or None for an ungrouped
    # query -- never assumed to be one shape without checking.
    if isinstance(group, dict):
        return ", ".join(f"{k}={v}" for k, v in group.items())
    return str(group) if group is not None else ""


def render_fallback(tool_jsons: list[dict]) -> str:
    lines = ["I couldn't safely phrase this one in plain language -- here's the real data "
             "directly, so nothing gets misstated:"]
    for tj in tool_jsons:
        if tj.get("error"):
            lines.append(f"- Error: {tj['error']}")
            continue
        if tj.get("note") and not tj.get("results"):
            lines.append(f"- {tj['note']}")
            continue

        provenance_tag = " (preview estimate)" if tj.get("provenance") == "SIMULATED" else ""

        if "predictions" in tj:  # get_lead_propensity shape
            for target, pred in tj["predictions"].items():
                tag = " (preview estimate)" if pred.get("provenance") == "SIMULATED" else ""
                lines.append(f"- {target}: {pred.get('probability')}{tag}")
            for target, err in (tj.get("unavailable") or {}).items():
                lines.append(f"- {target}: unavailable")
        elif "expected_total" in tj:  # get_forecast shape
            # ⚠️ FIXED 2026-09-22: printed the raw expected_total unconverted even for a rate
            # target (connect_rate etc.), same bug class as query_metric's "value" -- convert to
            # a percentage when the target is one of the 0-1 proportion metrics.
            et = tj["expected_total"]
            if tj.get("target") in _RATE_METRIC_NAMES and isinstance(et, (int, float)):
                et_display = f"{round(et * 100, 1)}%"
            else:
                et_display = str(et)
            lines.append(
                f"- {tj.get('target')}: expected {et_display} over the next "
                f"{tj.get('horizon_hours')} hours{provenance_tag}"
            )
        elif "results" in tj and isinstance(tj["results"], list):  # query_lead_outcomes / query_metric
            if not tj["results"]:
                lines.append(f"- No matching data{provenance_tag}.")
            for r in tj["results"]:
                group = _fmt_group(r["group"]) if "group" in r else ""
                if "rate_pct" in r:
                    lines.append(f"- {group}: {r['rate_pct']}% ({r.get('n')} leads){provenance_tag}")
                elif "avg_minutes" in r:
                    disp = r.get("avg_display") or f"{r['avg_minutes']} min"
                    lines.append(f"- {group}: {disp} avg ({r.get('n')} leads){provenance_tag}")
                elif "extreme_minutes" in r:
                    kind_word = "max" if r.get("extreme_kind") == "max" else "min"
                    disp = r.get("extreme_display") or f"{r['extreme_minutes']} min"
                    lines.append(f"- {group}: {disp} ({kind_word}, {r.get('n')} leads){provenance_tag}")
                elif "share_pct" in r:
                    lines.append(f"- {group}: {r['share_pct']}% of leads ({r.get('n')}){provenance_tag}")
                elif "value" in r:  # query_metric shape -- raw value, convert if it's a rate metric
                    # prefer pooled_value (volume-weighted, the correct "overall rate") over the
                    # naive per-hour-average "value" when both exist -- see _RATE_METRIC_COUNT_
                    # FIELDS in query_metric.py for why they can meaningfully disagree.
                    v = r["pooled_value"] if r.get("pooled_value") is not None else r["value"]
                    if tj.get("metric") in _RATE_METRIC_NAMES and isinstance(v, (int, float)):
                        lines.append(f"- {group}: {round(v * 100, 1)}%{provenance_tag}")
                    else:
                        lines.append(f"- {group}: {v}{provenance_tag}")
                else:
                    lines.append(f"- {group}: {r}{provenance_tag}")
        else:
            lines.append(f"- {tj}{provenance_tag}")
    return "\n".join(lines)
