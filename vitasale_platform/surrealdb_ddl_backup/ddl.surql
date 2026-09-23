-- Phase 1 new tables. See PHASE1_PHASE2_EXECUTION_FLOW.md Stages 2/4/5/6 for the field-by-field
-- rationale. Additive only — never touches existing raw tables (doc's "raw stays unchanged").
-- Run once: surreal sql --endpoint http://127.0.0.1:8000 -u root -p root --ns salesdb2 --db salesdb2 < ddl.surql

-- ============================================================
-- Stage 2: sales_intelligence_call_event
-- ============================================================
DEFINE TABLE sales_intelligence_call_event TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

DEFINE FIELD event_id ON sales_intelligence_call_event TYPE string
  ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD lead_id ON sales_intelligence_call_event TYPE string PERMISSIONS FULL;
DEFINE FIELD organisation ON sales_intelligence_call_event TYPE record<organisation> PERMISSIONS FULL;
DEFINE FIELD campaign_id ON sales_intelligence_call_event TYPE none | string PERMISSIONS FULL;
DEFINE FIELD event_type ON sales_intelligence_call_event TYPE string
  ASSERT $value INSIDE [
    'CALL_ATTEMPTED', 'CALL_CONNECTED', 'CALL_DECISION_SCORED',
    'FOLLOWUP_SCHEDULED', 'FOLLOWUP_EXECUTED', 'RETRY_SCHEDULED', 'RETRY_EXECUTED',
    'CUSTOMER_MESSAGE', 'AGENT_MESSAGE'
  ] PERMISSIONS FULL;
DEFINE FIELD event_timestamp ON sales_intelligence_call_event TYPE datetime PERMISSIONS FULL;
DEFINE FIELD actor ON sales_intelligence_call_event TYPE string
  ASSERT $value INSIDE ['CUSTOMER', 'VITASALE', 'DEALER', 'SYSTEM', 'CAMPAIGN'] PERMISSIONS FULL;
DEFINE FIELD channel ON sales_intelligence_call_event TYPE string
  ASSERT $value INSIDE ['VOICE', 'WHATSAPP', 'EMAIL', 'WEB'] PERMISSIONS FULL;
DEFINE FIELD source_table ON sales_intelligence_call_event TYPE string PERMISSIONS FULL;
DEFINE FIELD source_id ON sales_intelligence_call_event TYPE string PERMISSIONS FULL;
DEFINE FIELD parent_event_id ON sales_intelligence_call_event TYPE none | string PERMISSIONS FULL;
DEFINE FIELD payload ON sales_intelligence_call_event TYPE object FLEXIBLE PERMISSIONS FULL;
DEFINE FIELD feature_version ON sales_intelligence_call_event TYPE string PERMISSIONS FULL;
DEFINE FIELD generated_at ON sales_intelligence_call_event TYPE datetime DEFAULT time::now() PERMISSIONS FULL;

DEFINE INDEX sice_event_id_idx ON sales_intelligence_call_event FIELDS event_id UNIQUE;
DEFINE INDEX sice_lead_idx ON sales_intelligence_call_event FIELDS lead_id, event_timestamp;
DEFINE INDEX sice_type_idx ON sales_intelligence_call_event FIELDS event_type;
DEFINE INDEX sice_source_idx ON sales_intelligence_call_event FIELDS source_table, source_id;

-- ============================================================
-- Stage 4: sales_intelligence_feature_snapshot
-- ============================================================
DEFINE TABLE sales_intelligence_feature_snapshot TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

DEFINE FIELD lead_id ON sales_intelligence_feature_snapshot TYPE string PERMISSIONS FULL;
DEFINE FIELD organisation ON sales_intelligence_feature_snapshot TYPE record<organisation> PERMISSIONS FULL;
DEFINE FIELD campaign_id ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD snapshot_at ON sales_intelligence_feature_snapshot TYPE datetime PERMISSIONS FULL;
DEFINE FIELD bucket ON sales_intelligence_feature_snapshot TYPE string DEFAULT 'event' PERMISSIONS FULL;
DEFINE FIELD source_call_decision_id ON sales_intelligence_feature_snapshot TYPE string
  ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD parent_event_id ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD attempt_number ON sales_intelligence_feature_snapshot TYPE none | int PERMISSIONS FULL;

-- Disposition
DEFINE FIELD disposition_latest ON sales_intelligence_feature_snapshot TYPE string PERMISSIONS FULL;
DEFINE FIELD disposition_history ON sales_intelligence_feature_snapshot TYPE array DEFAULT [] PERMISSIONS FULL;
DEFINE FIELD "disposition_history.*" ON sales_intelligence_feature_snapshot TYPE string PERMISSIONS FULL;

-- Engagement / counts
DEFINE FIELD messages_customer ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD messages_agent ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD total_interactions ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;

-- Sentiment
DEFINE FIELD sentiment_latest ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD sentiment_velocity ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD sentiment_mean ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD sentiment_min ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD sentiment_max ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;

-- Intent / qualification
DEFINE FIELD purchase_interest_latest ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD purchase_interest_velocity ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD test_drive_interest_flag ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD intent_tags_latest ON sales_intelligence_feature_snapshot TYPE array DEFAULT [] PERMISSIONS FULL;
DEFINE FIELD "intent_tags_latest.*" ON sales_intelligence_feature_snapshot TYPE string PERMISSIONS FULL;
DEFINE FIELD qualification_score ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;  -- always null, descoped

-- NBA
DEFINE FIELD nba_generated ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD nba_completed ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD nba_overdue ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD nba_priority_latest ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;

-- Objections / context
DEFINE FIELD competitor_mentions ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD finance_interest_ever ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD escalate_flag ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD assign_rep_flag ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD whatsapp_sent_count ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;

-- Followups / retries
DEFINE FIELD followups_scheduled ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD followups_completed ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD followups_cancelled ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD followups_exhausted ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD followup_latency_minutes ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD retries_pending ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;

-- Call volume
DEFINE FIELD calls_total ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_connected ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_no_response ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;

-- Recency / latency
DEFINE FIELD days_in_pipeline ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD pipeline_velocity ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;  -- always null, descoped
DEFINE FIELD days_since_last_call ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD time_to_first_response_minutes ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD avg_dealer_response_minutes ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;  -- pending source

-- Momentum (descriptive, doc §10)
DEFINE FIELD momentum_score ON sales_intelligence_feature_snapshot TYPE none | int PERMISSIONS FULL;
DEFINE FIELD momentum_state ON sales_intelligence_feature_snapshot TYPE none | string
  ASSERT $value = NONE OR $value INSIDE ['HIGH', 'STABLE', 'DECLINING', 'STALLED'] PERMISSIONS FULL;

-- Dimensions
DEFINE FIELD showroom_id ON sales_intelligence_feature_snapshot TYPE none | record<showroom> PERMISSIONS FULL;
DEFINE FIELD product_id ON sales_intelligence_feature_snapshot TYPE none | record<master_product_price_list> PERMISSIONS FULL;

-- Outcome (always null, descoped) + versioning
DEFINE FIELD outcome ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD feature_version ON sales_intelligence_feature_snapshot TYPE string PERMISSIONS FULL;
DEFINE FIELD generated_at ON sales_intelligence_feature_snapshot TYPE datetime DEFAULT time::now() PERMISSIONS FULL;

DEFINE INDEX sifs_source_call_decision_idx ON sales_intelligence_feature_snapshot
  FIELDS source_call_decision_id UNIQUE;
DEFINE INDEX sifs_lead_idx ON sales_intelligence_feature_snapshot FIELDS lead_id, snapshot_at;
DEFINE INDEX sifs_campaign_idx ON sales_intelligence_feature_snapshot FIELDS campaign_id;

-- ============================================================
-- Stage 5: sales_intelligence_timeseries
-- ============================================================
DEFINE TABLE sales_intelligence_timeseries TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

DEFINE FIELD date ON sales_intelligence_timeseries TYPE string
  ASSERT string::len($value) = 10 PERMISSIONS FULL;  -- 'YYYY-MM-DD', IST calendar day
DEFINE FIELD organisation ON sales_intelligence_timeseries TYPE record<organisation> PERMISSIONS FULL;
DEFINE FIELD campaign_id ON sales_intelligence_timeseries TYPE none | string PERMISSIONS FULL;
DEFINE FIELD calls_attempted ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_connected ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_no_response ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD disposition_counts ON sales_intelligence_timeseries TYPE object FLEXIBLE DEFAULT {} PERMISSIONS FULL;
DEFINE FIELD test_drive_interest_yes_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD purchase_interest_yes_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD escalate_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD new_leads_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD avg_talk_duration_seconds ON sales_intelligence_timeseries TYPE none | float PERMISSIONS FULL;
DEFINE FIELD feature_version ON sales_intelligence_timeseries TYPE string PERMISSIONS FULL;
DEFINE FIELD generated_at ON sales_intelligence_timeseries TYPE datetime DEFAULT time::now() PERMISSIONS FULL;

DEFINE INDEX sit_bucket_idx ON sales_intelligence_timeseries
  FIELDS date, organisation, campaign_id UNIQUE;

-- ============================================================
-- Stage 6: sales_intelligence_job_state
-- ============================================================
DEFINE TABLE sales_intelligence_job_state TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

DEFINE FIELD job_name ON sales_intelligence_job_state TYPE string ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD last_processed_call_decision_id ON sales_intelligence_job_state TYPE none | string PERMISSIONS FULL;
DEFINE FIELD last_processed_at ON sales_intelligence_job_state TYPE none | datetime PERMISSIONS FULL;
DEFINE FIELD feature_version ON sales_intelligence_job_state TYPE string PERMISSIONS FULL;
DEFINE FIELD last_run_at ON sales_intelligence_job_state TYPE datetime DEFAULT time::now() PERMISSIONS FULL;
DEFINE FIELD status ON sales_intelligence_job_state TYPE string
  ASSERT $value INSIDE ['SUCCESS', 'FAILED', 'RUNNING'] PERMISSIONS FULL;

DEFINE INDEX sijs_job_name_idx ON sales_intelligence_job_state FIELDS job_name UNIQUE;
