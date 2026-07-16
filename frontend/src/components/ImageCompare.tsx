import { useState } from "react";
import type { ImageSummary } from "../lib/api/client";
import { ImageLightbox } from "./ImageLightbox";

const statusStyles: Record<string, string> = {
  pending: "bg-amber-500/20 text-amber-200",
  approved: "bg-emerald-500/20 text-emerald-200",
  rejected: "bg-red-500/20 text-red-200",
};

const statusLabels: Record<string, string> = {
  pending: "In attesa",
  approved: "Approvata",
  rejected: "Rifiutata",
};

export function ApprovalBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusStyles[status] ?? "bg-zinc-500/20"}`}
    >
      {statusLabels[status] ?? status}
    </span>
  );
}

function ImagePreview({
  src,
  alt,
  compact,
  placeholder,
  enlargeLabel,
  onEnlarge,
}: {
  src?: string;
  alt: string;
  compact: boolean;
  placeholder: string;
  enlargeLabel: string;
  onEnlarge?: () => void;
}) {
  const frameClass = compact
    ? "flex h-24 items-center justify-center overflow-hidden rounded-md border border-[var(--story-border)] bg-black/20"
    : "flex h-48 items-center justify-center overflow-hidden rounded-lg border border-[var(--story-border)] bg-black/20";

  if (!src) {
    return (
      <div
        className={[
          frameClass,
          "border-dashed px-2 text-center text-[var(--story-muted)]",
          compact ? "text-[10px]" : "text-sm",
        ].join(" ")}
      >
        {placeholder}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onEnlarge}
      className={[
        frameClass,
        "group relative w-full cursor-zoom-in transition hover:border-[var(--story-accent)]/60 hover:ring-1 hover:ring-[var(--story-accent)]/40",
      ].join(" ")}
      aria-label={`Ingrandisci: ${enlargeLabel}`}
      title="Clicca per ingrandire"
    >
      <img src={src} alt={alt} className="max-h-full max-w-full object-contain" loading="lazy" />
      <span className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-1.5 pb-1 pt-4 text-center text-[10px] text-white/90 opacity-0 transition group-hover:opacity-100">
        Ingrandisci
      </span>
    </button>
  );
}

type LightboxState = {
  src: string;
  alt: string;
  label: string;
};

export function ImageCompare({
  image,
  compact = false,
}: {
  image: ImageSummary;
  compact?: boolean;
}) {
  const [lightbox, setLightbox] = useState<LightboxState | null>(null);

  const metaParts: string[] = [];
  if (image.visual_score != null) metaParts.push(`Score ${image.visual_score.toFixed(1)}`);
  if (image.visual_status) metaParts.push(image.visual_status);
  if (image.editing_required != null) {
    metaParts.push(image.editing_required ? "Editing sì" : "Editing no");
  }
  if (image.visual_method) metaParts.push(image.visual_method);

  const originalSrc = image.has_original_file ? image.media.original : undefined;
  const processedSrc = image.has_processed_file ? image.media.processed : undefined;
  const originalLabel = compact ? "Originale" : "Originale Drive";
  const processedLabel = compact ? "Asset finale" : "Asset finale";

  return (
    <>
      <div className={compact ? "space-y-1.5" : "space-y-3"}>
        {metaParts.length > 0 && (
          <p
            className={[
              "truncate text-[var(--story-muted)]",
              compact ? "text-[10px] leading-tight" : "text-sm",
            ].join(" ")}
            title={metaParts.join(" · ")}
          >
            {metaParts.join(" · ")}
          </p>
        )}
        <div className={compact ? "grid grid-cols-2 gap-1.5" : "grid gap-4 md:grid-cols-2"}>
          <figure className={compact ? "min-w-0 space-y-0.5" : "space-y-2"}>
            <figcaption className="text-[10px] uppercase tracking-wide text-[var(--story-muted)]">
              {compact ? "Orig." : "Originale Drive"}
            </figcaption>
            <ImagePreview
              src={originalSrc}
              alt={`Originale ${image.name}`}
              compact={compact}
              placeholder={compact ? "Non in cache" : "Originale non in cache locale"}
              enlargeLabel={originalLabel}
              onEnlarge={
                originalSrc
                  ? () =>
                      setLightbox({
                        src: originalSrc,
                        alt: `Originale ${image.name}`,
                        label: `${originalLabel} · #${image.id} · ${image.name}`,
                      })
                  : undefined
              }
            />
          </figure>
          <figure className={compact ? "min-w-0 space-y-0.5" : "space-y-2"}>
            <figcaption className="text-[10px] uppercase tracking-wide text-[var(--story-muted)]">
              {compact ? "Finale" : "Asset finale"}
            </figcaption>
            <ImagePreview
              src={processedSrc}
              alt={`Processata ${image.name}`}
              compact={compact}
              placeholder={compact ? "Assente" : "File output assente"}
              enlargeLabel={processedLabel}
              onEnlarge={
                processedSrc
                  ? () =>
                      setLightbox({
                        src: processedSrc,
                        alt: `Processata ${image.name}`,
                        label: `${processedLabel} · #${image.id} · ${image.name}`,
                      })
                  : undefined
              }
            />
          </figure>
        </div>
      </div>

      {lightbox && (
        <ImageLightbox
          src={lightbox.src}
          alt={lightbox.alt}
          label={lightbox.label}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  );
}
