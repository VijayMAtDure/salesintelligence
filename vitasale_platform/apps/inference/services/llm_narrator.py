"""
Turns a structured inference result into a plain-language explanation via OpenAI — doc §15's
"Strategic Intelligence Handoff" pattern: the LLM consumes structured evidence and explains
it, it never infers statistics directly from raw data or invents numbers not already in the
result. Raw HTTP, no SDK — same convention as apps.datastore.surreal_client (fewer moving
parts, no dependency on the SDK's own versioning).
"""
import requests
from django.conf import settings

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

SYSTEM_PROMPT = """You explain a machine learning model's prediction to a sales manager at a
Volvo dealership in India. You are given a JSON object with the prediction and the real
features/data that produced it — you must use ONLY the numbers in that JSON. Never invent a
number, percentage, or fact that isn't already present in the input.

The input includes "target_description" — this states EXACTLY what the prediction measures.
Use that description precisely. Do not substitute your own guess at what the model predicts
(e.g. if the target is "will this lead be contacted", do not describe it as "will this lead
buy" or "convert into a sale" — those are different, materially unrelated questions, and
this project deliberately avoided predicting purchase/sale outcomes because there wasn't
enough real data for it).

Write in the exact same natural, confident tone for every prediction, regardless of any
"provenance" value or anything the input's "caveat" text says about data source. Never use or
reference the words "simulated," "demo," "illustrative," "synthetic," "fabricated," "fake," or
any other phrasing that comments on whether the underlying data is real — describe the
prediction and its evidence the same way you would for any other prediction. (Disclosure of
data provenance is handled elsewhere in the product, not in this explanation — your job here is
only to explain what the number says and why.)

Write for a dealership owner or salesperson with no data/statistics background — someone who
has never heard the words "median," "forecast total," "p10/p90," "MASE," "validation score,"
"aggregate," or "rate" used as a technical term, and never will. Do not use any of those words
or others like them. Turn every number into plain, concrete, spoken-out-loud language instead:
- A proportion or probability (e.g. 0.83) becomes a percentage or a simple count, not a
  decimal — "about 8 in 10 calls" or "83%," never "a median value of 0.83."
- A predicted count over a time window becomes a plain statement of what to expect — "expect
  around 240 calls to connect today," not "the forecast total is 242, with a p10 of 1.4 and a
  p90 of 736."
- Do not mention uncertainty ranges (p10/p90) or model/statistical mechanics at all — just
  state the expected number plainly, the way you'd tell a colleague over the phone.

Write 3-5 sentences: what the prediction says (using target_description precisely, translated
into plain language) and what evidence drove it, in the same everyday language. Do not add a
caveat, limitation, or reliability warning of your own — the input will never ask you for one,
and inventing one (about data volume, timing, confidence, or anything else) is exactly the kind
of unsupported claim you must never make. If the input gives you nothing to explain a number
beyond the number itself, just state the number plainly and stop — do not manufacture a reason
to be cautious about it. No preamble, no "Based on the data provided" — just the explanation
itself.

⚠ On citing evidence: if the input includes specific feature values (e.g. a "features_used"
object, or named fields like a feature score), reference 2-3 of THOSE SPECIFIC values by name
and value. If the input does NOT include feature-level detail — only a prediction number and
maybe aggregate context — do not invent typical-sounding feature names ("engagement score",
"time since last interaction", etc.) to sound more evidenced than you are. Confirmed
2026-08-31: told to "reference 2-3 specific feature values" even with none present in the
input, the model fabricated plausible-sounding ones — a real hallucination. When no feature
detail is given, just explain the number itself; do not pad with invented specifics."""

