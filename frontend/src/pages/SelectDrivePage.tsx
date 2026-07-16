import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pagination } from "../components/Pagination";
import {
  driveThumbnailUrl,
  fetchDriveAssets,
  fetchImageCategories,
  fetchMarketingObjectives,
  startAiBatch,
  type DriveAsset,
} from "../lib/api/client";

const MONTHS_IT = [
  "Gennaio",
  "Febbraio",
  "Marzo",
  "Aprile",
  "Maggio",
  "Giugno",
  "Luglio",
  "Agosto",
  "Settembre",
  "Ottobre",
  "Novembre",
  "Dicembre",
];

export function SelectDrivePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const now = new Date();

  const categoriesQuery = useQuery({
    queryKey: ["config", "categories"],
    queryFn: fetchImageCategories,
  });

  const categories = categoriesQuery.data?.categories ?? ["food"];
  const [category, setCategory] = useState("food");
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [page, setPage] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [allAssets, setAllAssets] = useState<DriveAsset[]>([]);
  const [platform, setPlatform] = useState("instagram");
  const [format, setFormat] = useState("post");
  const [objectives, setObjectives] = useState<string[]>(["Engagement"]);
  const [error, setError] = useState<string | null>(null);

  const objectivesQuery = useQuery({
    queryKey: ["config", "marketing-objectives"],
    queryFn: fetchMarketingObjectives,
  });
  const objectiveOptions = objectivesQuery.data?.objectives ?? [
    "Aumentare prenotazioni",
    "Engagement",
    "Community",
    "Notorietà",
  ];

  const pageSize = 12;

  const loadMutation = useMutation({
    mutationFn: async (refreshCache: boolean) => {
      const collected: DriveAsset[] = [];
      let pageNum = 0;
      let total = 0;
      do {
        const chunk = await fetchDriveAssets({
          category,
          year,
          month,
          page: pageNum,
          pageSize: 100,
          refreshCache: pageNum === 0 && refreshCache,
        });
        collected.push(...chunk.items);
        total = chunk.total;
        pageNum += 1;
      } while (collected.length < total);
      return collected;
    },
    onSuccess: (items) => {
      setAllAssets(items);
      setSelectedIds(new Set());
      setPage(0);
      setLoaded(true);
      setError(null);
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Errore caricamento Drive");
    },
  });

  const startMutation = useMutation({
    mutationFn: () => {
      const chosen = allAssets.filter((a) => selectedIds.has(a.file_id));
      return startAiBatch({
        category,
        platform,
        media_format: format,
        assets: chosen,
        marketing_objectives: objectives,
        channels: [platform],
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["batches"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/workflow/output?batch=${data.batch_id}`);
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Errore avvio coda");
    },
  });

  const pageAssets = useMemo(() => {
    const start = page * pageSize;
    return allAssets.slice(start, start + pageSize);
  }, [allAssets, page]);

  const totalPages = Math.max(1, Math.ceil(allAssets.length / pageSize));

  function toggleAsset(fileId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });
  }

  function selectAll() {
    setSelectedIds(new Set(allAssets.map((a) => a.file_id)));
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">① Seleziona da Drive</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Carica le foto da Drive, seleziona quelle da passare a Story AI e avvia la coda.
        </p>
      </header>

      <div className="grid gap-3 md:grid-cols-4">
        <label className="space-y-1 text-sm md:col-span-2">
          <span className="text-[var(--story-muted)]">Categoria</span>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setLoaded(false);
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
          <span className="text-[var(--story-muted)]">Anno</span>
          <input
            type="number"
            min={2000}
            max={2100}
            value={year}
            onChange={(e) => {
              setYear(Number(e.target.value));
              setLoaded(false);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Mese</span>
          <select
            value={month}
            onChange={(e) => {
              setMonth(Number(e.target.value));
              setLoaded(false);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {MONTHS_IT.map((label, index) => (
              <option key={label} value={index + 1}>
                {String(index + 1).padStart(2, "0")} · {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => loadMutation.mutate(false)}
          disabled={loadMutation.isPending}
          className="rounded-lg border border-[var(--story-border)] px-4 py-2 text-sm"
        >
          {loadMutation.isPending ? "Caricamento…" : "Carica immagini da Drive"}
        </button>
        <button
          type="button"
          onClick={() => loadMutation.mutate(true)}
          disabled={loadMutation.isPending}
          className="rounded-lg border border-[var(--story-border)] px-4 py-2 text-sm text-[var(--story-muted)]"
        >
          Ricarica (svuota cache anteprime)
        </button>
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm whitespace-pre-wrap break-words text-red-200">
          {error}
        </p>
      )}

      {!loaded && (
        <div className="rounded-xl border border-dashed border-[var(--story-border)] p-6 text-[var(--story-muted)]">
          Imposta filtri e clicca <strong>Carica immagini da Drive</strong>.
        </div>
      )}

      {loaded && allAssets.length === 0 && (
        <div className="rounded-xl border border-[var(--story-border)] p-6 text-[var(--story-muted)]">
          Nessuna immagine trovata per i filtri selezionati.
        </div>
      )}

      {loaded && allAssets.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Pagination
              page={page}
              totalPages={totalPages}
              total={allAssets.length}
              onPageChange={setPage}
            />
            <p className="text-sm text-[var(--story-muted)]">
              {selectedIds.size} selezionate su {allAssets.length}
            </p>
          </div>

          <div className="flex gap-2">
            <button
              type="button"
              onClick={selectAll}
              className="rounded-lg border border-[var(--story-border)] px-3 py-1.5 text-sm"
            >
              Seleziona tutte ({allAssets.length})
            </button>
            <button
              type="button"
              onClick={clearSelection}
              className="rounded-lg border border-[var(--story-border)] px-3 py-1.5 text-sm"
            >
              Deseleziona tutte
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {pageAssets.map((asset) => {
              const selected = selectedIds.has(asset.file_id);
              return (
                <button
                  key={asset.file_id}
                  type="button"
                  onClick={() => toggleAsset(asset.file_id)}
                  className={[
                    "rounded-xl border p-3 text-left transition",
                    selected
                      ? "border-[var(--story-accent)] bg-[var(--story-accent)]/10"
                      : "border-[var(--story-border)] bg-[var(--story-surface)]",
                  ].join(" ")}
                >
                  <img
                    src={driveThumbnailUrl(asset.file_id, asset.mime_type)}
                    alt={asset.name}
                    className="mb-2 aspect-square w-full rounded-lg object-cover bg-black/20"
                    loading="lazy"
                  />
                  <p className="truncate text-sm font-medium">{asset.name}</p>
                  {asset.path_hint && (
                    <p className="truncate text-xs text-[var(--story-muted)]">{asset.path_hint}</p>
                  )}
                  <p className="mt-2 text-xs text-[var(--story-muted)]">
                    {selected ? "Selezionata" : "Clicca per selezionare"}
                  </p>
                </button>
              );
            })}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-[var(--story-muted)]">Social destinazione</span>
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
                className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
              >
                <option value="instagram">Instagram</option>
                <option value="facebook">Facebook</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-[var(--story-muted)]">Formato export</span>
              <select
                value={format}
                onChange={(e) => setFormat(e.target.value)}
                className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
              >
                <option value="post">Post (feed)</option>
                <option value="story">Story (9:16)</option>
              </select>
            </label>
          </div>

          <fieldset className="space-y-2 text-sm">
            <legend className="text-[var(--story-muted)]">Obiettivi marketing (uno o più)</legend>
            <div className="flex flex-wrap gap-4">
              {objectiveOptions.map((obj) => (
                <label key={obj} className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={objectives.includes(obj)}
                    onChange={(e) => {
                      setObjectives((prev) => {
                        if (e.target.checked) return [...prev, obj];
                        const next = prev.filter((o) => o !== obj);
                        return next.length ? next : ["Engagement"];
                      });
                    }}
                  />
                  {obj}
                </label>
              ))}
            </div>
          </fieldset>

          <button
            type="button"
            disabled={selectedIds.size === 0 || startMutation.isPending}
            onClick={() => startMutation.mutate()}
            className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
          >
            {startMutation.isPending
              ? "Avvio coda…"
              : `Avvia coda ritocco (${selectedIds.size} foto)`}
          </button>
        </>
      )}
    </div>
  );
}
