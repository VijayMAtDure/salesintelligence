-- sales_intelligence_model_run + sales_intelligence_prediction, 2026-08-26.
-- Doc §13 (MDB write model) + §14 (prediction output contract) + §16 acceptance criterion
-- "Persistence | Forecasts/model runs queryable from MDB." Until now, all model outputs sat
-- in CSVs/JSON on the GPU training server — not queryable from the DB. This closes that gap.
--
-- §14's contract is forecast-shaped (target_timestamp, p10/p50/p90). Extended minimally for
-- propensity (per-lead probability, no timestamp horizon) rather than forcing it into the
-- forecast shape — see field comments below for which fields apply to which track.

DEFINE TABLE OVERWRITE sales_intelligence_model_run TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;
DEFINE FIELD OVERWRITE model_run_id ON sales_intelligence_model_run TYPE string ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD OVERWRITE track ON sales_intelligence_model_run TYPE string
  ASSERT $value INSIDE ['forecast', 'propensity'] PERMISSIONS FULL;
DEFINE FIELD OVERWRITE target ON sales_intelligence_model_run TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE model_name ON sales_intelligence_model_run TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE models_trained ON sales_intelligence_model_run TYPE array DEFAULT [] PERMISSIONS FULL;
DEFINE FIELD OVERWRITE models_trained[*] ON sales_intelligence_model_run TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE leaderboard ON sales_intelligence_model_run TYPE array DEFAULT [] PERMISSIONS FULL;
DEFINE FIELD OVERWRITE leaderboard[*] ON sales_intelligence_model_run TYPE object FLEXIBLE PERMISSIONS FULL;
DEFINE FIELD OVERWRITE feature_version ON sales_intelligence_model_run TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE validation_metric ON sales_intelligence_model_run TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE validation_score ON sales_intelligence_model_run TYPE float PERMISSIONS FULL;
DEFINE FIELD OVERWRITE n_rows ON sales_intelligence_model_run TYPE none | int PERMISSIONS FULL;
DEFINE FIELD OVERWRITE n_series ON sales_intelligence_model_run TYPE none | int PERMISSIONS FULL;       -- forecast only
DEFINE FIELD OVERWRITE positives ON sales_intelligence_model_run TYPE none | int PERMISSIONS FULL;      -- propensity only
DEFINE FIELD OVERWRITE horizon_hours ON sales_intelligence_model_run TYPE none | int PERMISSIONS FULL;  -- forecast only
-- REAL vs SIMULATED — the single most important field on this table. Any consumer must
-- check this before treating validation_score as evidence about real customers.
DEFINE FIELD OVERWRITE provenance ON sales_intelligence_model_run TYPE string
  ASSERT $value INSIDE ['REAL', 'SIMULATED_LABELS'] PERMISSIONS FULL;
DEFINE FIELD OVERWRITE caveat ON sales_intelligence_model_run TYPE none | string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE trained_at ON sales_intelligence_model_run TYPE datetime PERMISSIONS FULL;
DEFINE FIELD OVERWRITE training_host ON sales_intelligence_model_run TYPE string DEFAULT 'gpu-204.12.205.2' PERMISSIONS FULL;
DEFINE FIELD OVERWRITE generated_at ON sales_intelligence_model_run TYPE datetime DEFAULT time::now() PERMISSIONS FULL;
DEFINE INDEX OVERWRITE simr_run_idx ON sales_intelligence_model_run FIELDS model_run_id UNIQUE;
DEFINE INDEX OVERWRITE simr_target_idx ON sales_intelligence_model_run FIELDS target;

DEFINE TABLE OVERWRITE sales_intelligence_prediction TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;
DEFINE FIELD OVERWRITE prediction_id ON sales_intelligence_prediction TYPE string ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD OVERWRITE model_run_id ON sales_intelligence_prediction TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE track ON sales_intelligence_prediction TYPE string
  ASSERT $value INSIDE ['forecast', 'propensity'] PERMISSIONS FULL;
DEFINE FIELD OVERWRITE target ON sales_intelligence_prediction TYPE string PERMISSIONS FULL;
-- forecast dimensions (doc §14) — null for propensity rows
DEFINE FIELD OVERWRITE organisation ON sales_intelligence_prediction TYPE none | record<organisation> PERMISSIONS FULL;
DEFINE FIELD OVERWRITE showroom_id ON sales_intelligence_prediction TYPE none | record<showroom> PERMISSIONS FULL;
DEFINE FIELD OVERWRITE product_id ON sales_intelligence_prediction TYPE none | record<master_product_price_list> PERMISSIONS FULL;
DEFINE FIELD OVERWRITE item_id ON sales_intelligence_prediction TYPE none | string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE forecast_at ON sales_intelligence_prediction TYPE datetime PERMISSIONS FULL;
DEFINE FIELD OVERWRITE target_timestamp ON sales_intelligence_prediction TYPE none | datetime PERMISSIONS FULL;  -- forecast only
DEFINE FIELD OVERWRITE p10 ON sales_intelligence_prediction TYPE none | float PERMISSIONS FULL;
DEFINE FIELD OVERWRITE p50 ON sales_intelligence_prediction TYPE none | float PERMISSIONS FULL;
DEFINE FIELD OVERWRITE p90 ON sales_intelligence_prediction TYPE none | float PERMISSIONS FULL;
-- propensity-specific — null for forecast rows
DEFINE FIELD OVERWRITE lead_id ON sales_intelligence_prediction TYPE none | string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE source_call_decision_id ON sales_intelligence_prediction TYPE none | string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE probability ON sales_intelligence_prediction TYPE none | float PERMISSIONS FULL;
DEFINE FIELD OVERWRITE model_name ON sales_intelligence_prediction TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE model_version ON sales_intelligence_prediction TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE feature_version ON sales_intelligence_prediction TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE validation_metric ON sales_intelligence_prediction TYPE string PERMISSIONS FULL;
DEFINE FIELD OVERWRITE provenance ON sales_intelligence_prediction TYPE string
  ASSERT $value INSIDE ['REAL', 'SIMULATED_LABELS'] PERMISSIONS FULL;
DEFINE FIELD OVERWRITE generated_at ON sales_intelligence_prediction TYPE datetime DEFAULT time::now() PERMISSIONS FULL;
DEFINE INDEX OVERWRITE sip_pred_idx ON sales_intelligence_prediction FIELDS prediction_id UNIQUE;
DEFINE INDEX OVERWRITE sip_run_idx ON sales_intelligence_prediction FIELDS model_run_id;
DEFINE INDEX OVERWRITE sip_target_idx ON sales_intelligence_prediction FIELDS target;
