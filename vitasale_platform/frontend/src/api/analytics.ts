import { apiClient } from "./client";

export interface NbaEffectivenessRow {
  priority: string;
  n: number;
  acted_on: number;
  acted_on_pct: number | null;
}

export interface NbaEffectivenessResult {
  provenance: "REAL" | "SIMULATED";
  caveat: string;
  breakdown: NbaEffectivenessRow[];
  total_outcome_rows: number;
  total_feature_rows: number;
  unmatched_rows: number;
  sim_seed: number;
}

export async function getNbaEffectiveness(): Promise<NbaEffectivenessResult> {
  return (await apiClient.get<NbaEffectivenessResult>("/analytics/nba-effectiveness/")).data;
}

export interface ResponseWindowRow {
  window: string;
  n: number;
  pct_of_all_nba: number | null;
  test_drive_booked: number;
  purchase_interest_yes_count: number;
  purchase_interest_yes_pct: number | null;
}

export interface ResponseWindowResult {
  provenance: "REAL" | "SIMULATED";
  caveat: string;
  breakdown: ResponseWindowRow[];
  total_nba_suggested: number;
  total_test_drives_booked: number;
  unmatched_rows: number;
  sim_seed: number;
}

export async function getResponseWindow(): Promise<ResponseWindowResult> {
  return (await apiClient.get<ResponseWindowResult>("/analytics/response-window/")).data;
}

export interface ResponseWindowSimRow {
  window: string;
  n: number;
  pct_of_all_nba: number | null;
  test_drive_booked: number;
  test_drive_booked_pct: number | null;
}

export interface ResponseWindowSimResult {
  provenance: "REAL" | "SIMULATED";
  caveat: string;
  breakdown: ResponseWindowSimRow[];
  total_nba_suggested: number;
  total_test_drives_booked: number;
  unmatched_rows: number;
  sim_seed: number;
}

export async function getResponseWindowSim(): Promise<ResponseWindowSimResult> {
  return (await apiClient.get<ResponseWindowSimResult>("/analytics/response-window-sim/")).data;
}

export interface SourceTable {
  name: string;
  row_count: number;
  provenance: "REAL" | "SIMULATED";
  description: string;
  fields_used: string[];
}

export interface DerivedTable {
  name: string;
  row_count: number;
  provenance: "REAL" | "SIMULATED";
  description: string;
}

export interface FlowSection {
  page?: string;
  options?: string[];
  note?: string;
  description?: string;
}

export interface SystemMapResult {
  source_tables: SourceTable[];
  derived_tables: DerivedTable[];
  pipeline_stages: { name: string; description: string }[];
  pipeline_modes: { name: string; description: string }[];
  normalization: { name: string; description: string }[];
  flow: {
    ingestion: FlowSection;
    transform: FlowSection;
    training: FlowSection;
    inference: FlowSection;
    sandbox: FlowSection;
    analytics: FlowSection;
    assistant: FlowSection;
  };
  predictions: {
    forecast_targets: number;
    propensity_targets: number;
    simulated_demo_variants: number;
    total_selectable_in_predict_ui: number;
    analytics_cards: number;
    forecast_target_list: NamedItem[];
    propensity_target_list: NamedItem[];
    simulated_demo_list: NamedItem[];
    analytics_card_list: NamedItem[];
  };
}

export interface NamedItem {
  key: string;
  label: string;
  blurb: string;
}

export async function getSystemMap(): Promise<SystemMapResult> {
  return (await apiClient.get<SystemMapResult>("/analytics/system-map/")).data;
}
