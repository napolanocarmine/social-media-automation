import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { BatchProgressBanner } from "../components/BatchProgressBanner";
import {
  fetchActiveBatch,
  fetchBatchDetail,
  fetchBatchList,
  prepareWeek,
  stopBatch,
  type BatchSummary,
} from "../lib/api/client";

function PrepareWeekPanel() {
  const [days, setDays] = useState(7);
  const [dryRun, setDryRun] = useState(true);
  const [tryRender, setTryRender] = useState(true);
  const [result, setResult] = useState<Awaited<ReturnType<typeof prepareWeek>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => prepareWeek({ days, dry_run: dryRun, try_render: tryRender }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setResult(null);
    },
  });

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--story-muted)]">
        Per ogni slot libero in <code>config/schedule.yaml</code>: processa foto mancanti,
        auto-approva se Story AI OK, pianifica con caption.
      </p>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Giorni da coprire</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {[7, 14, 21].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-end gap-2 text-sm">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
          />
          Solo simulazione (dry-run)
        </label>
        <label className="flex items-end gap-2 text-sm">
          <input
            type="checkbox"
            checked={tryRender}
            onChange={(e) => setTryRender(e.target.checked)}
            disabled={dryRun}
          />
          Processa Drive→Story AI se mancano immagini
        </label>
      </div>
      <button
        type="button"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
        className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
      >
        {mutation.isPending ? "Preparazione in corso…" : "Avvia preparazione settimanale"}
      </button>
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      {result ? (
        <div className="space-y-3 rounded-xl border border-[var(--story-border)] p-4 text-sm">
          <p className="text-green-400">{result.message}</p>
          <p className="text-[var(--story-muted)]">Schedule: {result.schedule_path}</p>
          {result.errors.length > 0 ? (
            <ul className="list-disc pl-5 text-amber-200">
              {result.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          ) : null}
          {result.skipped_borderline > 0 ? (
            <p className="text-[var(--story-muted)]">
              {result.skipped_borderline} immagine/i da rivedere in ③ Approva.
            </p>
          ) : null}
          {!result.dry_run && result.planned > 0 ? (
            <Link
              to="/workflow/publish"
              className="inline-block text-[var(--story-accent)] underline"
            >
              Vai a ⑤ Pubblica
            </Link>
          ) : null}
          {result.assignments.length > 0 ? (
            <pre className="max-h-64 overflow-auto rounded-lg bg-[var(--story-bg)] p-3 text-xs">
              {JSON.stringify(result.assignments, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function BatchDashboard() {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("tutti");
  const [platform, setPlatform] = useState("tutti");
  const [format, setFormat] = useState("tutti");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const listQuery = useQuery({
    queryKey: ["batches", "list", status, platform, format],
    queryFn: () =>
      fetchBatchList({
        status,
        platform,
        format,
        limit: 50,
      }),
    refetchInterval: 5000,
  });

  const detailQuery = useQuery({
    queryKey: ["batches", "detail", selectedId],
    queryFn: () => fetchBatchDetail(selectedId!),
    enabled: selectedId != null,
    refetchInterval: selectedId != null ? 2000 : false,
  });

  const stopMutation = useMutation({
    mutationFn: (batchId: number) => stopBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
    },
  });

  const rows = listQuery.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => {
            const running = rows.find((r) => r.status === "running");
            if (running) setSelectedId(running.id);
          }}
          className="rounded-lg border border-[var(--story-border)] px-3 py-2 text-sm"
        >
          Apri ultimo batch running
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Stato</span>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {["tutti", "running", "completed", "partial", "failed", "cancelled"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Social</span>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            <option value="tutti">Tutti</option>
            <option value="instagram">Instagram</option>
            <option value="facebook">Facebook</option>
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Formato</span>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            <option value="tutti">Tutti</option>
            <option value="post">Post</option>
            <option value="story">Story</option>
          </select>
        </label>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-[var(--story-muted)]">Nessun batch con i filtri correnti.</p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[var(--story-border)]">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-[var(--story-surface)] text-[var(--story-muted)]">
              <tr>
                {["id", "status", "category", "platform", "media_format", "progress_pct", "done_count"].map(
                  (col) => (
                    <th key={col} className="px-3 py-2 font-medium">
                      {col}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row: BatchSummary) => (
                <tr
                  key={row.id}
                  className={[
                    "cursor-pointer border-t border-[var(--story-border)]",
                    selectedId === row.id ? "bg-[var(--story-accent)]/10" : "",
                  ].join(" ")}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="px-3 py-2">#{row.id}</td>
                  <td className="px-3 py-2">{row.status}</td>
                  <td className="px-3 py-2">{row.category ?? "—"}</td>
                  <td className="px-3 py-2">{row.platform ?? "—"}</td>
                  <td className="px-3 py-2">{row.media_format ?? "post"}</td>
                  <td className="px-3 py-2">{row.progress_pct}%</td>
                  <td className="px-3 py-2">
                    {row.done_count}/{row.requested_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedId != null && detailQuery.data ? (
        <div className="rounded-xl border border-[var(--story-border)] p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-medium">Batch #{selectedId}</h3>
            {detailQuery.data.batch.status === "running" ? (
              <button
                type="button"
                disabled={stopMutation.isPending}
                onClick={() => stopMutation.mutate(selectedId)}
                className="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-200"
              >
                Richiedi stop
              </button>
            ) : null}
          </div>
          <p className="mb-3 text-sm text-[var(--story-muted)]">
            {detailQuery.data.batch.completed_count} ok · {detailQuery.data.batch.failed_count}{" "}
            errori · {detailQuery.data.batch.progress_pct}%
          </p>
          <ul className="max-h-48 space-y-1 overflow-auto text-xs text-[var(--story-muted)]">
            {detailQuery.data.items.map((item) => (
              <li key={item.id}>
                #{item.item_index + 1} · {item.status}
                {item.source_asset_name ? ` · ${item.source_asset_name}` : ""}
                {item.error_message ? ` · ${item.error_message}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function AutomationPage() {
  const [tab, setTab] = useState<"prepare" | "batches">("prepare");

  const activeQuery = useQuery({
    queryKey: ["batches", "active"],
    queryFn: fetchActiveBatch,
    refetchInterval: 3000,
  });

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">Automazione</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Prepara la settimana editoriale e monitora le code batch Story AI.
        </p>
      </header>

      {activeQuery.data ? <BatchProgressBanner batchId={activeQuery.data.id} /> : null}

      <div className="flex gap-2 border-b border-[var(--story-border)]">
        {(
          [
            ["prepare", "Prepara settimana"],
            ["batches", "Monitor batch"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={[
              "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === id
                ? "border-[var(--story-accent)] text-[var(--story-accent)]"
                : "border-transparent text-[var(--story-muted)] hover:text-[var(--story-text)]",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "prepare" ? <PrepareWeekPanel /> : <BatchDashboard />}
    </div>
  );
}
