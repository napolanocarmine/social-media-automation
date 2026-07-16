import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ImageCompare } from "../components/ImageCompare";
import { ErrorNotice } from "../components/ErrorNotice";
import { imageReviewCardClass, imageReviewGridClass } from "../components/imageReviewLayout";
import { Pagination } from "../components/Pagination";
import {
  fetchImageCategories,
  fetchPendingApproval,
  postImageApproval,
  type ApprovalAction,
  type ImageSummary,
} from "../lib/api/client";
import { getErrorMessage } from "../lib/api/errors";

function ApprovalCard({
  image,
  busy,
  onAction,
}: {
  image: ImageSummary;
  busy: boolean;
  onAction: (action: ApprovalAction) => void;
}) {
  return (
    <article className={imageReviewCardClass}>
      <h3
        className="mb-1.5 truncate text-xs font-medium"
        title={`#${image.id} · ${image.name}`}
      >
        #{image.id} · {image.name}
      </h3>
      <ImageCompare image={image} compact />
      <div className="mt-2 grid grid-cols-1 gap-1">
        <button
          type="button"
          disabled={busy}
          onClick={() => onAction("approve")}
          className="rounded-md bg-[var(--story-accent)] px-2 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
        >
          Approva ritocco
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onAction("use_original")}
          className="rounded-md border border-[var(--story-border)] px-2 py-1.5 text-xs disabled:opacity-50"
        >
          Usa originale
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => onAction("reject")}
          className="rounded-md border border-red-500/40 px-2 py-1.5 text-xs text-red-200 disabled:opacity-50"
        >
          Rifiuta
        </button>
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

  const categoriesQuery = useQuery({
    queryKey: ["images", "categories"],
    queryFn: fetchImageCategories,
  });

  const listQuery = useQuery({
    queryKey: ["images", "pending-approval", platform, format, category, page],
    queryFn: () =>
      fetchPendingApproval({ platform, format, category, page, pageSize: 20 }),
  });

  const mutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: ApprovalAction }) =>
      postImageApproval(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["images"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const categories = categoriesQuery.data?.categories ?? ["tutte"];

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">③ Approva foto</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Controlla il ritocco. Solo le immagini approvate compaiono in pianificazione.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
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
      </div>

      {listQuery.isLoading && <p className="text-[var(--story-muted)]">Caricamento…</p>}
      {mutation.isError && (
        <ErrorNotice
          title="Errore approvazione"
          message={getErrorMessage(mutation.error, "Errore sconosciuto")}
        />
      )}

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
            onAction={(action) => mutation.mutate({ id: image.id, action })}
          />
        ))}
      </div>
    </div>
  );
}
