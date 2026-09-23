import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cancelPipelineRun, createPipelineRun, getPipelinePreview, listPipelineRuns } from "../api/pipeline";
import type { PipelineMode } from "../api/types";

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING"]);

export function usePipelineRuns() {
  return useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: () => listPipelineRuns(),
    refetchInterval: (query) => {
      const runs = query.state.data;
      return runs?.some((r) => ACTIVE_STATUSES.has(r.status)) ? 2000 : false;
    },
  });
}

export function useCreatePipelineRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { mode: PipelineMode; feature_version: string }) => createPipelineRun(params),
    onSettled: () => qc.invalidateQueries({ queryKey: ["pipeline-runs"] }),
  });
}

export function useCancelPipelineRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => cancelPipelineRun(id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["pipeline-runs"] }),
  });
}

export function usePipelinePreview(id: number | null) {
  return useQuery({
    queryKey: ["pipeline-preview", id],
    queryFn: () => getPipelinePreview(id as number),
    enabled: id !== null,
  });
}
