import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BatchProgressBanner } from "../components/BatchProgressBanner";
import { ErrorNotice } from "../components/ErrorNotice";
import { ApprovalBadge, ImageCompare } from "../components/ImageCompare";
import { imageReviewCardClass, imageReviewGridClass } from "../components/imageReviewLayout";
import { fetchAiOutput } from "../lib/api/client";
import { getErrorMessage } from "../lib/api/errors";

const filters = [
  { value: "pending", label: "Da approvare" },
  { value: "approved", label: "Approvate" },
  { value: "rejected", label: "Rifiutate" },
  { value: "all", label: "Tutte" },
] as const;

export function AiOutputPage() {
  const [searchParams] = useSearchParams();
  const batchParam = searchParams.get("batch");
  const batchId = batchParam && /^\d+$/.test(batchParam) ? Number(batchParam) : undefined;
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("pending");

  const query = useQuery({
    queryKey: ["images", "ai-output", filter],
    queryFn: () => fetchAiOutput(filter),
  });

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">② Output AI</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Anteprima ritocco: originale Drive vs asset finale. Il copy si genera in pianificazione.
        </p>
      </header>

      <BatchProgressBanner batchId={batchId} />

      <div className="flex flex-wrap gap-2">
        {filters.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setFilter(item.value)}
            className={[
              "rounded-lg px-3 py-1.5 text-sm transition",
              filter === item.value
                ? "bg-[var(--story-accent)] text-black font-medium"
                : "border border-[var(--story-border)] text-[var(--story-muted)] hover:text-[var(--story-text)]",
            ].join(" ")}
          >
            {item.label}
          </button>
        ))}
      </div>

      {query.isLoading && <p className="text-[var(--story-muted)]">Caricamento…</p>}
      {query.isError && (
        <ErrorNotice
          title="Errore nel caricamento degli output AI"
          message={getErrorMessage(query.error, "Errore sconosciuto")}
        />
      )}

      {query.data && query.data.total === 0 && (
        <div className="rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-6 text-[var(--story-muted)]">
          Nessun output AI per questo filtro. Vai a ① Seleziona e avvia una coda.
        </div>
      )}

      {query.data && query.data.items.length > 0 && (
        <p className="text-sm text-[var(--story-muted)]">
          Mostrate {query.data.items.length} di {query.data.total} immagini.
        </p>
      )}

      <div className={imageReviewGridClass}>
        {query.data?.items.map((image) => (
          <article key={image.id} className={imageReviewCardClass}>
            <div className="mb-1.5 flex items-center gap-1.5">
              <h3
                className="min-w-0 flex-1 truncate text-xs font-medium"
                title={`#${image.id} · ${image.name}`}
              >
                #{image.id} · {image.name}
              </h3>
              <ApprovalBadge status={image.approval_status} />
            </div>
            <ImageCompare image={image} compact />
          </article>
        ))}
      </div>
    </div>
  );
}
