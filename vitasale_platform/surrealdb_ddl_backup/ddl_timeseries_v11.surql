-- sales_intelligence_timeseries re-grained 2026-08-21 to match doc §7 exactly:
-- organisation / showroom / product x fixed time bucket, hourly (doc §8 "1 hour initially").
-- Replaces the original (date x organisation x campaign_id, daily) grain — see aggregates.py
-- header for the full rationale. Table is dropped and recreated; it is fully derived, so no
-- data is lost (rebuilt from sales_intelligence_call_event).

REMOVE TABLE sales_intelligence_timeseries;

DEFINE TABLE sales_intelligence_timeseries TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

-- series keys (doc §7 grain)
DEFINE FIELD bucket_start ON sales_intelligence_timeseries TYPE datetime PERMISSIONS FULL;
DEFINE FIELD bucket ON sales_intelligence_timeseries TYPE string DEFAULT 'hourly' PERMISSIONS FULL;
DEFINE FIELD organisation ON sales_intelligence_timeseries TYPE record<organisation> PERMISSIONS FULL;
DEFINE FIELD showroom_id ON sales_intelligence_timeseries TYPE none | record<showroom> PERMISSIONS FULL;
DEFINE FIELD product_id ON sales_intelligence_timeseries TYPE none | record<master_product_price_list> PERMISSIONS FULL;
-- AutoGluon TimeSeriesDataFrame item_id: one string per series
DEFINE FIELD item_id ON sales_intelligence_timeseries TYPE string PERMISSIONS FULL;

-- volume targets
DEFINE FIELD calls_attempted ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_connected ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD calls_no_response ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD decisions_scored ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD disposition_counts ON sales_intelligence_timeseries TYPE object FLEXIBLE DEFAULT {} PERMISSIONS FULL;
DEFINE FIELD test_drive_interest_yes_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD purchase_interest_yes_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD escalate_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD new_leads_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD avg_talk_duration_seconds ON sales_intelligence_timeseries TYPE none | float PERMISSIONS FULL;

-- rate targets (demand-side; unaffected by operator batch scheduling)
DEFINE FIELD connect_rate ON sales_intelligence_timeseries TYPE none | float PERMISSIONS FULL;
DEFINE FIELD test_drive_interest_rate ON sales_intelligence_timeseries TYPE none | float PERMISSIONS FULL;
DEFINE FIELD purchase_interest_rate ON sales_intelligence_timeseries TYPE none | float PERMISSIONS FULL;

-- known-future covariates (doc §7.2)
DEFINE FIELD hour_of_day ON sales_intelligence_timeseries TYPE int PERMISSIONS FULL;
DEFINE FIELD weekday ON sales_intelligence_timeseries TYPE int PERMISSIONS FULL;
DEFINE FIELD is_business_hours ON sales_intelligence_timeseries TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD active_campaign_count ON sales_intelligence_timeseries TYPE int DEFAULT 0 PERMISSIONS FULL;

DEFINE FIELD feature_version ON sales_intelligence_timeseries TYPE string PERMISSIONS FULL;
DEFINE FIELD generated_at ON sales_intelligence_timeseries TYPE datetime DEFAULT time::now() PERMISSIONS FULL;

DEFINE INDEX sit_bucket_idx ON sales_intelligence_timeseries
  FIELDS bucket_start, organisation, showroom_id, product_id UNIQUE;
DEFINE INDEX sit_item_idx ON sales_intelligence_timeseries FIELDS item_id, bucket_start;
