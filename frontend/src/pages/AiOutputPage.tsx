import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BatchProgressBanner } from "../components/BatchProgressBanner";
import { ErrorNotice } from "../components/ErrorNotice";
import { ApprovalBadge, ImageCompare } from "../components/ImageCompare";
import { imageReviewCardClass, imageReviewGridClass } from "../components/imageReviewLayout";
import { fetchAiOutput, fetchVisualPipelineConfig, reprocessImage } from "../lib/api/client";
import { getErrorMessage } from "../lib/api/errors";

const filters = [
  { value: "pending", label: "Da approvare" },
  { value: "approved", label: "Approvate" },
  { value: "rejected", label: "Rifiutate" },
  { value: "all", label: "Tutte" },
] as const;

export function AiOutputPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const batchParam = searchParams.get("batch");
  const batchId = batchParam && /^\d+$/.test(batchParam) ? Number(batchParam) : undefined;
  const [filter, setFilter] = useState<(typeof filters)[number]["value"]>("pending");
  const [inputFidelity, setInputFidelity] = useState("low");
  const [reprocessError, setReprocessError] = useState<string | null>(null);
  const [reprocessingId, setReprocessingId] = useState<number | null>(null);

  const pipelineQuery = useQuery({
    queryKey: ["config", "visual-pipeline"],
    queryFn: fetchVisualPipelineConfig,
  });

  useEffect(() => {
    if (pipelineQuery.data?.default_input_fidelity) {
      setInputFidelity(pipelineQuery.data.default_input_fidelity);
    }
  }, [pipelineQuery.data?.default_input_fidelity]);

  const query = useQuery({
    queryKey: ["images", "ai-output", filter],
    queryFn: () => fetchAiOutput(filter),
  });

  const reprocessMutation = useMutation({
    mutationFn: (imageId: number) =>
      reprocessImage(imageId, { visual_image_input_fidelity: inputFidelity }),
    onMutate: (imageId) => {
      setReprocessError(null);
      setReprocessingId(imageId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["images", "ai-output"] });
    },
    onError: (err) => {
      setReprocessError(getErrorMessage(err, "Rigenerazione fallita"));
    },
    onSettled: () => {
      setReprocessingId(null);
    },
  });

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">② Output AI</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Confronto originale vs asset finale. Profilo <strong>quality</strong>: edit plan, compiler
          e pre-crop attivi. Usa «Rigenera» per rifare l&apos;editing come il Custom GPT.
        </p>
      </header>

      <BatchProgressBanner batchId={batchId} />

      <label className="block max-w-md space-y-1 text-sm">
        <span className="text-[var(--story-muted)]">Input fidelity (rigenera)</span>
        <select
          value={inputFidelity}
          onChange={(e) => setInputFidelity(e.target.value)}
          className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
        >
          {(pipelineQuery.data?.input_fidelity_options ?? [
            { value: "low", label: "Bassa — generazione parziale più visibile" },
            { value: "high", label: "Alta — preserva pixel originali (edit sottile)" },
          ]).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      {reprocessError ? (
        <ErrorNotice title="Rigenerazione non riuscita" message={reprocessError} />
      ) : null}

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
            <ImageCompare
              image={image}
              compact
              onReprocess={(id) => reprocessMutation.mutate(id)}
              isReprocessing={reprocessingId === image.id && reprocessMutation.isPending}
            />
          </article>
        ))}
      </div>
    </div>
  );
}
