-- feature_version 1.2 additions, 2026-08-26.
-- Derived features only — every one computed from columns already present. No new source
-- data required. Additive; nothing existing is changed or dropped.

-- doc §6 ratio forms. Scale-invariant where the raw counts are not: 5 interruptions across
-- 40 turns is a different conversation from 5 across 8. NULL (not 0) when the denominator
-- is absent, so "no data" stays distinguishable from "genuinely zero".
DEFINE FIELD connect_rate_lead ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD followup_completion_rate ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD interruption_rate ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD turns_per_minute ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD calls_per_day_in_pipeline ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD nba_completion_rate ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;

-- Territory. NOT in doc §6 — added because the CRM outcome analysis showed this is the
-- variable separating commercially useful leads from wasted ones, and no behavioural
-- feature can see it (out-of-territory leads were the MOST engaged group).
DEFINE FIELD territory_status ON sales_intelligence_feature_snapshot TYPE string
  DEFAULT 'unknown'
  ASSERT $value INSIDE ['in_territory','out_of_territory','unknown'] PERMISSIONS FULL;

-- Cyclical time encoding. Raw hour_of_day tells a model 23:00 and 00:00 are maximally
-- distant when they are adjacent; sin/cos pairs fix that.
DEFINE FIELD is_weekend ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD hour_sin ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD hour_cos ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD weekday_sin ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD weekday_cos ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD territory_source ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;  -- ai_extracted | salesforce
DEFINE FIELD territory_city ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
