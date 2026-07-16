type PaginationProps = {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
};

export function Pagination({ page, totalPages, total, onPageChange }: PaginationProps) {
  if (total === 0) {
    return null;
  }
  const safeTotalPages = Math.max(1, totalPages);
  const current = Math.min(page, safeTotalPages - 1);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--story-muted)]">
      <span>
        Pagina {current + 1} di {safeTotalPages} · {total} elementi
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={current <= 0}
          onClick={() => onPageChange(current - 1)}
          className="rounded-lg border border-[var(--story-border)] px-3 py-1.5 disabled:opacity-40"
        >
          ◀
        </button>
        <button
          type="button"
          disabled={current >= safeTotalPages - 1}
          onClick={() => onPageChange(current + 1)}
          className="rounded-lg border border-[var(--story-border)] px-3 py-1.5 disabled:opacity-40"
        >
          ▶
        </button>
      </div>
    </div>
  );
}
