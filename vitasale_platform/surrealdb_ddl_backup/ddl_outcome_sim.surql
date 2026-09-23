-- sales_intelligence_outcome_sim — SIMULATED outcome data, 2026-08-25.
--
-- ⚠️ THIS TABLE CONTAINS FABRICATED DATA. IT IS NOT REAL.
--
-- Purpose: exercise the outcome-join and model-training path end-to-end so the pipeline is
-- ready the moment real KIFS outcome data arrives. Explicitly NOT for drawing conclusions —
-- outcomes here are generated from rules we invented, so any model trained on them merely
-- recovers our own assumptions. Nothing from this table may be reported as a finding.
--
-- Real KIFS data, when it arrives, goes to a SEPARATE table (sales_intelligence_outcome).
-- Kept apart deliberately so the two can never be mixed by accident.
--
-- Mirrors the field list requested in KIFS_DATA_REQUIREMENT.md, so swapping simulated for
-- real data later is a table-name change, not a schema change.

DEFINE TABLE sales_intelligence_outcome_sim TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

-- provenance — non-negotiable, every row is flagged
DEFINE FIELD is_simulated ON sales_intelligence_outcome_sim TYPE bool DEFAULT true
  ASSERT $value = true PERMISSIONS FULL;
DEFINE FIELD sim_version ON sales_intelligence_outcome_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD sim_seed ON sales_intelligence_outcome_sim TYPE int PERMISSIONS FULL;

-- join keys back to real data
DEFINE FIELD source_call_decision_id ON sales_intelligence_outcome_sim TYPE string
  ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD lead_id ON sales_intelligence_outcome_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD contact_id ON sales_intelligence_outcome_sim TYPE none | string PERMISSIONS FULL;

-- Tier 1 fields (KIFS_DATA_REQUIREMENT.md §3.1)
DEFINE FIELD assigned_at ON sales_intelligence_outcome_sim TYPE none | datetime PERMISSIONS FULL;
DEFINE FIELD first_contact_at ON sales_intelligence_outcome_sim TYPE none | datetime PERMISSIONS FULL;
DEFINE FIELD final_outcome ON sales_intelligence_outcome_sim TYPE string
  ASSERT $value INSIDE ['won','lost','open','no_show','never_contacted'] PERMISSIONS FULL;
DEFINE FIELD outcome_reason ON sales_intelligence_outcome_sim TYPE none | string PERMISSIONS FULL;

-- derived latencies (the whole point of the exercise)
DEFINE FIELD nba_to_assign_mins ON sales_intelligence_outcome_sim TYPE none | float PERMISSIONS FULL;
DEFINE FIELD nba_to_contact_mins ON sales_intelligence_outcome_sim TYPE none | float PERMISSIONS FULL;
DEFINE FIELD assign_to_contact_mins ON sales_intelligence_outcome_sim TYPE none | float PERMISSIONS FULL;

-- test drive (§3.3)
DEFINE FIELD td_scheduled_at ON sales_intelligence_outcome_sim TYPE none | datetime PERMISSIONS FULL;
DEFINE FIELD td_happened ON sales_intelligence_outcome_sim TYPE none | bool PERMISSIONS FULL;
DEFINE FIELD td_status ON sales_intelligence_outcome_sim TYPE none | string PERMISSIONS FULL;

-- attempts (§3.2) — array of {attempt_no, attempted_at, channel, result}
DEFINE FIELD contact_attempts ON sales_intelligence_outcome_sim TYPE array DEFAULT [] PERMISSIONS FULL;
DEFINE FIELD attempt_count ON sales_intelligence_outcome_sim TYPE int DEFAULT 0 PERMISSIONS FULL;

-- enrichment (§3.4 / tier 2)
DEFINE FIELD salesperson ON sales_intelligence_outcome_sim TYPE none | string PERMISSIONS FULL;
DEFINE FIELD vehicle_purchased ON sales_intelligence_outcome_sim TYPE none | string PERMISSIONS FULL;
DEFINE FIELD deal_value ON sales_intelligence_outcome_sim TYPE none | number PERMISSIONS FULL;
DEFINE FIELD competitor_brand ON sales_intelligence_outcome_sim TYPE none | string PERMISSIONS FULL;

DEFINE FIELD generated_at ON sales_intelligence_outcome_sim TYPE datetime DEFAULT time::now() PERMISSIONS FULL;

DEFINE INDEX sios_decision_idx ON sales_intelligence_outcome_sim FIELDS source_call_decision_id UNIQUE;
DEFINE INDEX sios_lead_idx ON sales_intelligence_outcome_sim FIELDS lead_id;
DEFINE INDEX sios_outcome_idx ON sales_intelligence_outcome_sim FIELDS final_outcome;
DEFINE FIELD contact_attempts[*] ON sales_intelligence_outcome_sim TYPE object FLEXIBLE PERMISSIONS FULL;  -- attempt rows: {attempt_no, attempted_at, channel, result}
