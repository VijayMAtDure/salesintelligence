import { apiClient } from "./client";
import type { ModelVersion, Paginated, Track, Transform, TrainingJob } from "./types";

export async function listTrainingJobs(status?: string): Promise<TrainingJob[]> {
  const resp = await apiClient.get<Paginated<TrainingJob>>("/training/jobs/", {
    params: status ? { status } : {},
  });
  return resp.data.results;
}

export async function getTrainingJob(id: number): Promise<TrainingJob> {
  return (await apiClient.get<TrainingJob>(`/training/jobs/${id}/`)).data;
}

export async function createTrainingJob(params: {
  track: Track;
  target: string;
  transform?: Transform;
  preset?: string;
}): Promise<TrainingJob> {
  const resp = await apiClient.post<TrainingJob>("/training/jobs/", params);
  return resp.data;
}

export async function cancelTrainingJob(id: number): Promise<TrainingJob> {
  return (await apiClient.post<TrainingJob>(`/training/jobs/${id}/cancel/`)).data;
}

export async function listModelVersions(params?: {
  track?: string;
  target?: string;
}): Promise<ModelVersion[]> {
  const resp = await apiClient.get<Paginated<ModelVersion>>("/training/models/", { params });
  return resp.data.results;
}

export async function promoteModelVersion(id: number): Promise<ModelVersion> {
  return (await apiClient.post<ModelVersion>(`/training/models/${id}/promote/`)).data;
}
