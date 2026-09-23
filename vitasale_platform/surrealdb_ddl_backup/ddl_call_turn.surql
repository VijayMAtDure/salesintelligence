-- Turn-level table, added 2026-08-20. One row per conversational turn, linked back to the
-- call-level call_response/call_decision (parent-child design, per user's confirmed instinct).
-- Source: ElevenLabs Conversational AI API (/v1/convai/conversations/{conversation_id}) —
-- real time_in_call_secs and per-turn latency metrics, NOT available anywhere in SurrealDB
-- itself (confirmed 2026-08-20: transcript is a flat text blob, only call-level
-- callStartTime/callEndTime exist). sentiment is NOT provided by ElevenLabs at any level
-- (confirmed: call-level sentiment_analysis is null, no turn has non-null analysis) —
-- field kept for forward-compatibility, deliberately left unpopulated (computing it
-- ourselves would mean an LLM call per turn, breaking Phase 1's deterministic-only rule).

DEFINE TABLE sales_intelligence_call_turn TYPE NORMAL SCHEMAFULL PERMISSIONS FULL;

DEFINE FIELD call_response_id ON sales_intelligence_call_turn TYPE string ASSERT $value != '' PERMISSIONS FULL;
DEFINE FIELD call_decision_id ON sales_intelligence_call_turn TYPE none | string PERMISSIONS FULL;
DEFINE FIELD lead_id ON sales_intelligence_call_turn TYPE string PERMISSIONS FULL;
DEFINE FIELD call_session_id ON sales_intelligence_call_turn TYPE string PERMISSIONS FULL;
DEFINE FIELD turn_index ON sales_intelligence_call_turn TYPE int PERMISSIONS FULL;
DEFINE FIELD role ON sales_intelligence_call_turn TYPE string
  ASSERT $value INSIDE ['AGENT', 'CUSTOMER'] PERMISSIONS FULL;
DEFINE FIELD message ON sales_intelligence_call_turn TYPE string PERMISSIONS FULL;
DEFINE FIELD time_in_call_secs ON sales_intelligence_call_turn TYPE int PERMISSIONS FULL;
DEFINE FIELD turn_timestamp ON sales_intelligence_call_turn TYPE datetime PERMISSIONS FULL;
DEFINE FIELD interrupted ON sales_intelligence_call_turn TYPE bool DEFAULT false PERMISSIONS FULL;
DEFINE FIELD asr_latency_secs ON sales_intelligence_call_turn TYPE none | float PERMISSIONS FULL;
DEFINE FIELD llm_ttfb_secs ON sales_intelligence_call_turn TYPE none | float PERMISSIONS FULL;
DEFINE FIELD tts_ttfb_secs ON sales_intelligence_call_turn TYPE none | float PERMISSIONS FULL;
DEFINE FIELD silence_before_secs ON sales_intelligence_call_turn TYPE none | float PERMISSIONS FULL;
DEFINE FIELD sentiment ON sales_intelligence_call_turn TYPE none | string PERMISSIONS FULL;  -- reserved, always null (no source)
DEFINE FIELD source ON sales_intelligence_call_turn TYPE string DEFAULT 'elevenlabs_api' PERMISSIONS FULL;
DEFINE FIELD feature_version ON sales_intelligence_call_turn TYPE string PERMISSIONS FULL;
DEFINE FIELD generated_at ON sales_intelligence_call_turn TYPE datetime DEFAULT time::now() PERMISSIONS FULL;

DEFINE INDEX sict_call_response_idx ON sales_intelligence_call_turn FIELDS call_response_id, turn_index UNIQUE;
DEFINE INDEX sict_lead_idx ON sales_intelligence_call_turn FIELDS lead_id, turn_timestamp;
DEFINE INDEX sict_session_idx ON sales_intelligence_call_turn FIELDS call_session_id;
