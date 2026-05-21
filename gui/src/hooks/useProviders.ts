import { useQuery } from "@tanstack/react-query";
import { mockApi } from "@/api/mock";

export function useProviders() {
  return useQuery({
    queryKey: ["providers"],
    queryFn: () => mockApi.getProviders(),
    staleTime: 60_000,
  });
}

export function useSkills() {
  return useQuery({
    queryKey: ["skills"],
    queryFn: () => mockApi.getSkills(),
    staleTime: 30_000,
  });
}