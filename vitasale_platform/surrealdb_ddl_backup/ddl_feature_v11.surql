-- feature_version 1.1 additions, 2026-08-21. Closes doc §6/§6.2/§7.2/§10/§20 gaps found in
-- the final scope audit. Additive only — no existing field changed or dropped.

-- §10 Sales Momentum Score: was emitting only 2 of the 5 required outputs.
DEFINE FIELD momentum_change ON sales_intelligence_feature_snapshot TYPE none | int PERMISSIONS FULL;
DEFINE FIELD top_positive_signal ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD top_negative_signal ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;

-- §7.2 known-future covariates / §20 timezone-risk mitigation (evaluated in business_tz).
DEFINE FIELD hour_of_day ON sales_intelligence_feature_snapshot TYPE none | int PERMISSIONS FULL;
DEFINE FIELD weekday ON sales_intelligence_feature_snapshot TYPE none | int PERMISSIONS FULL;
DEFINE FIELD is_business_hours ON sales_intelligence_feature_snapshot TYPE none | bool PERMISSIONS FULL;

-- §6 Engagement family — newly buildable from sales_intelligence_call_turn (Stage 2c).
-- engagement_depth is the empirically validated interested-vs-not differentiator.
DEFINE FIELD conversation_duration_secs ON sales_intelligence_feature_snapshot TYPE none | int PERMISSIONS FULL;
DEFINE FIELD customer_turns ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD agent_turns ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD total_turns ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD interruptions ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD customer_agent_ratio ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;
DEFINE FIELD engagement_depth ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD re_engagement_count ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;

-- §6 Latency family: AI_processing_time (mean llm_ttfb + tts_ttfb per call).
DEFINE FIELD ai_processing_time_secs ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;

-- §6.2 explicit field.
DEFINE FIELD last_customer_gap_minutes ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;

-- §6 Sentiment family: negative-to-positive recovery.
DEFINE FIELD sentiment_recovery ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;

-- §6 Channel family.
DEFINE FIELD channel_dominant ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD channel_first ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD channel_last ON sales_intelligence_feature_snapshot TYPE none | string PERMISSIONS FULL;
DEFINE FIELD channel_switches ON sales_intelligence_feature_snapshot TYPE int DEFAULT 0 PERMISSIONS FULL;
DEFINE FIELD is_multi_channel ON sales_intelligence_feature_snapshot TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD avg_silence_before_secs ON sales_intelligence_feature_snapshot TYPE none | float PERMISSIONS FULL;  -- §6 Engagement: dead air before agent turns (0.9s interested vs 1.4s not)
