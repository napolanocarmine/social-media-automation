import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  dispatchDryRun,
  dispatchRun,
  fetchDispatchConfig,
  fetchDueEvents,
  type DuePlanningEvent,
  type DueStoryRule,
} from "../lib/api/client";

function EventsTable({ rows, columns }: { rows: Record<string, unknown>[]; columns: string[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--story-border)]">
      <table className="min-w-full text-left text-sm">
        <thead className="bg-[var(--story-surface)] text-[var(--story-muted)]">
          <tr>
            {columns.map((col) => (
              <th key={col} className="px-3 py-2 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} className="border-t border-[var(--story-border)]">
              {columns.map((col) => (
                <td key={col} className="px-3 py-2 align-top">
                  {String(row[col] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PublishPage() {
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState("tutti");
  const [limit, setLimit] = useState(50);
  const [message, setMessage] = useState<string | null>(null);

  const dueQuery = useQuery({
    queryKey: ["dispatch", "due", platform, limit],
    queryFn: () => fetchDueEvents({ platform, limit }),
    refetchInterval: 30_000,
  });

  const dispatchConfigQuery = useQuery({
    queryKey: ["config", "dispatch"],
    queryFn: fetchDispatchConfig,
  });

  const dryRunMutation = useMutation({
    mutationFn: () => dispatchDryRun({ platform: platform === "tutti" ? undefined : platform, limit }),
    onSuccess: (data) => setMessage(data.message),
    onError: (err: Error) => setMessage(err.message),
  });

  const runMutation = useMutation({
    mutationFn: () => dispatchRun({ platform: platform === "tutti" ? undefined : platform, limit }),
    onSuccess: (data) => {
      setMessage(data.message);
      queryClient.invalidateQueries({ queryKey: ["dispatch"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const planningRows = (dueQuery.data?.planning_events ?? []).map((ev: DuePlanningEvent) => ({
    id: ev.id,
    image_id: ev.image_id,
    platform: ev.platform,
    scheduled_for: ev.scheduled_for,
    gate: ev.dispatch_gate,
    name: ev.image_name,
  }));

  const storyRows = (dueQuery.data?.story_rules ?? []).map((r: DueStoryRule) => ({
    rule_id: r.rule_id,
    image_id: r.image_id,
    platform: r.platform,
    mode: r.schedule_mode,
    slot: r.slot_label,
    occurrence: r.occurrence_key,
  }));

  const busy = dryRunMutation.isPending || runMutation.isPending;

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">⑤ Pubblica</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Dispatch <strong>manuale</strong> degli eventi scaduti verso Meta. Lo scheduler automatico
          (Docker o launchd) gira ogni{" "}
          {dispatchConfigQuery.data?.auto_interval_minutes ?? 10} minuti in background.
        </p>
      </header>

      <section className="space-y-4 rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-4">
        <h3 className="text-sm font-medium">Dispatch manuale</h3>
        <p className="mt-1 text-sm text-[var(--story-muted)]">
          Pubblica subito i post/story scaduti, senza attendere il prossimo ciclo automatico.
          Usa dry-run per vedere cosa verrebbe inviato.
        </p>

      <div className="grid gap-3 md:grid-cols-2">
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
          <span className="text-[var(--story-muted)]">Max eventi</span>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {[20, 50, 100, 200].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      {dueQuery.isLoading ? (
        <p className="text-sm text-[var(--story-muted)]">Caricamento eventi…</p>
      ) : (
        <>
          <p className="text-sm text-[var(--story-muted)]">
            Eventi post pronti: {dueQuery.data?.planning_count ?? 0} · Regole story:{" "}
            {dueQuery.data?.story_count ?? 0}
          </p>

          {planningRows.length === 0 ? (
            <p className="rounded-lg border border-[var(--story-border)] p-4 text-sm text-[var(--story-muted)]">
              Nessun evento post scaduto al momento.
            </p>
          ) : (
            <EventsTable
              rows={planningRows}
              columns={["id", "image_id", "platform", "scheduled_for", "gate", "name"]}
            />
          )}

          {storyRows.length > 0 ? (
            <>
              <h3 className="text-sm font-medium">Regole story dovute</h3>
              <EventsTable
                rows={storyRows}
                columns={["rule_id", "image_id", "platform", "mode", "slot", "occurrence"]}
              />
            </>
          ) : null}
        </>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => runMutation.mutate()}
          className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
        >
          Esegui dispatch ora
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => dryRunMutation.mutate()}
          className="rounded-lg border border-[var(--story-border)] px-4 py-2 text-sm disabled:opacity-50"
        >
          Anteprima dispatch (dry-run)
        </button>
      </div>

      {message ? <p className="text-sm text-[var(--story-muted)]">{message}</p> : null}
      </section>
    </div>
  );
}
