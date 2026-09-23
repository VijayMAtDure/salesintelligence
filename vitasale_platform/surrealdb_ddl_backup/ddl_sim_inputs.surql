-- Simulated INPUT tables, 2026-08-26.
--
-- ⚠️ ALL DATA IN THESE TABLES IS FABRICATED.
--
-- These fill the remaining gaps that block doc §9 use cases, so the analysis pipeline can be
-- completed and tested end-to-end. Each table mirrors the shape of the real data we expect,
-- so swapping simulated -> real is a source change, not a schema change.
--
-- Every table name ends in _sim and every row carries is_simulated = true.

-- =========================================================================================
-- 1. Rep capacity  -> unblocks §9 use case 1 (sales workload forecast)
--    "Tomorrow forecast: 68-76 qualified leads; dealer capacity is only 55"
--    Real source when available: KIFS staffing roster.
-- =========================================================================================
DEFINE TABLE sales_intelligence_capacity_sim TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;
DEFINE FIELD is_simulated ON sales_intelligence_capacity_sim TYPE bool DEFAULT true
  ASSERT $value = true PERMISSIONS FULL;
DEFINE FIELD organisation ON sales_intelligence_capacity_sim TYPE record<organisation> PERMISSIONS FULL;
DEFINE FIELD showroom_id ON sales_intelligence_capacity_sim TYPE none | record<showroom> PERMISSIONS FULL;
DEFINE FIELD date ON sales_intelligence_capacity_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD reps_available ON sales_intelligence_capacity_sim TYPE int PERMISSIONS FULL;
DEFINE FIELD leads_per_rep_per_day ON sales_intelligence_capacity_sim TYPE int PERMISSIONS FULL;
DEFINE FIELD total_capacity ON sales_intelligence_capacity_sim TYPE int PERMISSIONS FULL;
DEFINE FIELD sim_version ON sales_intelligence_capacity_sim TYPE string PERMISSIONS FULL;
DEFINE INDEX sics_date_idx ON sales_intelligence_capacity_sim FIELDS date, organisation UNIQUE;

-- =========================================================================================
-- 2. Objection tags -> unblocks §9 use case 7 (product intelligence)
--    Doc §6 asks for "price, competitor, financing, delivery objections where structured
--    data permits". No structured tag exists upstream.
--    NOTE: the REAL path here is LLM extraction from call_turn.message (48,681 words of
--    actual customer speech). This simulation is a placeholder so the downstream analysis
--    can be built and tested; it should be replaced by extraction, not by client data.
-- =========================================================================================
DEFINE TABLE sales_intelligence_objection_sim TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;
DEFINE FIELD is_simulated ON sales_intelligence_objection_sim TYPE bool DEFAULT true
  ASSERT $value = true PERMISSIONS FULL;
DEFINE FIELD source_call_decision_id ON sales_intelligence_objection_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD lead_id ON sales_intelligence_objection_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD snapshot_at ON sales_intelligence_objection_sim TYPE datetime PERMISSIONS FULL;
DEFINE FIELD price_objection ON sales_intelligence_objection_sim TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD delivery_objection ON sales_intelligence_objection_sim TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD competitor_objection ON sales_intelligence_objection_sim TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD finance_objection ON sales_intelligence_objection_sim TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD objection_count ON sales_intelligence_objection_sim TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD product_id ON sales_intelligence_objection_sim TYPE none | record<master_product_price_list> PERMISSIONS FULL;
DEFINE FIELD sim_version ON sales_intelligence_objection_sim TYPE string PERMISSIONS FULL;
DEFINE INDEX sios2_decision_idx ON sales_intelligence_objection_sim FIELDS source_call_decision_id UNIQUE;

-- =========================================================================================
-- 3. Peer dealer -> unblocks §9 use case 6 (dealer benchmarking)
--    This pilot has exactly ONE dealer (KIFS Volvo), so there is nothing to benchmark
--    against. A synthetic peer is generated purely so the comparison logic can be built.
--    ⚠️ THE PEER DOES NOT EXIST. Any "KIFS vs peer" number is meaningless until a real
--    second dealer is onboarded.
-- =========================================================================================
DEFINE TABLE sales_intelligence_peer_dealer_sim TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;
DEFINE FIELD is_simulated ON sales_intelligence_peer_dealer_sim TYPE bool DEFAULT true
  ASSERT $value = true PERMISSIONS FULL;
DEFINE FIELD dealer_name ON sales_intelligence_peer_dealer_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD date ON sales_intelligence_peer_dealer_sim TYPE string PERMISSIONS FULL;
DEFINE FIELD calls_attempted ON sales_intelligence_peer_dealer_sim TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_connected ON sales_intelligence_peer_dealer_sim TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD connect_rate ON sales_intelligence_peer_dealer_sim TYPE none | float PERMISSIONS FULL;
DEFINE FIELD median_response_mins ON sales_intelligence_peer_dealer_sim TYPE none | float PERMISSIONS FULL;
DEFINE FIELD test_drives_booked ON sales_intelligence_peer_dealer_sim TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD test_drives_held ON sales_intelligence_peer_dealer_sim TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD wins ON sales_intelligence_peer_dealer_sim TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD sim_version ON sales_intelligence_peer_dealer_sim TYPE string PERMISSIONS FULL;
DEFINE INDEX sipd_idx ON sales_intelligence_peer_dealer_sim FIELDS dealer_name, date UNIQUE;
