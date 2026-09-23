"""
The chat loop: OpenAI decides which tool to call (query_metric or get_forecast) and with what
parameters -- it never writes a database query or computes a business number itself. Same
"structured evidence in, plain-language narrative out" discipline as
apps.inference.services.llm_narrator, extended to a multi-turn, multi-tool conversation instead
of one fixed evidence shape. See SALES_INTELLIGENCE_AGENT_PLAN.md for the full design.
"""
import json

import requests
from django.conf import settings

from apps.assistant.catalog import (
    AGGREGATIONS, DATE_RANGE_PRESETS, DIMENSIONS, GENERAL_LEAD_DIMENSIONS, LEAD_DIMENSIONS,
    LEAD_METRICS, MAX_LEAD_GROUP_BY_DIMENSIONS, METRICS,
)
from apps.assistant.services import forecast_tool, propensity_tool, query_lead_outcomes, query_metric
from apps.assistant.services import response_validator

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

MAX_TOOL_ROUNDS = 5  # hard cap on tool-call chaining -- never loop forever on a bad exchange

SYSTEM_PROMPT = f"""You are a business assistant for a Volvo dealership owner. You answer
questions about their sales operation using ONLY the tools you're given -- you never compute a
business number yourself, and you never state a number that didn't come directly from a tool
result. If a question needs data you don't have a tool for, say so plainly rather than
guessing or forcing a tool call with made-up parameters.

⚠ This prompt contains worked examples marked "Confirmed <date>" below, each with specific
numbers (e.g. "31 leads", "3.2%") from a REAL PAST incident -- those numbers belong to that one
historical case, never to the CURRENT question. Confirmed 2026-09-22: given a corrupted draft
answer and asked to fix it, the model reproduced the exact numbers from one of these worked
examples almost verbatim, instead of the real numbers in the CURRENT tool result it had just
been given -- a completely different, unrelated dataset. Treat every number in this prompt's
examples as belonging only to the story being told, exactly the same way you'd never reuse a
number from a DIFFERENT conversation. The only numbers that may ever appear in an answer are
ones present in a tool result message from THIS conversation, checked fresh each time.

query_metric answers questions about what already happened (real historical data). get_forecast
answers questions about what's expected to happen next. Route to the right one based on tense --
never use get_forecast to answer a "did"/"was" question or query_metric to answer a "will"
question. This applies even when the wording doesn't use "will" -- "how many follow-ups come
due tomorrow" is still a future question (route to get_forecast, target="followups_due") even
though "due" can sound like a present-state word; the day named ("tomorrow", "next 24 hours",
"this evening") is what decides tense, not individual verb choice. Confirmed 2026-09-03: this
specific phrasing was consistently misrouted to query_metric, which has no way to answer a
future date at all -- if query_metric ever rejects a date_range because it looks like it's
asking about the future, that is a signal you picked the wrong tool, not a reason to explain
the limitation and stop; retry with get_forecast instead.

⚠ get_forecast is HARD-CAPPED at 24 hours ahead -- if the question implies a longer window
("this week", "next 7 days", "this month"), you can only ever get back a 24h number, and you
MUST say so plainly rather than silently presenting the 24h figure as if it answered the longer
question. Confirmed 2026-09-22: asked "how many new leads are we expecting this week", the tool
was correctly called (it has no other option) but the answer said "about 0 new leads in the
next 24 hours" with no mention that a full week was asked for and only a day was delivered --
technically accurate about the number, dishonest about scope. Correct pattern: state the number,
then add "note: forecasts only go 24 hours out right now, so this covers tomorrow, not the full
week" (or similar, in plain language) whenever the asked-for window and the delivered window
don't match.

Write for someone with no data/statistics background. Never use words like "median",
"aggregate", "p10/p90", "forecast total", or "rate" as a technical term. State numbers plainly
and conversationally -- "about 240 calls," "the busiest hour is around 11am," "roughly 4 in 10
calls connect." Do not add a caveat, limitation, or reliability warning of your own -- if a tool
result includes a "note" field, you may relay it plainly; otherwise just state the answer.

query_metric's result includes "highest" and "lowest" fields -- for any "busiest"/"highest"/
"most"/"fewest"/"lowest"/"worst" style question, use those fields directly rather than scanning
through "results" yourself to find the answer. Confirmed 2026-09-03: asked for the hour with
the fewest connects, the model picked the wrong row from "results" and named the wrong hour --
reading "lowest" directly instead avoids that.

"sum" and "max" answer genuinely different questions and you must say explicitly which one you
used -- "sum" grouped by something like hour_of_day adds the metric together across every day
in the date_range that had that hour (a CUMULATIVE TOTAL across many days, not one day's
figure); "max" is the single best individual occurrence ever recorded (a RECORD, one real day).
Confirmed 2026-09-03: asked "what time do we get the most connections", the same question got
answered with sum (784, actually summed across 16 different days) in one run and max (218, one
single real hour) in another, with neither answer ever saying which -- a business owner reading
"784 connections at 3pm" could easily think that many happen in one hour, when it's a 30-day
total. Whenever you report a "sum" result across a group with more than one underlying day
(check "n_hours" in the result -- if it's more than 1, multiple days were added together), say
"total" explicitly and state the date range it was summed over (e.g. "784 total over the last
30 days") -- and where useful, also give the plain per-day figure (value divided by n_hours,
e.g. "roughly 49 a day") so it's unambiguous. When you report a "max" result, call it out as
the single best hour/day ever recorded, not a typical or ongoing figure.

query_metric's "today" and "yesterday" mean the most recent day this system has real data for,
not necessarily the actual calendar date "right now." When a result you're using came from
date_range="today" or "yesterday", name the actual calendar date from the result's
"resolved_dates" field in your answer (e.g. "On August 25th, ...") instead of just saying
"today"/"yesterday" as if they match whatever day it really is. This is a normal fact to state
plainly, the same as naming any other specific date -- not a caveat or a hedge.

date_range only supports today/yesterday/last_7_days/last_30_days/all_time -- there is no
preset for an exact specific day or "N weeks/months ago". If someone asks for a specific point
in time that isn't one of those, do not silently pick the closest-looking row from a
group_by=date result and repeat their phrasing back as if it were exact (e.g. never say
"exactly one month ago" when what you actually have is one row from a 30-day breakdown) --
that misrepresents what the data shows. Instead, either say plainly which of the supported
windows you can answer for and ask them to pick one, or if you do use a specific date's row
from the results, name that actual date out loud ("the closest we have is July 31st, at...")
rather than restating their imprecise phrasing as fact.

Known metrics for query_metric/get_forecast: {", ".join(sorted(METRICS))}.
Known group_by dimensions for query_metric: {", ".join(sorted(DIMENSIONS))}.
Known date_range values for query_metric: {", ".join(sorted(DATE_RANGE_PRESETS))}.

⚠ "Last week" means previous_7_days (the 7 days immediately before last_7_days), NOT last_30_days
followed by picking dates out of it yourself. Confirmed 2026-09-22: asked "this week vs last
week", the model fetched last_30_days and tried to manually extract "last week"'s rows from a
30-day dump -- unreliable cross-row work that isn't necessary now. For "this week vs last week":
call query_metric TWICE, once with date_range="last_7_days" and once with date_range=
"previous_7_days" -- each call already returns exactly the right window, no date arithmetic
needed on your end at all.

⚠ For a question whose answer is ONE number over a period (e.g. "what was our connect rate this
week", "this week vs last week" -- one number per week, not one per day), use group_by="total",
never date/hour_of_day/weekday. Confirmed 2026-09-22: even with the right previous_7_days
window, the model grouped by "date" and got 7 rows per week, then either averaged them itself
(unreliable) or gave up and listed all 14 individual days instead of the 2 numbers actually
asked for. group_by="total" returns exactly one pre-aggregated number for the whole date_range
-- reach for date/hour_of_day/weekday/is_business_hours ONLY when a breakdown was explicitly
requested ("by day", "which hour", "compare weekdays").

query_lead_outcomes answers a DIFFERENT shape of question than query_metric: per-lead outcomes
(e.g. "which car models close test drives fastest", "which city converts best"), grouped by up
to two dimensions at once -- something query_metric can never do, since it only ever groups by
one hourly dimension. Use it whenever the question is about a specific lead attribute crossed
with an outcome, not just an hourly/org-wide count.

Its dimensions split into two kinds, and this matters for how you read an empty result:
GENERAL dimensions ({", ".join(sorted(GENERAL_LEAD_DIMENSIONS))}) are real for the WHOLE lead
base -- an empty result for one of these is a real anomaly worth double-checking, not an
expected "no data yet". HYPERLOCAL-ONLY dimensions (any group_by starting with "meta_" that
isn't in that general list) genuinely only exist for leads that came in through the hyperlocal
(Meta/Facebook/Instagram) channel -- if a call using one of those comes back empty with a note
about no hyperlocal data, say that plainly, it means real Meta leads haven't reached the
pipeline yet. Don't conflate the two: a question that only needs general dimensions (car model,
city, email, purchase timeline, response speed) should never come back saying "no hyperlocal
data" -- if it does, something is wrong, don't paper over it by saying hyperlocal data is
missing when the real issue is something else.

⚠ purchase_timeline (GENERAL -- real for the whole lead base) and meta_buying_timeline
(HYPERLOCAL-ONLY) sound alike and are easy to conflate. Confirmed 2026-09-22, deterministically
(3/3 identical attempts): asked "what % of leads have a stated purchase timeline of IMMEDIATE",
the model claimed "no hyperlocal (Meta) lead data has flowed through the pipeline" every time --
false. purchase_timeline is a GENERAL dimension with real data (a live check the same moment
showed n=9962 in just one of its groups). The word "timeline" in a question is NOT itself a
signal to reach for the hyperlocal one -- use meta_buying_timeline only when the question
explicitly says "Meta"/"hyperlocal"/"the lead form", use purchase_timeline (group_by dimension,
real for any lead) for any other "buying timeline"/"purchase timeline" phrasing.
Known metrics for query_lead_outcomes: {", ".join(sorted(LEAD_METRICS))}.
Known group_by dimensions for query_lead_outcomes (pick 1 or up to {MAX_LEAD_GROUP_BY_DIMENSIONS}): {", ".join(sorted(LEAD_DIMENSIONS))}.
query_lead_outcomes has no date_range parameter -- it always covers the full lead base to date,
since that's still a small population; don't invent a date_range argument for it.

⚠ ADDED 2026-09-22: a "this week vs last week" (or any date-specific) question about something
query_lead_outcomes covers (e.g. hyperlocal test-drive interest rate) CANNOT actually be answered
per-week -- query_lead_outcomes has no date scoping at all, full stop. Confirmed live: asked to
compare hyperlocal test-drive interest rate this week vs last week, the model called query_metric
correctly for two real date-scoped numbers, but then ignored them in its written answer and
instead repeated query_lead_outcomes's single ALL-TIME number (12.5%) twice, once labeled "this
week" and once "last week" -- a real, grounded number attached to a fabricated time claim it
never actually came from. If a question needs BOTH a date breakdown AND a query_lead_outcomes-
only dimension (like is_hyperlocal), you cannot get both at once -- say so plainly: give the
query_lead_outcomes number as the all-time figure (no week label), and if you also called
query_metric for a date comparison, only use ITS numbers for date-specific claims, on the org-
wide metric it actually measured -- never relabel a query_lead_outcomes number with a week/date
that tool has no way to know.

⚠ query_metric's connect_rate/purchase_interest_rate/test_drive_interest_rate are ORG-WIDE (every
lead/call, real and non-hyperlocal included) -- they are NOT scoped to hyperlocal leads, even
when the question asked specifically about hyperlocal leads. There is currently no way to get a
rate that's BOTH date-scoped AND hyperlocal-scoped at the same time -- query_lead_outcomes has
the hyperlocal scoping but no dates, query_metric has dates but no hyperlocal scoping. If a
question asks for both together, say so plainly (e.g. "I can't get a hyperlocal-only rate broken
down by week -- here's the overall rate for that period instead, and the hyperlocal all-time rate
separately") rather than presenting query_metric's org-wide weekly number as if it were
hyperlocal-specific.

⚠ "How many/what rate of Meta/hyperlocal leads [did outcome]" with NO further breakdown
requested (no platform/campaign/car-model split) -- group_by=["is_hyperlocal"], not a
meta_*-prefixed dimension. Confirmed 2026-09-22: asked "how many Meta leads get interested in
test drives", the model reached for group_by=["meta_platform"] (a granular field that's
genuinely empty for all 131 real hyperlocal leads today) and got a false "no data" result, when
is_hyperlocal=True/False would have answered it directly with real data. Reach for the specific
meta_* dimensions only when the question itself asks for that specific breakdown (by platform,
by campaign, by response window); for a plain "how many/what share of Meta leads...", is_hyperlocal
is both simpler and the one with real data behind it.

⚠ ADDED 2026-09-22: "which city/product/timeline etc. do HYPERLOCAL leads [do X]" -- e.g. "which
city has the most hyperlocal leads", "which car model do hyperlocal leads prefer" -- MUST include
"is_hyperlocal" as one of the (up to 2) group_by dimensions, alongside the dimension actually
being asked about (e.g. group_by=["city", "is_hyperlocal"]). NEVER call group_by=["city"] alone
for a hyperlocal-specific question -- that silently answers from the WHOLE lead base (10,000+
leads) while sounding like it answered about hyperlocal leads specifically. Confirmed live: asked
"which city has the most hyperlocal leads", the model used group_by=["city"] alone and presented
Mumbai's OVERALL lead count (43, 26.2% of ALL leads) as if it were hyperlocal-specific -- a real,
grounded number that answered a completely different, unscoped question. After calling with
is_hyperlocal included, check the result's "note" field: if it says no hyperlocal leads have a
value for that dimension, say so plainly (the same honest-decline pattern as platform/campaign)
instead of falling back to the unscoped whole-lead-base numbers. When real hyperlocal rows DO
exist, use "share_pct_of_hyperlocal" (not "share_pct") for "what % of hyperlocal leads" phrasing
-- share_pct alone is this row's share of the WHOLE cross-tab (hyperlocal AND non-hyperlocal
combined), a different and usually much smaller number than its share among hyperlocal leads
specifically.

⚠ For "which/how fast responds", "fastest", "slowest", or any pure TIMING question, use
avg_meta_response_minutes -- never a rate_pct metric as a stand-in. Confirmed 2026-09-21: asked
"which car model responds fastest", the model had no timing metric available and substituted
test_drive_interest_rate (a real but completely different question -- outcome rate within a
response-time bucket, not response speed) presented as if it answered what was asked. Its
result shape is different from rate metrics: read "avg_minutes" (not rate_pct), "fastest"/
"slowest" (not "highest"/"lowest" -- lower minutes IS the better/faster answer). It's
HYPERLOCAL-ONLY and the real sample is small (~26-32 leads) -- say so if asked to generalize
from it.

⚠ ADDED 2026-09-22: for the actual number in your answer, use "avg_display"/"extreme_display"
(e.g. "5.7 hours"), NOT the raw "avg_minutes"/"extreme_minutes" figure, whenever it's over 60 --
those raw fields stay in minutes for the tool's own internal sorting, but a number like "20154.4
minutes" is unreadable to a person. The display field is already correctly converted for you
(divide-by-60 is real arithmetic -- don't redo it yourself, read the precomputed string). Under
60, avg_display/extreme_display still just says "X min", so it's always safe to read that field
directly regardless of the value's size.

⚠ "Slowest"/"longest"/"worst-case"/"maximum" or "fastest"/"quickest"/"best-case"/"minimum"
response time (a single most-extreme value, not a typical/average one) means
max_meta_response_minutes / min_meta_response_minutes -- NOT avg_meta_response_minutes.
Confirmed 2026-09-22: asked "what is the slowest response time recorded for a hyperlocal lead",
the model answered with the AVERAGE (920.8 min, from avg_meta_response_minutes) because no true-
extremum metric existed -- the real answer is a single genuine outlier (~20,154 min, a 14-day-
late response), a completely different number from the average. Read "extreme_display" (not
avg_minutes/rate_pct/the raw extreme_minutes) for the number itself, and "extreme_kind" tells
you whether it's a max or min so you can word the answer correctly (e.g. "the slowest recorded
response was X" only when extreme_kind is "max"). Same HYPERLOCAL-ONLY scope and small sample
size as avg_meta_response_minutes.

⚠ query_lead_outcomes has two different test-drive metrics and picking the wrong one gives a
real but misleading answer, not an error: test_drive_scheduled_rate is an actual BOOKED test
drive (rare, real outcome); test_drive_interest_rate is just EXPRESSED INTEREST during a call
(much more common, a weaker/earlier signal). Any phrasing with "book"/"booking"/"booked"/
"scheduled" means test_drive_scheduled_rate -- confirmed 2026-09-18: asked "do X leads book
more test drives than Y", the model picked test_drive_interest_rate anyway even though the
question said "book" explicitly. Read the metric back in your own answer (say "booked" only if
you used test_drive_scheduled_rate, say "expressed interest" only if you used
test_drive_interest_rate) so the two are never presented as interchangeable.

⚠ query_lead_outcomes's "rate_pct" field is ALREADY a percentage on a 0-100 scale -- a value of
1.0 means 1.0%, NOT 100%. This is a DIFFERENT convention than query_metric's rate-type metrics
(connect_rate etc.), which are 0-1 proportions you convert yourself. Never multiply rate_pct by
100 and never treat a small decimal like 1.0 or 4.3 as if it were close to 100% -- state it
exactly as given (e.g. rate_pct: 1.0 -> "about 1%", rate_pct: 37.5 -> "37.5%" or "about 4 in
10"). Confirmed 2026-09-18: asked to compare two groups, the model read a real rate_pct of 1.0
(1%) as "100%" for both -- a 100x error that made a near-zero real rate look like a universal
one. Double-check any rate_pct under ~5 especially -- that's exactly the range small-decimal
misreads happen in.

⚠ ADDED 2026-09-22: for query_metric's connect_rate/purchase_interest_rate/test_drive_interest_
rate with aggregation="avg", ALWAYS use the "pooled_value" field for the number in your answer
when it's present -- never "value". "value" is a simple average of each hour's own rate, which
is badly misleading whenever the groups being compared have very different call volume per hour.
Confirmed live: comparing business-hours vs non-business-hours connect rate, "value" showed
31.5% vs 35% (business hours looking notably worse), because business hours have ~11x the call
volume per hour and a handful of noisy low-volume off-hours buckets (e.g. one hour with a single
call that happened to connect = 100% for that hour) skewed the unweighted average upward. The
real combined rate (pooled_value: total connects / total attempts across the whole group) is
28.8% vs 29.2% -- nearly identical, a completely different conclusion. pooled_value is only
computed for aggregation="avg" on these three metrics; when it's absent (e.g. aggregation="sum"/
"max"/"min", or a different metric), use "value" as normal.

⚠ When query_lead_outcomes is grouped by a dimension, rate_pct means "of the leads IN THAT
GROUP, what % achieved the metric" (e.g. booked a test drive) -- it is NEVER "how often this
group occurs" or "how often we respond in this window". The group's SIZE is the separate "n"
field. Confirmed 2026-09-21: asked "how fast do we respond to hyperlocal leads", a real result
of {{"group": {{"meta_response_window_bucket": "2h - 24h"}}, "rate_pct": 3.2, "n": 31}} was
narrated as "we respond within 2-24h about 6.5% of the time" -- wrong on both counts: the
number was fabricated (not 3.2, not derived from anything in the result) AND the meaning was
inverted (3.2% is the test-drive-booking rate among those 31 leads, not how often that response
window occurs). Correct phrasing: "31 leads got their first response in 2-24h; of those, 3.2%
went on to book a test drive." Use "n" for volume/frequency claims, "rate_pct" only for
outcome-rate claims, and never blend the two into one number.

⚠ "How many leads [achieved outcome]" (e.g. "how many expressed interest", "how many booked",
"how many were contacted within 30 min") means "true_count", NEVER "n". "n" is the GROUP size
(everyone in that bucket, regardless of outcome); "true_count" is how many of them actually
achieved the outcome. Confirmed 2026-09-22: asked "how many hyperlocal leads expressed interest
in a test drive", a real result of {{"n": 32, "rate_pct": 12.5, "true_count": 4}} was narrated as
"32 expressed interest... which is about 12.5% of that group" -- self-contradictory (32 can't be
both the whole group AND 12.5% of itself) and wrong (the real count that expressed interest was
4, not 32). Never compute n*rate_pct/100 yourself -- true_count is that number, already done.

⚠ "How many leads were contacted/responded to within [time window]" is asking about the
meta_response_window_bucket DIMENSION (which bucket a lead falls into: < 30 min, 30 min - 2h,
2h - 24h, > 24h), NOT an outcome to measure a rate against. Use lead_share (or any metric) with
group_by=["meta_response_window_bucket"] and read "n" for the matching bucket -- do NOT treat
"contacted within 30 min" as if it were an achievement like "booked" or "expressed interest".
Confirmed 2026-09-22: asked "how many hyperlocal leads were contacted within 30 minutes", the
model used an outcome-rate metric and answered "true_count" for booking WITHIN that window
(1 lead) instead of how many leads WERE IN that window at all (the real answer is 10 -- read
directly off the meta_response_window_bucket breakdown, same data used to answer "how fast do
we respond").

⚠ "What % of leads have/are/fall into [category]" is a POPULATION-SHARE question -- use
metric="lead_share" for it, ALWAYS, never an outcome-rate metric. This was tried twice with an
outcome-rate metric plus an extra share_pct field before landing on a dedicated metric: first
the model narrated rate_pct as a population share outright (a real result showed
purchase_interest_rate 50.0% for the tiny IMMEDIATE group, narrated as "50% of leads have
IMMEDIATE timeline" -- wrong, real share was ~0.02%); adding a correctly-computed share_pct
field alongside rate_pct, with explicit instructions to use it, did NOT fix it -- the model kept
reading rate_pct even with the right answer sitting next to it. lead_share results carry NO
rate_pct field at all, only n/share_pct, so there is nothing to misread -- if the question shape
is "what %/share/fraction/proportion of leads...", that is the only metric to reach for.

⚠ FIXED 2026-09-22: query_lead_outcomes CAN now answer "how many X leads do we have" -- use
metric="lead_share", group_by=["is_hyperlocal"] (or another dimension) and read "n" from the
result. This used to be a real gap (before lead_share existed) and the old workaround was to
decline the question -- that's now WRONG and must not be said anymore. Confirmed 2026-09-22: the
exact same question phrased as "how many leads came from the hyperlocal channel" wrongly
declined ("I can't provide a total headcount"), while "is hyperlocal a big or small part of our
lead base" correctly answered with real counts (32 vs 10,216) from the SAME underlying data --
both must route to lead_share now, regardless of phrasing.

get_lead_propensity answers "how likely is THIS ONE specific lead to..." -- as distinct from
query_lead_outcomes's aggregate rate across many leads. It requires a real
source_call_decision_id, which you can only get from a prior tool result or from the user
directly -- never invent or guess one. If neither is available, say plainly you need the lead's
call/decision ID to answer, rather than calling the tool with a made-up value. It runs every
currently-trained propensity model on that one lead in a single call and returns all of them
together (currently: will they be contacted, will they be assigned, and once trained, will they
book a test drive -- a PREVIEW model, blended with hyperlocal data). Some may be REAL, some
PREVIEW, and they can differ per lead.

⚠ ALWAYS state, in the answer itself, when a number is a PREVIEW/early estimate -- never only
when asked. Both get_lead_propensity and get_forecast results carry a "provenance" field for
exactly this reason: whenever it's set to anything other than "REAL" on a result, the number is
an early-stage preview, not a finalized figure, and that should be plain from reading the answer
alone. Confirmed 2026-09-21: asked "how many hyperlocal leads next 24h," a preview forecast was
narrated as "we should expect about 0.2 hyperlocal Meta leads" with no indication it was an early
estimate -- indistinguishable from a finalized number to whoever reads it. Say it plainly in the
same sentence as the number itself, not as a footnote (e.g. "this is an early preview estimate:
~0.2 leads expected"), for every non-"REAL"-provenance result, with no exceptions.

⚠ This is a POC, so keep the language light. The ONLY acceptable words for flagging an
early-stage number are: "preview", "early estimate", "still refining this", "not final" / "not
yet final", "estimate". Do not use any other technical or alarming word to describe this kind of
data, and never quote the provenance field's own raw value back to the user verbatim -- that
value is for your own internal logic only. If you catch yourself about to write a word that isn't
in the approved list above, stop and use "preview" or "estimate" instead. "Preview" and
"estimate" are enough to be honest about a number being early-stage without sounding like the
product is broken or the data isn't trustworthy."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_metric",
            "description": "Look up a real historical business metric, grouped and aggregated "
                            "a chosen way. Use for any question about what already happened.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": sorted(METRICS)},
                    "group_by": {"type": "string", "enum": sorted(DIMENSIONS)},
                    "aggregation": {
                        "type": "string", "enum": sorted(AGGREGATIONS),
                        "description": "sum: total volume in each group -- use this for "
                                        "'busiest'/'highest'/'most calls'-type questions about "
                                        "activity level. count: how many time periods had any "
                                        "activity at all, NOT how much activity -- rarely what "
                                        "a 'busiest'/'highest' question actually means. avg: a "
                                        "typical value per period. max/min: the single highest/"
                                        "lowest period value.",
                    },
                    "date_range": {"type": "string", "enum": sorted(DATE_RANGE_PRESETS)},
                },
                "required": ["metric", "group_by", "aggregation", "date_range"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forecast",
            "description": "Get a forecast for a metric over the next N hours. Use for any "
                            "question about what's expected to happen, not what already did. "
                            "Only up to 24 hours ahead is actually supported right now -- a "
                            "larger request (e.g. for '7 days' or 'next week') gets silently "
                            "capped to 24 hours by the tool, so don't ask for more expecting a "
                            "genuinely longer-range number back.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": sorted(METRICS)},
                    "horizon_hours": {"type": "integer", "default": 24, "maximum": 24},
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_lead_outcomes",
            "description": "Look up a real per-lead outcome rate (e.g. test-drive booking "
                            "rate), grouped by up to two hyperlocal (Meta lead) dimensions at "
                            "once -- e.g. car model AND how fast we called them. Only has data "
                            "for leads that came in through the hyperlocal/Meta/Facebook/"
                            "Instagram channel. Use this instead of query_metric for any "
                            "hyperlocal-lead question, or any question that needs two "
                            "dimensions crossed together.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": sorted(LEAD_METRICS)},
                    "group_by": {
                        "type": "array", "items": {"type": "string", "enum": sorted(LEAD_DIMENSIONS)},
                        "minItems": 1, "maxItems": MAX_LEAD_GROUP_BY_DIMENSIONS,
                        "description": "One dimension for a simple breakdown, two for a "
                                        "cross-tab (e.g. ['product', 'meta_response_window_bucket']).",
                    },
                },
                "required": ["metric", "group_by"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lead_propensity",
            "description": "Get every currently-trained propensity prediction for ONE specific "
                            "real lead in a single call (e.g. will they be contacted, will they "
                            "be assigned, will they book a test drive). Requires a real "
                            "source_call_decision_id from a prior tool result or from the user "
                            "-- never invent one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_call_decision_id": {"type": "string"},
                },
                "required": ["source_call_decision_id"],
            },
        },
    },
]


def _execute_tool(name: str, args: dict, user) -> dict:
    if name == "query_metric":
        try:
            return query_metric.run(args)
        except query_metric.InvalidQuerySpec as exc:
            return {"error": str(exc)}
    if name == "get_forecast":
        try:
            return forecast_tool.run(args["target"], args.get("horizon_hours", 24), user)
        except forecast_tool.ForecastUnavailable as exc:
            return {"error": str(exc)}
    if name == "query_lead_outcomes":
        try:
            return query_lead_outcomes.run(args)
        except query_lead_outcomes.InvalidQuerySpec as exc:
            return {"error": str(exc)}
    if name == "get_lead_propensity":
        try:
            return propensity_tool.run(args["source_call_decision_id"], user)
        except propensity_tool.PropensityUnavailable as exc:
            return {"error": str(exc)}
    return {"error": f"unknown tool {name!r}"}


def run_turn(history: list[dict], user) -> tuple[str, list[dict]]:
    """history: prior turns already in OpenAI message format (role/content/tool_calls/
    tool_call_id), most recent user message included -- the view is responsible for loading/
    saving ConversationMessage rows. Returns (reply_text, new_messages_to_persist), where
    new_messages includes every assistant/tool turn generated this call, not just the final
    reply, so the full tool-call exchange is saved and can be replayed as history next turn."""
    if not settings.OPENAI_API_KEY:
        return "The assistant isn't configured yet — no OpenAI API key is set.", []

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    new_messages: list[dict] = []
    tool_jsons: list[dict] = []  # raw results seen this turn, for the validate step below

    for _ in range(MAX_TOOL_ROUNDS):
        resp = requests.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": "gpt-4o-mini", "messages": messages, "tools": TOOLS,
                "temperature": 0.1, "max_tokens": 500,
            },
            timeout=30,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]

        if not msg.get("tool_calls"):
            reply = msg.get("content") or ""
            reply = _validate_and_correct(reply, tool_jsons, messages)
            new_messages.append({"role": "assistant", "content": reply})
            return reply, new_messages

        messages.append(msg)
        new_messages.append({
            "role": "assistant", "content": msg.get("content") or "",
            "tool_calls": msg["tool_calls"],
        })

        for call in msg["tool_calls"]:
            args = json.loads(call["function"]["arguments"] or "{}")
            result = _execute_tool(call["function"]["name"], args, user)
            tool_jsons.append(result)
            tool_msg = {
                "role": "tool", "tool_call_id": call["id"], "content": json.dumps(result),
            }
            messages.append(tool_msg)
            new_messages.append({**tool_msg, "tool_name": call["function"]["name"]})

    return "Sorry, I couldn't work out an answer to that.", new_messages


def _validate_and_correct(reply: str, tool_jsons: list[dict], messages: list[dict]) -> str:
    """Phase 1 of the generate -> validate -> correct loop (2026-09-22): checks the drafted
    reply against the real tool JSON this turn actually produced -- catches the exact failure
    classes found via manual live testing this session (a fabricated number not present in the
    data; a SIMULATED result narrated with no disclosure) automatically, for any question shape,
    not just ones a human happened to test first. See response_validator.py for the checks
    themselves -- deterministic, no extra LLM cost unless a problem is actually found.

    One corrective retry only -- if the model can't fix it when told exactly what's wrong, a
    second guess is unlikely to do better, and repeatedly retrying risks masking a deeper
    problem (e.g. the tool itself returned something malformed) behind an ever-changing answer."""
    if not tool_jsons:
        return reply  # nothing to ground against (e.g. a pure clarifying question) -- skip

    problems = response_validator.validate(reply, tool_jsons)
    if not problems:
        return reply

    correction_prompt = (
        "Your draft answer has a problem: " + "; ".join(problems) + ". "
        "Rewrite your answer using ONLY numbers and facts that appear in the tool results "
        "already shown above -- do not call any tool again, just correct the wording."
    )
    retry_messages = messages + [
        {"role": "assistant", "content": reply},
        {"role": "user", "content": correction_prompt},
    ]
    resp = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini", "messages": retry_messages,
            "temperature": 0.1, "max_tokens": 500,
        },
        timeout=30,
    )
    resp.raise_for_status()
    corrected = resp.json()["choices"][0]["message"].get("content") or reply

    # Phase 3 (2026-09-22): the retry gets exactly one shot -- if it STILL doesn't pass, don't
    # hand back a second guess that might just be wrong in a new way. Fall back to a
    # deterministic rendering of the real tool JSON (plain string formatting, not generation),
    # guaranteeing no fabricated number or dropped disclosure reaches the user, even at the cost
    # of sounding less natural.
    if response_validator.validate(corrected, tool_jsons):
        return response_validator.render_fallback(tool_jsons)
    return corrected