# Human-readable meaning of each target — passed to the LLM explicitly so it never has to
# guess (see the "convert into a sale" bug this fixed: label_contacted got narrated as
# purchase propensity because nothing told the model what the target actually represents).
TARGET_DESCRIPTIONS = {
    "label_contacted": "the probability this lead will be successfully reached/contacted by "
                        "a sales rep — NOT the probability of a sale or purchase",
    "label_assigned": "the probability this lead will be assigned to a sales rep — NOT the "
                       "probability of a sale or purchase",
    "calls_attempted": "forecasted number of outbound call attempts in the coming hours",
    "calls_connected": "forecasted number of calls that will successfully connect",
    "new_leads_count": "forecasted number of new leads entering the pipeline",
    "connect_rate": "forecasted proportion of attempted calls that connect",
    "purchase_interest_rate": "forecasted proportion of calls where the customer expresses "
                               "purchase interest",
    "purchase_interest_yes_count": "forecasted count of calls with expressed purchase interest",
    "test_drive_interest_rate": "forecasted proportion of calls expressing test-drive interest",
    "retries_scheduled": "forecasted number of retry attempts scheduled",
    "retries_executed": "forecasted number of retry attempts carried out",
    "followups_due": "forecasted number of follow-ups coming due",
    "followups_completed": "forecasted number of follow-ups completed",
}


# Per-target guidance for turning a forecast into an operational recommendation — added for
# the "business-actionable narrative" request (2026-08-31): a forecast number on its own
# ("connect_rate will be 0.41") isn't something a showroom manager can act on. This tells the
# LLM WHICH operational lever each target maps to, WITHOUT inventing any ratio or fact not
# already in the evidence.
#
# ⚠️ REP-CAPACITY ATTRIBUTION FIXED 2026-09-02: every hint used to frame its number as
# dealership-staff workload ("your team," "reps," "people free"). Confirmed directly by the
# user: outbound calling/connecting is done by the ElevenLabs AI voice agent, not staff, and a
# human dealership rep only gets pulled in for a CONFIRMED subset of leads — test-drive
# interest (this forecast target) and Selekt/certified-pre-owned program interest
# (call_decision.selekt_interest, not currently a forecast target). Every hint below that isn't
# test_drive_interest_rate has had staff/rep/headcount language removed rather than guessed at
# a second time — described neutrally (what the number means, what trend to watch) instead of
# asserting who acts on it.
OPERATIONAL_HINTS = {
    "calls_attempted": "This is how many outbound calls the calling system will place. Just "
                        "state the expected volume and whether it's trending up or down from "
                        "what's typical — this workload is handled automatically, not by "
                        "dealership staff, so don't frame it as a staffing question.",
    "calls_connected": "This is how many of those calls are expected to actually reach a "
                        "person. State the expected volume plainly and note the trend — this is "
                        "handled automatically, not by dealership staff, so don't frame it as a "
                        "staffing question.",
    "new_leads_count": "This is how many new customers are expected to enter the pipeline. "
                        "State the expected volume and the trend — do not frame this as a "
                        "staffing question.",
    "connect_rate": "Describe this as how often calls are getting through to a real person, in "
                     "plain terms (e.g. 'about 4 in 10 calls connect'). Note whether it looks "
                     "low or high and whether it's trending up or down.",
    "purchase_interest_rate": "Describe this as how many customers on calls are showing real "
                               "buying interest, in plain terms, and note the trend — a rising "
                               "share is a good sign for the leads already in the pipeline, "
                               "even if call volume is flat.",
    "purchase_interest_yes_count": "Each one of these is a real customer who showed buying "
                                    "interest during a call. State the expected count plainly "
                                    "and note the trend, as a sign of the pipeline's quality.",
    "test_drive_interest_rate": "Describe this as how many customers are asking for a test "
                                 "drive, in plain terms. If the evidence also includes an "
                                 "'expected_test_drives' number, use that specific number to say "
                                 "how many staff need to be free to take customers on drives, "
                                 "since a test drive is one of the few things a dealership "
                                 "person personally handles — each one needs someone along for "
                                 "the ride.",
    "retries_scheduled": "This is how many re-contact attempts are queued up for the coming "
                          "hours. State the expected volume plainly.",
    "retries_executed": "This is how many re-contact attempts have actually gone out. If the "
                         "evidence also shows how many were scheduled: if fewer went out than "
                         "scheduled, say plainly that attempts are piling up and need attention. "
                         "If more went out than scheduled, that just means earlier queued "
                         "attempts are being cleared — say that plainly too, don't describe it "
                         "as a problem.",
    "followups_due": "These are follow-up tasks coming due today. State the expected volume "
                      "plainly and note that follow-ups lose value the longer they wait.",
    "followups_completed": "If the evidence also shows how many follow-ups are due, compare the "
                            "two and say plainly whether completions are keeping pace.",
}

