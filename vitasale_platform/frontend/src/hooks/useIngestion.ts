import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getIngestionPreview, listIngestionJobs, pullDb, uploadCsv } from "../api/ingestion";

const ACTIVE_STATUSES = new Set(["QUEUED", "RUNNING"]);

export function useIngestionJobs() {
  return useQuery({
    queryKey: ["ingestion-jobs"],
    queryFn: () => listIngestionJobs(),
    refetchInterval: (query) => {
      const jobs = query.state.data;
      return jobs?.some((j) => ACTIVE_STATUSES.has(j.status)) ? 2000 : false;
    },
  });
}

export function useUploadCsv() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, targetTable }: { file: File; targetTable: string }) => uploadCsv(file, targetTable),
    onSettled: () => qc.invalidateQueries({ queryKey: ["ingestion-jobs"] }),
  });
}

export function usePullDb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: "INCREMENTAL" | "FULL") => pullDb(mode),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["ingestion-jobs"] });
      qc.invalidateQueries({ queryKey: ["pipeline-runs"] });
    },
  });
}

export function useIngestionPreview(id: number | null) {
  return useQuery({
    queryKey: ["ingestion-preview", id],
    queryFn: () => getIngestionPreview(id as number),
    enabled: id !== null,
  });
}
