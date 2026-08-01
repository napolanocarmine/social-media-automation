type FormatPlatformFiltersProps = {
  format: string;
  platform: string;
  onFormatChange: (format: string) => void;
  onPlatformChange: (platform: string) => void;
  formatClassName?: string;
  platformClassName?: string;
  storyOptionLabel?: string;
};

export function FormatPlatformFilters({
  format,
  platform,
  onFormatChange,
  onPlatformChange,
  formatClassName = "w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2",
  platformClassName = "w-full rounded-lg border border-[var(--story-border)] bg-[var(--story-bg)] px-3 py-2",
  storyOptionLabel = "Story (1080×1920, IG + FB)",
}: FormatPlatformFiltersProps) {
  const isStory = format === "story";

  return (
    <>
      <label className="space-y-1 text-sm">
        <span className="text-[var(--story-muted)]">Formato</span>
        <select
          value={format}
          onChange={(e) => {
            const next = e.target.value;
            onFormatChange(next);
            if (next === "story") {
              onPlatformChange("instagram");
            }
          }}
          className={formatClassName}
        >
          <option value="post">Post (feed)</option>
          <option value="story">{storyOptionLabel}</option>
        </select>
      </label>
      <label className="space-y-1 text-sm">
        <span className="text-[var(--story-muted)]">Canale</span>
        <select
          value={isStory ? "both" : platform}
          disabled={isStory}
          onChange={(e) => onPlatformChange(e.target.value)}
          className={[
            platformClassName,
            isStory ? "cursor-not-allowed opacity-70" : "",
          ].join(" ")}
          title={
            isStory
              ? "Le story vengono sempre pubblicate su Instagram e Facebook"
              : undefined
          }
        >
          {isStory ? (
            <option value="both">Instagram + Facebook</option>
          ) : (
            <>
              <option value="instagram">Instagram</option>
              <option value="facebook">Facebook</option>
            </>
          )}
        </select>
      </label>
    </>
  );
}

/** Piattaforma da inviare alle API (story → instagram, il backend pubblica su entrambi). */
export function platformForApi(format: string, platform: string): string {
  return format === "story" ? "instagram" : platform;
}

export function channelsForBatch(format: string, platform: string): string[] {
  return format === "story" ? ["instagram", "facebook"] : [platform];
}
