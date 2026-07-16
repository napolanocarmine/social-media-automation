export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--story-border)] bg-[var(--story-surface)]/50 p-8">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-2 max-w-xl text-[var(--story-muted)]">{description}</p>
      <p className="mt-4 text-sm text-[var(--story-muted)]">
        Pagina in migrazione da Streamlit — vedi{" "}
        <code className="rounded bg-black/30 px-1">docs/migrazione-fe-react.md</code>.
      </p>
    </div>
  );
}
