import { apiClient } from "./client";
import type { InferenceJob, Paginated, SampleLead, Track } from "./types";

export async function listInferenceJobs(): Promise<InferenceJob[]> {
  const resp = await apiClient.get<Paginated<InferenceJob>>("/inference/jobs/");
  return resp.data.results;
}

export async function getInferenceJob(id: number): Promise<InferenceJob> {
  return (await apiClient.get<InferenceJob>(`/inference/jobs/${id}/`)).data;
}

export async function createInferenceJob(params: {
  track: Track;
  target: string;
  model_version_id?: number;
  input: Record<string, unknown>;
}): Promise<InferenceJob> {
  return (await apiClient.post<InferenceJob>("/inference/jobs/", params)).data;
}

export async function requestNarrative(id: number): Promise<void> {
  await apiClient.post(`/inference/jobs/${id}/narrative/`);
}

export async function listSampleLeads(limit = 15): Promise<SampleLead[]> {
  return (await apiClient.get<SampleLead[]>("/inference/jobs/sample-leads/", { params: { limit } })).data;
}

export async function runNarrativeSandbox(params: {
  track: Track;
  provenance: "REAL" | "SIMULATED";
  caveat: string;
  evidence: Record<string, unknown>;
}): Promise<string> {
  const resp = await apiClient.post<{ narrative: string }>("/inference/narrative-sandbox/", params);
  return resp.data.narrative;
}
