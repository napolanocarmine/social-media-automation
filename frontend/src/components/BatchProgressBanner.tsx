import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchActiveBatch, fetchBatchDetail, stopBatch } from "../lib/api/client";

type BatchProgressBannerProps = {
  batchId?: number | null;
};

export function BatchProgressBanner({ batchId }: BatchProgressBannerProps) {
  const queryClient = useQueryClient();
  const activeQuery = useQuery({
    queryKey: ["batches", "active"],
    queryFn: fetchActiveBatch,
    refetchInterval: (query) => {
      const status = query.state.data?.status?.toLowerCase();
      return status === "running" ? 2000 : false;
    },
    enabled: batchId == null,
  });

  const resolvedId = batchId ?? activeQuery.data?.id ?? null;

  const detailQuery = useQuery({
    queryKey: ["batches", resolvedId],
    queryFn: () => fetchBatchDetail(resolvedId!),
    enabled: resolvedId != null,
    refetchInterval: (query) => {
      const status = query.state.data?.batch.status?.toLowerCase();
      return status === "running" ? 2000 : false;
    },
  });

  const stopMutation = useMutation({
    mutationFn: (id: number) => stopBatch(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["images"] });
    },
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });

  const batch = detailQuery.data?.batch;
  if (!batch) {
    return null;
  }

  const isRunning = batch.status.toLowerCase() === "running";
  const progress = batch.requested_count > 0 ? batch.done_count / batch.requested_count : 0;

  return (
    <section className="rounded-xl border border-[var(--story-accent)]/30 bg-[var(--story-accent)]/10 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-medium">Coda batch #{batch.id}</h3>
          <p className="mt-1 text-sm text-[var(--story-muted)]">
            Stato: {batch.status} · completati {batch.completed_count} · errori{" "}
            {batch.failed_count} · {batch.done_count}/{batch.requested_count}
          </p>
          {batch.last_error && (
            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-red-200">
              Ultimo errore: {batch.last_error}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {isRunning && (
            <button
              type="button"
              disabled={stopMutation.isPending}
              onClick={() => stopMutation.mutate(batch.id)}
              className="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-200"
            >
              Interrompi
            </button>
          )}
          {!isRunning && (
            <Link
              to="/workflow/approve"
              className="rounded-lg bg-[var(--story-accent)] px-3 py-1.5 text-sm font-semibold text-black"
            >
              Vai ad Approva →
            </Link>
          )}
        </div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-black/30">
        <div
          className="h-full bg-[var(--story-accent)] transition-all"
          style={{ width: `${Math.round(progress * 100)}%` }}
        />
      </div>
    </section>
  );
}
