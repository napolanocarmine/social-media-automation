import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Pagination } from "../components/Pagination";
import {
  cancelPlan,
  createPlan,
  fetchCalendar,
  fetchCalendarEvents,
  fetchImageCategories,
  fetchImageCopy,
  fetchMarketingObjectives,
  fetchPlannableImages,
  generateImageCopy,
  reschedulePlan,
  suggestPlanSlot,
  type CalendarEvent,
  type CopyPack,
  type ImageSummary,
} from "../lib/api/client";

const WEEKDAYS_IT = [
  "Lunedì",
  "Martedì",
  "Mercoledì",
  "Giovedì",
  "Venerdì",
  "Sabato",
  "Domenica",
];

const MONTH_NAMES = [
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

function captionFromCopy(copy: CopyPack | null, platform: string): string {
  if (!copy) return "";
  if (platform === "facebook") return String(copy.facebook_caption ?? "").trim();
  return String(copy.instagram_caption ?? "").trim();
}

function CopyPreview({ copy, platform }: { copy: CopyPack; platform: string }) {
  const caption = captionFromCopy(copy, platform);
  const tags = Array.isArray(copy.hashtags)
    ? copy.hashtags.join(" ")
    : String(copy.hashtags ?? "");
  return (
    <div className="rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] p-3 text-sm">
      <p className="whitespace-pre-wrap">{caption}</p>
      {tags ? <p className="mt-2 text-[var(--story-muted)]">{tags}</p> : null}
    </div>
  );
}

function PlanWizard() {
  const queryClient = useQueryClient();
  const [platform, setPlatform] = useState("instagram");
  const [format, setFormat] = useState("post");
  const [category, setCategory] = useState("tutte");
  const [page, setPage] = useState(0);
  const [step, setStep] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedObjectives, setSelectedObjectives] = useState<string[]>(["Engagement"]);
  const [channels, setChannels] = useState<string[]>(["instagram"]);
  const [copyPack, setCopyPack] = useState<CopyPack | null>(null);
  const [planDate, setPlanDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [planTime, setPlanTime] = useState("18:30");
  const [caption, setCaption] = useState("");
  const [storyKind, setStoryKind] = useState<"single" | "weekly">("single");
  const [storyWeekday, setStoryWeekday] = useState(0);
  const [storyTime, setStoryTime] = useState("10:00");
  const [flash, setFlash] = useState<{ level: "ok" | "err"; text: string } | null>(null);

  const categoriesQuery = useQuery({
    queryKey: ["config", "categories"],
    queryFn: fetchImageCategories,
  });
  const objectivesQuery = useQuery({
    queryKey: ["config", "marketing-objectives"],
    queryFn: fetchMarketingObjectives,
  });

  const listQuery = useQuery({
    queryKey: ["images", "plannable", platform, format, category, page],
    queryFn: () => fetchPlannableImages({ platform, format, category, page, pageSize: 10 }),
  });

  const slotQuery = useQuery({
    queryKey: ["plans", "suggest-slot", platform],
    queryFn: () => suggestPlanSlot(platform),
    enabled: step === 2 && format === "post",
  });

  const generateMutation = useMutation({
    mutationFn: () =>
      generateImageCopy(selectedId!, {
        platform,
        media_format: format,
        marketing_objectives: selectedObjectives,
        channels,
      }),
    onSuccess: (data) => {
      setCopyPack(data.copy);
      setCaption(captionFromCopy(data.copy, platform));
    },
    onError: (err: Error) => setFlash({ level: "err", text: err.message }),
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      const body: Parameters<typeof createPlan>[0] = {
        image_id: selectedId!,
        platform,
        media_format: format,
      };
      if (format === "story" && storyKind === "weekly") {
        body.story_schedule = {
          mode: "weekly",
          weekday: storyWeekday,
          time_local: storyTime,
        };
      } else {
        body.scheduled_date = planDate;
        body.scheduled_time = planTime;
        if (format === "post") body.caption = caption;
      }
      return createPlan(body);
    },
    onSuccess: (data) => {
      setFlash({ level: "ok", text: data.message });
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setStep(1);
      setSelectedId(null);
      setCopyPack(null);
    },
    onError: (err: Error) => setFlash({ level: "err", text: err.message }),
  });

  const categories = categoriesQuery.data?.categories ?? ["tutte"];
  const objectiveOptions = objectivesQuery.data?.objectives ?? [];
  const items = listQuery.data?.items ?? [];
  const selectedImage = items.find((i) => i.id === selectedId);

  async function pickImage(image: ImageSummary) {
    setSelectedId(image.id);
    setCopyPack(null);
    setCaption("");
    try {
      const existing = await fetchImageCopy(image.id);
      if (existing?.copy) {
        setCopyPack(existing.copy);
        setCaption(captionFromCopy(existing.copy, platform));
      }
    } catch {
      /* no copy yet */
    }
  }

  function useSuggestedSlot() {
    const slot = slotQuery.data;
    if (!slot) return;
    setPlanDate(slot.scheduled_date);
    setPlanTime(slot.scheduled_time);
  }

  const canContinue =
    format === "story" || copyPack !== null;

  if (step === 2 && selectedId !== null) {
    const preview = selectedImage;
    return (
      <div className="space-y-6">
        <h3 className="text-lg font-medium">Step 2 · Pianificazione</h3>
        {preview ? (
          <img
            src={preview.media.processed}
            alt={preview.name}
            className="max-h-64 rounded-lg border border-[var(--story-border)]"
          />
        ) : null}

        {format === "story" ? (
          <div className="space-y-3">
            <fieldset className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  checked={storyKind === "single"}
                  onChange={() => setStoryKind("single")}
                />
                Una data e ora
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  checked={storyKind === "weekly"}
                  onChange={() => setStoryKind("weekly")}
                />
                Ogni settimana
              </label>
            </fieldset>
            {storyKind === "weekly" ? (
              <div className="grid gap-3 md:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-[var(--story-muted)]">Giorno</span>
                  <select
                    value={storyWeekday}
                    onChange={(e) => setStoryWeekday(Number(e.target.value))}
                    className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
                  >
                    {WEEKDAYS_IT.map((d, i) => (
                      <option key={d} value={i}>
                        {d}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-[var(--story-muted)]">Ora</span>
                  <input
                    type="time"
                    value={storyTime}
                    onChange={(e) => setStoryTime(e.target.value)}
                    className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
                  />
                </label>
              </div>
            ) : null}
          </div>
        ) : null}

        {(format !== "story" || storyKind === "single") && (
          <div className="space-y-3">
            {slotQuery.data ? (
              <div className="rounded-lg border border-[var(--story-accent)]/30 bg-[var(--story-accent)]/10 p-3 text-sm">
                Prossimo slot libero: {slotQuery.data.weekday_label} alle{" "}
                {slotQuery.data.time_hhmm} ({slotQuery.data.timezone})
                <button
                  type="button"
                  onClick={useSuggestedSlot}
                  className="ml-3 underline"
                >
                  Usa questo slot
                </button>
              </div>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="text-[var(--story-muted)]">Data</span>
                <input
                  type="date"
                  value={planDate}
                  onChange={(e) => setPlanDate(e.target.value)}
                  className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
                />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-[var(--story-muted)]">Ora</span>
                <input
                  type="time"
                  value={planTime}
                  onChange={(e) => setPlanTime(e.target.value)}
                  className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
                />
              </label>
            </div>
          </div>
        )}

        {format === "post" ? (
          <label className="block space-y-1 text-sm">
            <span className="text-[var(--story-muted)]">Caption per Meta</span>
            <textarea
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={5}
              className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
            />
          </label>
        ) : (
          <p className="text-sm text-[var(--story-muted)]">
            Le story si pubblicano solo come media, senza caption testuale.
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => setStep(1)}
            className="rounded-lg border border-[var(--story-border)] px-4 py-2 text-sm"
          >
            Torna allo Step 1
          </button>
          <button
            type="button"
            disabled={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
            className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
          >
            Salva pianificazione
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-medium">Step 1 · Seleziona immagine</h3>

      <div className="grid gap-3 md:grid-cols-3">
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Social</span>
          <select
            value={platform}
            onChange={(e) => {
              setPlatform(e.target.value);
              setPage(0);
              setSelectedId(null);
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
              setSelectedId(null);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            <option value="post">Post</option>
            <option value="story">Story</option>
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-[var(--story-muted)]">Categoria</span>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(0);
              setSelectedId(null);
            }}
            className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      {listQuery.isLoading ? (
        <p className="text-sm text-[var(--story-muted)]">Caricamento…</p>
      ) : items.length === 0 ? (
        <p className="rounded-lg border border-[var(--story-border)] p-4 text-sm text-[var(--story-muted)]">
          Nessuna immagine approvata per questo social/formato. Elabora in ① Seleziona e approva in
          ③ Approva.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {items.map((image) => (
              <button
                key={image.id}
                type="button"
                onClick={() => pickImage(image)}
                className={[
                  "rounded-xl border p-2 text-left transition-colors",
                  selectedId === image.id
                    ? "border-[var(--story-accent)] bg-[var(--story-accent)]/10"
                    : "border-[var(--story-border)] hover:border-[var(--story-muted)]",
                ].join(" ")}
              >
                <img
                  src={image.media.processed}
                  alt={image.name}
                  className="mb-2 aspect-square w-full rounded-lg object-cover"
                />
                <span className="line-clamp-2 text-xs">{image.name}</span>
              </button>
            ))}
          </div>
          <Pagination
            page={page}
            totalPages={listQuery.data?.total_pages ?? 1}
            total={listQuery.data?.total ?? 0}
            onPageChange={setPage}
          />
        </>
      )}

      {selectedId !== null && format === "post" ? (
        <div className="space-y-4 border-t border-[var(--story-border)] pt-6">
          <h4 className="font-medium">Immagine #{selectedId}</h4>
          <div className="grid gap-3 md:grid-cols-2">
            <fieldset className="space-y-2 text-sm md:col-span-2">
              <legend className="text-[var(--story-muted)]">Obiettivi contenuto (uno o più)</legend>
              <div className="flex flex-wrap gap-4">
                {objectiveOptions.map((o) => (
                  <label key={o} className="inline-flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedObjectives.includes(o)}
                      onChange={(e) => {
                        setSelectedObjectives((prev) => {
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
            <fieldset className="space-y-2 text-sm">
              <legend className="text-[var(--story-muted)]">Canali comunicazione</legend>
              {(["instagram", "facebook"] as const).map((ch) => (
                <label key={ch} className="mr-4 inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={channels.includes(ch)}
                    onChange={(e) => {
                      setChannels((prev) =>
                        e.target.checked ? [...prev, ch] : prev.filter((c) => c !== ch),
                      );
                    }}
                  />
                  {ch === "instagram" ? "Instagram" : "Facebook"}
                </label>
              ))}
            </fieldset>
          </div>
          <button
            type="button"
            disabled={channels.length === 0 || generateMutation.isPending}
            onClick={() => generateMutation.mutate()}
            className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
          >
            {copyPack ? "Rigenera copy" : "Genera copy"}
          </button>
          {copyPack ? <CopyPreview copy={copyPack} platform={platform} /> : null}
        </div>
      ) : null}

      {selectedId !== null && format === "story" ? (
        <p className="text-sm text-[var(--story-muted)]">
          Story selezionata: #{selectedId}. Continua per impostare data/ora o regola settimanale.
        </p>
      ) : null}

      <button
        type="button"
        disabled={selectedId === null || !canContinue}
        onClick={() => setStep(2)}
        className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
      >
        Continua allo Step 2 · Pianifica
      </button>

      {flash ? (
        <p
          className={[
            "text-sm whitespace-pre-wrap break-words",
            flash.level === "ok" ? "text-green-400" : "text-red-300",
          ].join(" ")}
        >
          {flash.text}
        </p>
      ) : null}
    </div>
  );
}

function CalendarEditDialog({
  events,
  onDone,
}: {
  events: CalendarEvent[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [selectedKey, setSelectedKey] = useState("");
  const [editDate, setEditDate] = useState("");
  const [editTime, setEditTime] = useState("");
  const [editCaption, setEditCaption] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const selected = events.find((e) => `${e.image_id}:${e.platform}` === selectedKey);

  function selectEvent(ev: CalendarEvent) {
    setSelectedKey(`${ev.image_id}:${ev.platform}`);
    const raw = ev.scheduled_for;
    const d = raw.slice(0, 10);
    const tMatch = raw.match(/T(\d{2}:\d{2})/);
    setEditDate(d);
    setEditTime(tMatch?.[1] ?? "12:00");
    setEditCaption(ev.caption ?? "");
  }

  const rescheduleMutation = useMutation({
    mutationFn: () =>
      reschedulePlan(selected!.image_id, selected!.platform, {
        scheduled_date: editDate,
        scheduled_time: editTime,
        caption: editCaption || undefined,
      }),
    onSuccess: (data) => {
      setMessage(data.message);
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      onDone();
    },
    onError: (err: Error) => setMessage(err.message),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelPlan(selected!.image_id, selected!.platform),
    onSuccess: (data) => {
      setMessage(data.message);
      queryClient.invalidateQueries({ queryKey: ["calendar"] });
      onDone();
    },
    onError: (err: Error) => setMessage(err.message),
  });

  return (
    <div className="space-y-4 rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-4">
      <h3 className="font-medium">Modifica pianificazione</h3>
      <label className="block space-y-1 text-sm">
        <span className="text-[var(--story-muted)]">Evento</span>
        <select
          value={selectedKey}
          onChange={(e) => {
            const ev = events.find((x) => `${x.image_id}:${x.platform}` === e.target.value);
            if (ev) selectEvent(ev);
          }}
          className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
        >
          <option value="">Seleziona…</option>
          {events.map((ev) => (
            <option key={`${ev.image_id}:${ev.platform}`} value={`${ev.image_id}:${ev.platform}`}>
              #{ev.image_id} · {ev.platform.toUpperCase()} · {ev.time_label} · {ev.image_name}
            </option>
          ))}
        </select>
      </label>

      {selected ? (
        <>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-[var(--story-muted)]">Nuova data</span>
              <input
                type="date"
                value={editDate}
                onChange={(e) => setEditDate(e.target.value)}
                className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-[var(--story-muted)]">Nuova ora</span>
              <input
                type="time"
                value={editTime}
                onChange={(e) => setEditTime(e.target.value)}
                className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
              />
            </label>
          </div>
          {selected.media_format === "post" ? (
            <label className="block space-y-1 text-sm">
              <span className="text-[var(--story-muted)]">Caption</span>
              <textarea
                value={editCaption}
                onChange={(e) => setEditCaption(e.target.value)}
                rows={4}
                className="w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2"
              />
            </label>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={rescheduleMutation.isPending}
              onClick={() => rescheduleMutation.mutate()}
              className="rounded-lg bg-[var(--story-accent)] px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
            >
              Salva modifiche
            </button>
            <button
              type="button"
              disabled={cancelMutation.isPending}
              onClick={() => cancelMutation.mutate()}
              className="rounded-lg border border-red-500/40 px-4 py-2 text-sm text-red-200 disabled:opacity-50"
            >
              Annulla pianificazione
            </button>
          </div>
        </>
      ) : null}
      {message ? <p className="text-sm text-[var(--story-muted)]">{message}</p> : null}
    </div>
  );
}

function CalendarView() {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [platform, setPlatform] = useState("tutti");
  const [category, setCategory] = useState("tutte");

  const categoriesQuery = useQuery({
    queryKey: ["config", "categories"],
    queryFn: fetchImageCategories,
  });

  const calendarQuery = useQuery({
    queryKey: ["calendar", year, month, platform, category],
    queryFn: () => fetchCalendar({ year, month, platform, category }),
  });

  const eventsQuery = useQuery({
    queryKey: ["calendar", "events", year, month, platform],
    queryFn: () => fetchCalendarEvents({ year, month, platform }),
  });

  const grid = useMemo(() => {
    const first = new Date(year, month - 1, 1);
    const startPad = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(year, month, 0).getDate();
    const cells: Array<number | null> = [];
    for (let i = 0; i < startPad; i += 1) cells.push(null);
    for (let d = 1; d <= daysInMonth; d += 1) cells.push(d);
    while (cells.length % 7 !== 0) cells.push(null);
    return cells;
  }, [year, month]);

  const byDay = calendarQuery.data?.by_day ?? {};
  const categories = categoriesQuery.data?.categories ?? ["tutte"];

  function shiftMonth(delta: number) {
    const d = new Date(year, month - 1 + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => shiftMonth(-1)}
            className="rounded-lg border border-[var(--story-border)] px-3 py-2 text-sm"
          >
            ◀
          </button>
          <span className="min-w-[10rem] text-center font-medium">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button
            type="button"
            onClick={() => shiftMonth(1)}
            className="rounded-lg border border-[var(--story-border)] px-3 py-2 text-sm"
          >
            ▶
          </button>
        </div>
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2 text-sm"
        >
          <option value="tutti">Tutti i social</option>
          <option value="instagram">Instagram</option>
          <option value="facebook">Facebook</option>
        </select>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2 text-sm"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>

      <p className="text-sm text-[var(--story-muted)]">
        Eventi nel mese: {calendarQuery.data?.total ?? 0}
      </p>

      <div className="grid grid-cols-7 gap-2 text-center text-xs font-semibold text-[var(--story-muted)]">
        {["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map((d) => (
          <div key={d}>{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-2">
        {grid.map((day, idx) => {
          const events = day != null ? byDay[String(day)] ?? [] : [];
          return (
            <div
              key={`${day ?? "x"}-${idx}`}
              className="min-h-[7rem] rounded-lg border border-[var(--story-border)] p-2 text-left"
            >
              {day != null ? <div className="mb-1 text-sm font-semibold">{day}</div> : null}
              {events.slice(0, 2).map((ev) => (
                <div key={ev.id} className="mb-1 text-[10px] leading-tight text-[var(--story-muted)]">
                  {ev.platform.toUpperCase()} · {ev.time_label}
                </div>
              ))}
              {events.length > 2 ? (
                <div className="text-[10px] text-[var(--story-muted)]">+{events.length - 2}</div>
              ) : null}
            </div>
          );
        })}
      </div>

      <CalendarEditDialog
        events={eventsQuery.data ?? []}
        onDone={() => {
          calendarQuery.refetch();
          eventsQuery.refetch();
        }}
      />
    </div>
  );
}

export function PlanPage() {
  const [tab, setTab] = useState<"plan" | "calendar">("plan");

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-semibold">④ Pianifica</h2>
        <p className="mt-1 text-[var(--story-muted)]">
          Seleziona immagine approvata, genera copy e pianifica nel calendario editoriale.
        </p>
      </header>

      <div className="flex gap-2 border-b border-[var(--story-border)]">
        {(
          [
            ["plan", "Pianifica"],
            ["calendar", "Calendario"],
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

      {tab === "plan" ? <PlanWizard /> : <CalendarView />}
    </div>
  );
}
