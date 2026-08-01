import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ImageCompare } from "../components/ImageCompare";
import { ErrorNotice } from "../components/ErrorNotice";
import { imageReviewCardClass, imageReviewGridClass } from "../components/imageReviewLayout";
import { Pagination } from "../components/Pagination";
import {
  fetchApprovalFeedbackTags,
  fetchImageCategories,
  fetchPendingApproval,
  fetchVisualPipelineConfig,
  postImageApproval,
  reprocessImage,
  type ApprovalAction,
  type ApprovalPayload,
  type ImageSummary,
} from "../lib/api/client";
import { getErrorMessage } from "../lib/api/errors";

type FeedbackDraft = {
  reason: string;
  tags: string[];
};

function ApprovalCard({
  image,
  busy,
  reprocessing,
  feedbackTags,
  onAction,
  onReprocess,
}: {
  image: ImageSummary;
  busy: boolean;
  reprocessing: boolean;
  feedbackTags: Record<string, string>;
  onAction: (payload: ApprovalPayload) => void;
  onReprocess: (imageId: number) => void;
}) {
  const [pendingAction, setPendingAction] = useState<ApprovalAction | null>(null);
  const [draft, setDraft] = useState<FeedbackDraft>({ reason: "", tags: [] });

  const needsFeedback = pendingAction === "reject" || pendingAction === "use_original";

  const toggleTag = (tag: string) => {
    setDraft((prev) => ({
      ...prev,
      tags: prev.tags.includes(tag)
        ? prev.tags.filter((t) => t !== tag)
        : [...prev.tags, tag],
    }));
  };

  const resetFeedback = () => {
    setPendingAction(null);
    setDraft({ reason: "", tags: [] });
  };

  const submitDirect = (action: ApprovalAction) => {
    onAction({ action });
    resetFeedback();
  };

  const submitWithFeedback = () => {
    if (!pendingAction) return;
    onAction({
      action: pendingAction,
      reason: draft.reason.trim() || undefined,
      tags: draft.tags.length > 0 ? draft.tags : undefined,
    });
    resetFeedback();
  };

  return (
    <article className={imageReviewCardClass}>
      <h3
        className="mb-1.5 truncate text-xs font-medium"
        title={`#${image.id} · ${image.name}`}
      >
        #{image.id} · {image.name}
      </h3>
      <ImageCompare
        image={image}
        compact
        onReprocess={onReprocess}
        isReprocessing={reprocessing}
      />
      <div className="mt-2 grid grid-cols-1 gap-1">
        {!needsFeedback && (
          <>
            <button
              type="button"
              disabled={busy || reprocessing}
              onClick={() => submitDirect("approve")}
              className="rounded-md bg-[var(--story-accent)] px-2 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
            >
              Approva ritocco
            </button>
            <button
              type="button"
              disabled={busy || reprocessing}
              onClick={() => setPendingAction("use_original")}
              className="rounded-md border border-[var(--story-border)] px-2 py-1.5 text-xs disabled:opacity-50"
            >
              Usa originale
            </button>
            <button
              type="button"
              disabled={busy || reprocessing}
              onClick={() => setPendingAction("reject")}
              className="rounded-md border border-red-500/40 px-2 py-1.5 text-xs text-red-200 disabled:opacity-50"
            >
              Rifiuta
            </button>
          </>
        )}

        {needsFeedback && (
          <div className="space-y-2 rounded-md border border-[var(--story-border)] bg-[var(--story-bg)] p-2">
            <p className="text-xs text-[var(--story-muted)]">
              {pendingAction === "reject"
                ? "Perché rifiuti il ritocco?"
                : "Perché preferisci l'originale?"}
            </p>
            <div className="flex flex-wrap gap-1">
              {Object.entries(feedbackTags).map(([key, label]) => (
                <label
                  key={key}
                  className={`cursor-pointer rounded border px-1.5 py-0.5 text-[10px] ${
                    draft.tags.includes(key)
                      ? "border-[var(--story-accent)] text-[var(--story-accent)]"
                      : "border-[var(--story-border)] text-[var(--story-muted)]"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={draft.tags.includes(key)}
                    onChange={() => toggleTag(key)}
                  />
                  {label}
                </label>
              ))}
            </div>
            <textarea
              value={draft.reason}
              onChange={(e) => setDraft((prev) => ({ ...prev, reason: e.target.value }))}
              placeholder="Note aggiuntive (opzionale)"
              rows={2}
              className="w-full rounded border border-[var(--story-border)] bg-transparent px-2 py-1 text-xs"
            />
            <div className="grid grid-cols-2 gap-1">
              <button
                type="button"
                disabled={busy}
                onClick={resetFeedback}
                className="rounded-md border border-[var(--story-border)] px-2 py-1.5 text-xs disabled:opacity-50"
              >
                Annulla
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={submitWithFeedback}
                className="rounded-md bg-[var(--story-accent)] px-2 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
              >
                Conferma
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

export function ApprovePage() {
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState("instagram");
  const [format, setFormat] = useState("post");
  const [category, setCategory] = useState("tutte");
  const [page, setPage] = useState(0);
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

  const categoriesQuery = useQuery({
    queryKey: ["images", "categories"],
    queryFn: fetchImageCategories,
  });

  const feedbackTagsQuery = useQuery({
    queryKey: ["images", "approval-feedback-tags"],
    queryFn: fetchApprovalFeedbackTags,
  });

  const listQuery = useQuery({
    queryKey: ["images", "pending-approval", platform, format, category, page],
    queryFn: () =>
      fetchPendingApproval({ platform, format, category, page, pageSize: 20 }),
  });

  const mutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: ApprovalPayload }) =>
      postImageApproval(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["images"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: (imageId: number) =>
      reprocessImage(imageId, { visual_image_input_fidelity: inputFidelity }),
    onMutate: (imageId) => {
      setReprocessError(null);
      setReprocessingId(imageId);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["images", "pending-approval"] });
    },
    onError: (err) => {
      setReprocessError(getErrorMessage(err, "Rigenerazione fallita"));
    },
    onSettled: () => {
      setReprocessingId(null);
    },
  });

  const categories = categoriesQuery.data?.categories ?? ["tutte"];
  const feedbackTags = feedbackTagsQuery.data ?? {};
  const fidelityOptions = pipelineQuery.data?.input_fidelity_options ?? [
    { value: "high", label: "Alta — preserva pixel (consigliata per bandierine/loghi)" },
    { value: "low", label: "Bassa — più libertà AI (può rigenerare parti della scena)" },
  ];

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">③ Approva foto</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Controlla il ritocco. Usa <strong>Rigenera</strong> per rifare l&apos;edit dall&apos;originale
          con la fidelity scelta. Solo le immagini approvate compaiono in pianificazione.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Social</span>
          <select
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              setPage(0);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            <option value="instagram">Instagram</option>
            <option value="facebook">Facebook</option>
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Formato</span>
          <select
            value={format}
            onChange={(e) => {
              setFormat(e.target.value);
              setPage(0);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            <option value="post">Post (feed)</option>
            <option value="story">Story (9:16)</option>
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Categoria</span>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(0);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Input fidelity (rigenera)</span>
          <select
            value={inputFidelity}
            onChange={(e) => setInputFidelity(e.target.value)}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {fidelityOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {listQuery.isLoading && <p className="text-[var(--story-muted)]">Caricamento…</p>}
      {mutation.isError && (
        <ErrorNotice
          title="Errore approvazione"
          message={getErrorMessage(mutation.error, "Errore sconosciuto")}
        />
      )}
      {reprocessError ? (
        <ErrorNotice title="Rigenerazione non riuscita" message={reprocessError} />
      ) : null}

      {listQuery.data && listQuery.data.total === 0 && (
        <div className="rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-6 text-[var(--story-muted)]">
          Nessuna immagine in attesa. Elabora nuove foto in ① Seleziona → ② Output AI.
        </div>
      )}

      {listQuery.data && listQuery.data.total > 0 && (
        <Pagination
          page={page}
          totalPages={listQuery.data.total_pages ?? 1}
          total={listQuery.data.total}
          onPageChange={setPage}
        />
      )}

      <div className={imageReviewGridClass}>
        {listQuery.data?.items.map((image) => (
          <ApprovalCard
            key={image.id}
            image={image}
            busy={mutation.isPending}
            reprocessing={reprocessingId === image.id && reprocessMutation.isPending}
            feedbackTags={feedbackTags}
            onAction={(payload) => mutation.mutate({ id: image.id, payload })}
            onReprocess={(id) => reprocessMutation.mutate(id)}
          />
        ))}
      </div>
    </div>
  );
}
