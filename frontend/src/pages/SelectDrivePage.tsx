import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Pagination } from "../components/Pagination";
import {
  driveAssetsQueryKey,
  loadDriveSession,
  saveDriveSession,
} from "../lib/driveSession";
import {
  driveThumbnailUrl,
  fetchDriveAssets,
  fetchGoogleOAuthStatus,
  fetchImageCategories,
  fetchMarketingObjectives,
  fetchVisualPipelineConfig,
  googleDriveReconnectUrl,
  startAiBatch,
  type DriveAsset,
} from "../lib/api/client";
import { getErrorMessage, isGoogleTokenError } from "../lib/api/errors";

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

async function fetchAllDriveAssets(params: {
  category: string;
  year: number;
  month: number;
  refreshCache: boolean;
}): Promise<DriveAsset[]> {
  const collected: DriveAsset[] = [];
  let pageNum = 0;
  let total = 0;
  do {
    const chunk = await fetchDriveAssets({
      category: params.category,
      year: params.year,
      month: params.month,
      page: pageNum,
      pageSize: 100,
      refreshCache: pageNum === 0 && params.refreshCache,
    });
    collected.push(...chunk.items);
    total = chunk.total;
    pageNum += 1;
  } while (collected.length < total);
  return collected;
}

export function SelectDrivePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const now = new Date();
  const savedSession = loadDriveSession();
  const restoredRef = useRef(false);

  const categoriesQuery = useQuery({
    queryKey: ["config", "categories"],
    queryFn: fetchImageCategories,
  });

  const pipelineQuery = useQuery({
    queryKey: ["config", "visual-pipeline"],
    queryFn: fetchVisualPipelineConfig,
  });

  const categories = categoriesQuery.data?.categories ?? ["food"];
  const [category, setCategory] = useState(savedSession?.category ?? "food");
  const [year, setYear] = useState(savedSession?.year ?? now.getFullYear());
  const [month, setMonth] = useState(savedSession?.month ?? now.getMonth() + 1);
  const [page, setPage] = useState(0);
  const [loaded, setLoaded] = useState(savedSession?.loaded ?? false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(savedSession?.selectedIds ?? []),
  );
  const [allAssets, setAllAssets] = useState<DriveAsset[]>([]);
  const [platform, setPlatform] = useState(savedSession?.platform ?? "instagram");
  const [format, setFormat] = useState(savedSession?.format ?? "post");
  const [objectives, setObjectives] = useState<string[]>(
    savedSession?.objectives?.length ? savedSession.objectives : ["Engagement"],
  );
  const [inputFidelity, setInputFidelity] = useState(
    savedSession?.inputFidelity ?? pipelineQuery.data?.default_input_fidelity ?? "low",
  );
  const [error, setError] = useState<string | null>(null);
  const [tokenError, setTokenError] = useState(false);
  const [oauthNotice, setOauthNotice] = useState<string | null>(null);

  useEffect(() => {
    if (pipelineQuery.data?.default_input_fidelity && !savedSession?.inputFidelity) {
      setInputFidelity(pipelineQuery.data.default_input_fidelity);
    }
  }, [pipelineQuery.data?.default_input_fidelity, savedSession?.inputFidelity]);

  useEffect(() => {
    saveDriveSession({
      category,
      year,
      month,
      selectedIds: [...selectedIds],
      platform,
      format,
      objectives,
      inputFidelity,
      loaded,
    });
  }, [
    category,
    year,
    month,
    selectedIds,
    platform,
    format,
    objectives,
    inputFidelity,
    loaded,
  ]);

  const oauthStatusQuery = useQuery({
    queryKey: ["oauth", "google", "status"],
    queryFn: fetchGoogleOAuthStatus,
  });

  useEffect(() => {
    if (searchParams.get("google") === "connected") {
      setOauthNotice("Google Drive riconnesso. Puoi caricare le immagini.");
      setTokenError(false);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["oauth", "google", "status"] });
      searchParams.delete("google");
      setSearchParams(searchParams, { replace: true });
    }
  }, [queryClient, searchParams, setSearchParams]);

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

  const fidelityOptions = pipelineQuery.data?.input_fidelity_options ?? [
    { value: "low", label: "Bassa — generazione parziale più visibile" },
    { value: "high", label: "Alta — preserva pixel originali (edit sottile)" },
  ];

  const pageSize = 12;

  const loadMutation = useMutation({
    mutationFn: async (refreshCache: boolean) => {
      const key = driveAssetsQueryKey(category, year, month);
      if (refreshCache) {
        queryClient.removeQueries({ queryKey: key });
      }
      return queryClient.fetchQuery({
        queryKey: key,
        queryFn: () => fetchAllDriveAssets({ category, year, month, refreshCache }),
        staleTime: 5 * 60 * 1000,
      });
    },
    onSuccess: (items, refreshCache) => {
      setAllAssets(items);
      if (refreshCache) {
        setSelectedIds(new Set());
      } else {
        setSelectedIds((prev) => {
          const valid = new Set(items.map((a) => a.file_id));
          return new Set([...prev].filter((id) => valid.has(id)));
        });
      }
      setPage(0);
      setLoaded(true);
      setError(null);
      setTokenError(false);
    },
    onError: (err) => {
      setTokenError(isGoogleTokenError(err));
      setError(getErrorMessage(err, "Errore caricamento Drive"));
    },
  });

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    if (!savedSession?.loaded) return;

    const key = driveAssetsQueryKey(category, year, month);
    const cached = queryClient.getQueryData<DriveAsset[]>(key);
    if (cached?.length) {
      setAllAssets(cached);
      setLoaded(true);
      return;
    }
    loadMutation.mutate(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once on mount
  }, []);

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
        visual_image_input_fidelity: inputFidelity,
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

  const oauthStatus = oauthStatusQuery.data;
  const oauthWebAvailable = oauthStatus?.credentials_configured === true;
  const errorLooksLikeToken =
    Boolean(error && /invalid_grant|scaduta o revocata|token has been expired/i.test(error));
  const hasTokenProblem =
    tokenError || oauthStatus?.token_valid === false || errorLooksLikeToken;

  function handleReconnectGoogle() {
    window.location.href = googleDriveReconnectUrl();
  }

  function driveConnectionLabel(): string {
    if (oauthStatusQuery.isError) return "stato non disponibile (API non aggiornata?)";
    if (!oauthStatus) return "verifica in corso…";
    if (hasTokenProblem) return "token scaduto o revocato";
    if (oauthStatus.token_valid === true) return "connesso";
    if (oauthStatus.refresh_token_configured) return "token configurato";
    return "non connesso";
  }

  function displayError(): string | null {
    if (!error) return null;
    if (errorLooksLikeToken || tokenError) {
      return (
        "Connessione Google Drive scaduta o revocata. Usa «Riconnetti Google Drive» " +
        "qui sopra, oppure apri /api/v1/oauth/google/start nel browser."
      );
    }
    return error;
  }

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">① Seleziona da Drive</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Carica le foto da Drive, seleziona quelle da passare a Story AI e avvia la coda.
          La selezione resta salvata finché non chiudi il browser.
        </p>
      </header>

      {oauthNotice && (
        <p className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {oauthNotice}
        </p>
      )}

      <div
        className={[
          "space-y-2 rounded-lg border px-4 py-3 text-sm",
          hasTokenProblem
            ? "border-amber-500/50 bg-amber-500/10"
            : "border-[var(--story-border)] bg-[var(--story-surface)]",
        ].join(" ")}
      >
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[var(--story-muted)]">
            Google Drive: {driveConnectionLabel()}
            {oauthStatus?.token_source ? ` (sorgente: ${oauthStatus.token_source})` : ""}
          </span>
          <button
            type="button"
            onClick={handleReconnectGoogle}
            className="rounded-lg bg-[var(--story-accent)] px-3 py-1.5 text-xs font-semibold text-black"
          >
            Riconnetti Google Drive
          </button>
        </div>
        {!oauthWebAvailable && (
          <p className="text-xs text-amber-200/90">
            Se il pulsante non funziona, configura{" "}
            <code className="rounded bg-black/20 px-1">GOOGLE_CREDENTIALS_JSON</code> (OAuth{" "}
            <strong>Web application</strong>) e{" "}
            <code className="rounded bg-black/20 px-1">GOOGLE_REDIRECT_URI</code> su Vercel.
            In locale:{" "}
            <code className="rounded bg-black/20 px-1">python3 -m social_automation drive-auth</code>
            .
          </p>
        )}
        {oauthStatus?.redirect_uri && (
          <p className="text-xs text-[var(--story-muted)] break-all">
            Callback OAuth (deve essere identico in Google Cloud Console → Authorized redirect
            URIs):{" "}
            <code className="rounded bg-black/20 px-1 text-amber-100/90">
              {oauthStatus.redirect_uri}
            </code>
          </p>
        )}
        {oauthStatusQuery.isError && (
          <p className="text-xs text-amber-200/90">
            Endpoint OAuth non raggiungibile — il deploy potrebbe non essere aggiornato. Verifica{" "}
            <code className="rounded bg-black/20 px-1">/api/v1/health</code> (campo{" "}
            <code className="rounded bg-black/20 px-1">api_features</code>).
          </p>
        )}
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <label className="space-y-1 text-sm md:col-span-2">
          <span className="text-[var(--story-muted)]">Categoria</span>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setLoaded(false);
              setAllAssets([]);
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
              setAllAssets([]);
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
              setAllAssets([]);
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
          {displayError()}
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

          <div className="grid gap-3 md:grid-cols-3">
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
            <label className="space-y-1 text-sm">
              <span className="text-[var(--story-muted)]">Input fidelity (edit AI)</span>
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
