import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  channelsForBatch,
  FormatPlatformFilters,
  platformForApi,
} from "../components/FormatPlatformFilters";
import {
  fetchImageCategories,
  fetchMarketingObjectives,
  fetchVisualPipelineConfig,
  submitUploadBatch,
  validateUploadFile,
  type UploadDimensionValidation,
} from "../lib/api/client";
import { getErrorMessage } from "../lib/api/errors";

type PendingFile = {
  id: string;
  file: File;
  previewUrl: string;
  validating: boolean;
  dimensions: UploadDimensionValidation | null;
  resizeAction: "keep" | "resize" | null;
  error: string | null;
};

const TARGET_LABELS: Record<string, string> = {
  "post:instagram": "1080×1350 (IG feed 4:5)",
  "post:facebook": "1200×900 (FB feed 4:3)",
  "story:instagram": "1080×1920 (Story 9:16, IG + FB)",
};

function targetLabel(format: string, platform: string): string {
  if (format === "story") return TARGET_LABELS["story:instagram"];
  return TARGET_LABELS[`post:${platform}`] ?? "—";
}

export function UploadPage() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [format, setFormat] = useState("post");
  const [platform, setPlatform] = useState("instagram");
  const [category, setCategory] = useState("");
  const [objectives, setObjectives] = useState<string[]>(["Engagement"]);
  const [runAiRetouch, setRunAiRetouch] = useState(false);
  const [inputFidelity, setInputFidelity] = useState("");
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [flash, setFlash] = useState<{ level: "ok" | "err"; text: string } | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const categoriesQuery = useQuery({
    queryKey: ["config", "categories"],
    queryFn: fetchImageCategories,
  });
  const objectivesQuery = useQuery({
    queryKey: ["config", "marketing-objectives"],
    queryFn: fetchMarketingObjectives,
  });
  const visualQuery = useQuery({
    queryKey: ["config", "visual-pipeline"],
    queryFn: fetchVisualPipelineConfig,
    enabled: runAiRetouch,
  });

  const categories = useMemo(() => {
    const list = (categoriesQuery.data?.categories ?? []).filter((c) => c !== "tutte");
    return list;
  }, [categoriesQuery.data]);

  const objectiveOptions = objectivesQuery.data?.objectives ?? [];
  const fidelityOptions = visualQuery.data?.input_fidelity_options ?? [];
  const apiPlatform = platformForApi(format, platform);
  const expectedLabel = targetLabel(format, platform);

  const allResolved = pending.length > 0 && pending.every((p) => p.dimensions && p.resizeAction);
  const canSubmit =
    pending.length > 0 &&
    allResolved &&
    category.trim().length > 0 &&
    objectives.length > 0;

  const validateOne = useCallback(
    async (entry: PendingFile) => {
      setPending((prev) =>
        prev.map((p) => (p.id === entry.id ? { ...p, validating: true, error: null } : p)),
      );
      try {
        const result = await validateUploadFile(entry.file, {
          platform: apiPlatform,
          media_format: format,
        });
        setPending((prev) =>
          prev.map((p) =>
            p.id === entry.id
              ? {
                  ...p,
                  validating: false,
                  dimensions: result.dimensions,
                  resizeAction: result.dimensions.valid ? "keep" : null,
                }
              : p,
          ),
        );
      } catch (err) {
        setPending((prev) =>
          prev.map((p) =>
            p.id === entry.id
              ? {
                  ...p,
                  validating: false,
                  error: getErrorMessage(err, "Validazione fallita"),
                }
              : p,
          ),
        );
      }
    },
    [apiPlatform, format],
  );

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const list = Array.from(files).filter((f) => f.type.startsWith("image/"));
      if (!list.length) return;
      const entries: PendingFile[] = list.map((file) => ({
        id: `${file.name}-${file.size}-${Date.now()}-${Math.random()}`,
        file,
        previewUrl: URL.createObjectURL(file),
        validating: true,
        dimensions: null,
        resizeAction: null,
        error: null,
      }));
      setPending((prev) => [...prev, ...entries]);
      entries.forEach((entry) => void validateOne(entry));
    },
    [validateOne],
  );

  const uploadMutation = useMutation({
    mutationFn: () => {
      const resizeActions: Record<string, "keep" | "resize"> = {};
      for (const p of pending) {
        if (p.resizeAction) resizeActions[p.file.name] = p.resizeAction;
      }
      return submitUploadBatch({
        files: pending.map((p) => p.file),
        platform: apiPlatform,
        media_format: format,
        category,
        run_ai_retouch: runAiRetouch,
        marketing_objectives: objectives,
        resize_actions: resizeActions,
        visual_image_input_fidelity: runAiRetouch && inputFidelity ? inputFidelity : undefined,
      });
    },
    onSuccess: (data) => {
      setFlash({
        level: "ok",
        text: runAiRetouch
          ? `Batch AI avviato (#${data.batch_id}). Reindirizzamento…`
          : `${data.image_ids.length} immagine/i pronte per la pianificazione.`,
      });
      setTimeout(() => navigate(data.redirect), 800);
    },
    onError: (err: Error) => setFlash({ level: "err", text: err.message }),
  });

  function removeFile(id: string) {
    setPending((prev) => {
      const item = prev.find((p) => p.id === id);
      if (item) URL.revokeObjectURL(item.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }

  function setResizeAction(id: string, action: "keep" | "resize") {
    setPending((prev) =>
      prev.map((p) => (p.id === id ? { ...p, resizeAction: action } : p)),
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">Carica dal dispositivo</h2>
          <p className="mt-1 text-[var(--story-muted)]">
            Scegli formato e canale, poi carica una o più foto. Dimensioni attese:{" "}
            <strong className="text-[var(--story-text)]">{expectedLabel}</strong>.
          </p>
        </div>
        <Link
          to="/workflow/source"
          className="rounded-lg border border-[var(--story-border)] px-3 py-2 text-sm hover:border-[var(--story-accent)]/50"
        >
          ← Altra origine
        </Link>
      </header>

      <section className="grid gap-4 rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-4 md:grid-cols-2">
        <FormatPlatformFilters
          format={format}
          platform={platform}
          onFormatChange={(next) => {
            setFormat(next);
            setPending([]);
          }}
          onPlatformChange={(next) => {
            setPlatform(next);
            setPending([]);
          }}
        />
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Categoria</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            <option value="">Seleziona categoria…</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="space-y-2 text-sm md:col-span-2">
          <legend className="text-[var(--story-muted)]">Obiettivi contenuto</legend>
          <div className="flex flex-wrap gap-4">
            {objectiveOptions.map((o) => (
              <label key={o} className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={objectives.includes(o)}
                  onChange={(e) => {
                    setObjectives((prev) => {
                      if (e.target.checked) return [...prev, o];
                      const next = prev.filter((x) => x !== o);
                      return next.length ? next : ["Engagement"];
                    });
                  }}
                />
                {o}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="space-y-2 text-sm md:col-span-2">
          <legend className="text-[var(--story-muted)]">Ritocco Story AI</legend>
          <div className="flex flex-wrap gap-6">
            <label className="inline-flex items-center gap-2">
              <input
                type="radio"
                checked={!runAiRetouch}
                onChange={() => setRunAiRetouch(false)}
              />
              No — usa la foto così com&apos;è (dopo eventuale resize)
            </label>
            <label className="inline-flex items-center gap-2">
              <input
                type="radio"
                checked={runAiRetouch}
                onChange={() => setRunAiRetouch(true)}
              />
              Sì — passa dal batch AI (poi approvazione automatica)
            </label>
          </div>
          {runAiRetouch && fidelityOptions.length > 0 ? (
            <label className="mt-2 block space-y-1">
              <span className="text-[var(--story-muted)]">Input fidelity</span>
              <select
                value={inputFidelity || visualQuery.data?.default_input_fidelity || ""}
                onChange={(e) => setInputFidelity(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
              >
                {fidelityOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <p className="text-xs text-[var(--story-muted)]">
            Canali batch: {channelsForBatch(format, platform).join(", ")}
          </p>
        </fieldset>
      </section>

      <section
        className={[
          "rounded-xl border-2 border-dashed p-8 text-center transition-colors",
          dragOver
            ? "border-[var(--story-accent)] bg-[var(--story-accent)]/10"
            : "border-[var(--story-border)]",
        ].join(" ")}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
        }}
      >
        <p className="text-sm text-[var(--story-muted)]">
          Trascina qui le immagini oppure
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-3 rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black"
        >
          Sfoglia file
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </section>

      {pending.length > 0 ? (
        <ul className="space-y-4">
          {pending.map((item) => (
            <li
              key={item.id}
              className="flex flex-col gap-3 rounded-xl border border-[var(--story-border)] p-4 sm:flex-row sm:items-start"
            >
              <img
                src={item.previewUrl}
                alt={item.file.name}
                className="h-24 w-24 shrink-0 rounded-lg object-cover"
              />
              <div className="min-w-0 flex-1 space-y-2">
                <p className="truncate text-sm font-medium">{item.file.name}</p>
                {item.validating ? (
                  <p className="text-sm text-[var(--story-muted)]">Validazione dimensioni…</p>
                ) : item.error ? (
                  <p className="text-sm text-red-300">{item.error}</p>
                ) : item.dimensions ? (
                  <>
                    <p className="text-sm">
                      {item.dimensions.valid ? (
                        <span className="text-green-400">
                          Dimensioni OK ({item.dimensions.width}×{item.dimensions.height})
                        </span>
                      ) : (
                        <span className="text-amber-300">
                          {item.dimensions.width}×{item.dimensions.height} — attese{" "}
                          {item.dimensions.expected_label}
                        </span>
                      )}
                    </p>
                    {!item.dimensions.valid ? (
                      <div className="flex flex-wrap gap-3 text-sm">
                        <button
                          type="button"
                          onClick={() => setResizeAction(item.id, "keep")}
                          className={[
                            "rounded-lg border px-3 py-1.5",
                            item.resizeAction === "keep"
                              ? "border-[var(--story-accent)] bg-[var(--story-accent)]/15"
                              : "border-[var(--story-border)]",
                          ].join(" ")}
                        >
                          Procedi con dimensioni attuali
                        </button>
                        <button
                          type="button"
                          onClick={() => setResizeAction(item.id, "resize")}
                          className={[
                            "rounded-lg border px-3 py-1.5",
                            item.resizeAction === "resize"
                              ? "border-[var(--story-accent)] bg-[var(--story-accent)]/15"
                              : "border-[var(--story-border)]",
                          ].join(" ")}
                        >
                          Applica resize (center crop → {item.dimensions.expected_label})
                        </button>
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => removeFile(item.id)}
                className="shrink-0 text-sm text-[var(--story-muted)] hover:text-red-300"
              >
                Rimuovi
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={!canSubmit || uploadMutation.isPending}
          onClick={() => uploadMutation.mutate()}
          className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
        >
          {uploadMutation.isPending
            ? "Caricamento…"
            : runAiRetouch
              ? "Avvia batch AI"
              : "Carica e vai in pianificazione"}
        </button>
      </div>

      {flash ? (
        <p
          className={[
            "text-sm whitespace-pre-wrap",
            flash.level === "ok" ? "text-green-400" : "text-red-300",
          ].join(" ")}
        >
          {flash.text}
        </p>
      ) : null}
    </div>
  );
}
