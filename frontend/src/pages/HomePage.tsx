import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  fetchDashboardStats,
  fetchSuggestedNextStep,
} from "../lib/api/client";
import { getErrorMessage } from "../lib/api/errors";
import { ErrorNotice } from "../components/ErrorNotice";

const workflowRouteByPage: Record<string, string> = {
  "① Seleziona": "/workflow/select",
  "② Output AI": "/workflow/output",
  "③ Approva": "/workflow/approve",
  "④ Pianifica": "/workflow/plan",
  "⑤ Pubblica": "/workflow/publish",
};

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-4">
      <p className="text-sm text-[var(--story-muted)]">{label}</p>
      <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export function HomePage() {
  const statsQuery = useQuery({
    queryKey: ["dashboard", "stats"],
    queryFn: fetchDashboardStats,
    refetchInterval: 30_000,
  });
  const nextStepQuery = useQuery({
    queryKey: ["dashboard", "suggested-next-step"],
    queryFn: fetchSuggestedNextStep,
  });

  if (statsQuery.isLoading) {
    return <p className="text-[var(--story-muted)]">Caricamento dashboard…</p>;
  }

  if (statsQuery.isError || !statsQuery.data) {
    return (
      <ErrorNotice
        title="Impossibile caricare la dashboard"
        message={
          statsQuery.isError
            ? getErrorMessage(statsQuery.error, "Errore sconosciuto")
            : "Verifica che l'API sia avviata su :8000."
        }
      />
    );
  }

  const stats = statsQuery.data;
  const nextPage = nextStepQuery.data?.page ?? "① Seleziona";
  const nextRoute = workflowRouteByPage[nextPage] ?? "/workflow/select";

  return (
    <div className="space-y-8">
      <header>
        <h2 className="text-2xl font-semibold">Dashboard</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Flusso Story: Drive → ritocco AI → approvazione → pianificazione → Meta.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Foto elaborate" value={stats.processed_visual} />
        <StatCard label="Da approvare" value={stats.pending_approval} />
        <StatCard label="Pronte da pianificare" value={stats.ready_to_plan} />
        <StatCard label="Da pubblicare (scaduti)" value={stats.due_dispatch} />
        <StatCard label="Batch attivi" value={stats.running_batches} />
      </div>

      <div className="rounded-xl border border-[var(--story-accent)]/30 bg-[var(--story-accent)]/10 p-4">
        <p className="text-sm text-[var(--story-muted)]">Prossimo passo consigliato</p>
        <p className="mt-1 text-lg font-medium">{nextPage}</p>
        <Link
          to={nextRoute}
          className="mt-4 inline-flex rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110"
        >
          Vai a {nextPage}
        </Link>
      </div>

      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--story-muted)]">
          Percorso rapido
        </h3>
        <div className="flex flex-wrap gap-2">
          {Object.entries(workflowRouteByPage).map(([label, route]) => (
            <Link
              key={route}
              to={route}
              className="rounded-lg border border-[var(--story-border)] px-3 py-2 text-sm hover:border-[var(--story-accent)]/50"
            >
              {label}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
