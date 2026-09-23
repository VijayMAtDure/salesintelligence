import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createInferenceJob,
  getInferenceJob,
  listInferenceJobs,
  listSampleLeads,
  requestNarrative,
  runNarrativeSandbox,
} from "../api/inference";
import type { Track } from "../api/types";

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING"]);

export function useInferenceJobs() {
  return useQuery({
    queryKey: ["inference-jobs"],
    queryFn: () => listInferenceJobs(),
    refetchInterval: (query) => {
      const jobs = query.state.data;
      // also keep polling while a narrative is being generated (job succeeded, no narrative yet)
      const pendingNarrative = jobs?.some((j) => j.status === "SUCCEEDED" && j.narrative === "" && j.finished_at);
      return jobs?.some((j) => ACTIVE_STATUSES.has(j.status)) || pendingNarrative ? 2000 : false;
    },
  });
}

export function useInferenceJob(id: number | null) {
  return useQuery({
    queryKey: ["inference-job", id],
    queryFn: () => getInferenceJob(id as number),
    enabled: id !== null,
    refetchInterval: (query) => {
      const job = query.state.data;
      if (!job) return false;
      const active = ACTIVE_STATUSES.has(job.status);
      const pendingNarrative = job.status === "SUCCEEDED" && job.narrative === "";
      return active || pendingNarrative ? 1500 : false;
    },
  });
}

export function useCreateInferenceJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { track: Track; target: string; input: Record<string, unknown> }) =>
      createInferenceJob(params),
    onSettled: () => qc.invalidateQueries({ queryKey: ["inference-jobs"] }),
  });
}

export function useRequestNarrative() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => requestNarrative(id),
    onSettled: (_data, _err, id) => {
      qc.invalidateQueries({ queryKey: ["inference-job", id] });
      qc.invalidateQueries({ queryKey: ["inference-jobs"] });
    },
  });
}

export function useSampleLeads() {
  return useQuery({
    queryKey: ["sample-leads"],
    queryFn: () => listSampleLeads(15),
  });
}

export function useNarrativeSandbox() {
  return useMutation({ mutationFn: runNarrativeSandbox });
}