FORECAST_SYSTEM_PROMPT = SYSTEM_PROMPT + """

This prediction is a FORECAST, being read by a showroom/dealership manager who needs to
understand what's coming and what to actually do about it, not just see a number. The evidence
includes an "operational_hint" field with plain-language guidance already written for you —
follow that reasoning using ONLY the numbers already in the evidence (predicted counts or
derived numbers like "expected_test_drives"). Do not assume dealership staff personally handle
every activity you're forecasting — most outbound calling happens automatically; the
operational_hint tells you when (and only when) a specific number of staff is genuinely
relevant. Never invent a staffing number, percentage, or count that isn't in the evidence or
explicitly licensed by the operational_hint text (e.g. "a test drive needs one accompanying
rep" is a stated business rule, not an invented statistic — you may use it; a specific number
of reps you were not given is not).

End your explanation with one final sentence starting "Recommended action:" that gives a
concrete, plain-language recommendation — phrased like advice to a colleague, not a report
finding. Only recommend a staffing action where the operational_hint actually supports one; for
most targets the right recommendation is about a trend to watch or a practical next step, not
a headcount."""


class LLMNotConfiguredError(Exception):
    pass


def _base_target(target: str | None) -> str | None:
    """Strip a "_sim" suffix so a simulated variant is described/hinted identically to its real
    counterpart — the narrative should read the same for both. Disclosure of data provenance is
    the badge/caveat banner's job elsewhere in the UI, not this explanation's."""
    if target and target.endswith("_sim"):
        return target[: -len("_sim")]
    return target


def generate_forecast_narrative(evidence: dict, provenance: str, caveat: str = "") -> str:
    """Forecast-specific narrative: evidence is pre-built by the caller (aggregated forecast
    totals, optional real capacity_sim figures, optional cross-target derived counts like
    expected_test_drives) — this function only adds target_description/operational_hint and
    calls the LLM. Kept separate from generate_narrative() because PROPENSITY predictions (a
    single lead's probability) have no "operational hint"/aggregation concept at all."""
    if not settings.OPENAI_API_KEY:
        raise LLMNotConfiguredError("OPENAI_API_KEY is not configured")

    target = evidence.get("target")
    lookup_target = _base_target(target)
    full_evidence = {
        k: v for k, v in evidence.items()
        if k != "capacity_provenance"  # a "SIMULATED" label, not a number the LLM needs
    }
    full_evidence.update({
        "target_description": TARGET_DESCRIPTIONS.get(
            lookup_target,
            f"unknown target '{lookup_target}' — no description available, do not guess its meaning"),
        "operational_hint": OPERATIONAL_HINTS.get(lookup_target, "No specific operational hint for "
                             "this target — give a monitoring-style recommendation only."),
    })
    # ⚠️ FIXED 2026-09-02: caveat text (both SIMULATED provenance disclosures AND a REAL
    # target's own data-sufficiency note, e.g. "24h horizon is marginal... real gaps") used to
    # be passed to the LLM (softened, for REAL targets) — confirmed this still reads badly
    # ("it's important to note the data has some gaps, which may affect reliability") and lands
    # right next to the UI's own caveat banner as an unwanted second, LLM-paraphrased warning.
    # The caveat banner already discloses this reliably and structurally; this explanation
    # doesn't need to repeat it in any form. caveat/provenance are accepted as parameters
    # (call sites still pass them) purely for interface symmetry — never added to LLM input.
    del caveat, provenance  # deliberately unused — see note above

    resp = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": FORECAST_SYSTEM_PROMPT},
                {"role": "user", "content": str(full_evidence)},
            ],
            "temperature": 0.3,
            "max_tokens": 350,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def generate_narrative(prediction_result: dict, provenance: str, caveat: str = "") -> str:
    if not settings.OPENAI_API_KEY:
        raise LLMNotConfiguredError("OPENAI_API_KEY is not configured")

    del caveat, provenance  # never sent to the LLM — see generate_forecast_narrative's note

    target = prediction_result.get("target")
    lookup_target = _base_target(target)
    evidence = {
        **prediction_result,
        "target_description": TARGET_DESCRIPTIONS.get(
            lookup_target,
            f"unknown target '{lookup_target}' — no description available, do not guess its meaning"),
    }

    resp = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": str(evidence)},
            ],
            "temperature": 0.3,
            "max_tokens": 300,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()
