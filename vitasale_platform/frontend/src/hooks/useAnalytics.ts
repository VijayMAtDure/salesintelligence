import { useQuery } from "@tanstack/react-query";
import { getNbaEffectiveness, getResponseWindow, getResponseWindowSim, getSystemMap } from "../api/analytics";

export function useNbaEffectiveness() {
  return useQuery({
    queryKey: ["nba-effectiveness"],
    queryFn: getNbaEffectiveness,
  });
}

export function useResponseWindow() {
  return useQuery({
    queryKey: ["response-window"],
    queryFn: getResponseWindow,
  });
}

export function useResponseWindowSim() {
  return useQuery({
    queryKey: ["response-window-sim"],
    queryFn: getResponseWindowSim,
  });
}

export function useSystemMap() {
  return useQuery({
    queryKey: ["system-map"],
    queryFn: getSystemMap,
  });
}
