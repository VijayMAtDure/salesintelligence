import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  cancelTrainingJob,
  createTrainingJob,
  listModelVersions,
  listTrainingJobs,
  promoteModelVersion,
} from "../api/training";
import type { Track, Transform } from "../api/types";

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING"]);

/** Polls every 2s while ANY job is QUEUED/RUNNING, stops polling once everything is
 * terminal — avoids hammering the API once there's nothing left to watch. */
export function useTrainingJobs() {
  return useQuery({
    queryKey: ["training-jobs"],
    queryFn: () => listTrainingJobs(),
    refetchInterval: (query) => {
      const jobs = query.state.data;
      return jobs?.some((j) => ACTIVE_STATUSES.has(j.status)) ? 2000 : false;
    },
  });
}

/** ⚠️ FIXED 2026-09-03: the GPU status widget used to reuse useTrainingJobs() above, which
 * calls listTrainingJobs() with no status filter -- that hits /training/jobs/ unfiltered,
 * which DRF paginates at PAGE_SIZE=25 ordered OLDEST first (TrainingJob.Meta.ordering =
 * ["queued_at"], a deliberate FIFO order for the queue view). Once more than 25 jobs have ever
 * been created, page 1 can never contain a recent job again -- the widget was structurally
 * blind to anything currently running, not just unlucky about polling timing. Querying by
 * status directly sidesteps pagination entirely, since there are only ever a handful of
 * QUEUED/RUNNING jobs at once regardless of how much history exists. Always polls (this is a
 * cheap, small, filtered query) rather than conditionally like the full list above.*/
export function useActiveTrainingStatus() {
  return useQuery({
    queryKey: ["training-jobs-active"],
    queryFn: async () => {
      const [running, queued] = await Promise.all([
        listTrainingJobs("RUNNING"),
        listTrainingJobs("QUEUED"),
      ]);
      return { running: running[0] ?? null, queuedCount: queued.length };
    },
    refetchInterval: 2000,
  });
}

export function useCreateTrainingJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { track: Track; target: string; transform?: Transform; preset?: string }) =>
      createTrainingJob(params),
    onSettled: () => qc.invalidateQueries({ queryKey: ["training-jobs"] }),
  });
}

export function useCancelTrainingJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => cancelTrainingJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["training-jobs"] }),
  });
}

export function useModelVersions(params?: { track?: string; target?: string }) {
  return useQuery({
    queryKey: ["model-versions", params],
    queryFn: () => listModelVersions(params),
  });
}

export function usePromoteModelVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => promoteModelVersion(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-versions"] }),
  });
}
