// Mirrors apps/*/serializers.py field-for-field. Kept in one file since the backend is the
// source of truth and these should never drift silently from it.

export type JobStatus = "PENDING" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
export type Track = "FORECAST" | "PROPENSITY";
export type Transform = "RAW" | "LOG1P" | null;
export type Provenance = "REAL" | "SIMULATED";

export interface EventItem {
  id: number;
  event_type: string;
  timestamp: string;
  detail: Record<string, unknown>;
  gpu_host?: string;
  stage?: string | null;
}

export interface TrainingJob {
  id: number;
  track: Track;
  target: string;
  transform: Transform;
  preset: string;
  status: JobStatus;
  queue_position: number | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  gpu_host: string;
  failure_reason: string;
  error_message: string;
  events: EventItem[];
}

export interface ModelVersion {
  id: number;
  track: Track;
  target: string;
  version_label: string;
  feature_version: string;
  model_name: string;
  validation_metric: string;
  validation_score: number;
  validation_method: string;
  artifact_path: string;
  is_latest: boolean;
  provenance: Provenance;
  caveat: string;
  created_at: string;
  training_job: number;
}

export type PipelineMode = "BACKFILL" | "INCREMENTAL" | "REBUILD" | "VALIDATE";

export interface PipelineRun {
  id: number;
  mode: PipelineMode;
  feature_version: string;
  status: JobStatus;
  current_stage: string | null;
  started_at: string | null;
  finished_at: string | null;
  rows_processed: Record<string, number>;
  validation_results: Record<string, unknown>;
  error_message: string;
  events: EventItem[];
  created_at: string;
}

export interface UploadedFile {
  id: number;
  original_filename: string;
  target_table: string;
  row_count: number | null;
  validation_errors: string[];
  created_at: string;
}

export interface IngestionJob {
  id: number;
  job_type: "CSV_UPLOAD" | "DB_PULL";
  mode: "INCREMENTAL" | "FULL";
  uploaded_file: UploadedFile | null;
  status: JobStatus;
  started_at: string | null;
  finished_at: string | null;
  rows_ingested: number | null;
  watermark_before: string | null;
  watermark_after: string | null;
  error_message: string;
  events: EventItem[];
  created_at: string;
}

export interface SampleLead {
  source_call_decision_id: string;
  lead_id: string;
  disposition_latest: string | null;
  sentiment_latest: number | null;
  territory_status: string | null;
}

export interface InferenceJob {
  id: number;
  track: Track;
  target: string;
  model_version: ModelVersion;
  input_payload: Record<string, unknown>;
  status: JobStatus;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown>;
  narrative: string;
  error_message: string;
  created_at: string;
}

export interface ApiConflict<T> {
  detail: string;
  active_job?: T;
  active_run?: T;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
