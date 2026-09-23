import { apiClient } from "./client";
import type { IngestionJob, Paginated } from "./types";

export async function listIngestionJobs(): Promise<IngestionJob[]> {
  const resp = await apiClient.get<Paginated<IngestionJob>>("/ingestion/jobs/");
  return resp.data.results;
}

export async function getIngestionJob(id: number): Promise<IngestionJob> {
  return (await apiClient.get<IngestionJob>(`/ingestion/jobs/${id}/`)).data;
}

export async function uploadCsv(file: File, targetTable: string): Promise<IngestionJob | { detail: string; existing_job: IngestionJob }> {
  const form = new FormData();
  form.append("file", file);
  form.append("target_table", targetTable);
  const resp = await apiClient.post("/ingestion/jobs/upload-csv/", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function pullDb(mode: "INCREMENTAL" | "FULL"): Promise<{
  ingestion_job: IngestionJob;
  pipeline_run: unknown;
}> {
  return (await apiClient.post("/ingestion/jobs/pull-db/", { mode })).data;
}

export async function getIngestionPreview(
  id: number,
  limit = 20
): Promise<{ sample: Record<string, unknown>[] }> {
  return (await apiClient.get(`/ingestion/jobs/${id}/preview/`, { params: { limit } })).data;
}
