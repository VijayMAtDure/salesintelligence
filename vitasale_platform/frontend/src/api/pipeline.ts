import { apiClient } from "./client";
import type { Paginated, PipelineMode, PipelineRun } from "./types";

export async function listPipelineRuns(status?: string): Promise<PipelineRun[]> {
  const resp = await apiClient.get<Paginated<PipelineRun>>("/pipeline/runs/", {
    params: status ? { status } : {},
  });
  return resp.data.results;
}

export async function getPipelineRun(id: number): Promise<PipelineRun> {
  return (await apiClient.get<PipelineRun>(`/pipeline/runs/${id}/`)).data;
}

export async function createPipelineRun(params: {
  mode: PipelineMode;
  feature_version: string;
}): Promise<PipelineRun> {
  return (await apiClient.post<PipelineRun>("/pipeline/runs/", params)).data;
}

export async function cancelPipelineRun(id: number): Promise<PipelineRun> {
  return (await apiClient.post<PipelineRun>(`/pipeline/runs/${id}/cancel/`)).data;
}

export async function getPipelinePreview(
  id: number,
  limit = 20
): Promise<{ feature_snapshot_sample: Record<string, unknown>[]; timeseries_sample: Record<string, unknown>[] }> {
  return (await apiClient.get(`/pipeline/runs/${id}/preview/`, { params: { limit } })).data;
}
