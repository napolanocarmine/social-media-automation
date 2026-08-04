import { Link } from "react-router-dom";

export function SourceChoicePage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header className="text-center">
        <h2 className="text-2xl font-semibold">① Seleziona contenuto</h2>
        <p className="mt-2 text-[var(--story-muted)]">
          Scegli come aggiungere le foto al flusso editoriale.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link
          to="/workflow/upload"
          className="group rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-6 transition hover:border-[var(--story-accent)]/60 hover:bg-[var(--story-accent)]/5"
        >
          <p className="text-lg font-medium group-hover:text-[var(--story-accent)]">
            Carica dal dispositivo
          </p>
          <p className="mt-2 text-sm text-[var(--story-muted)]">
            Drag &amp; drop o selezione da PC/cellulare. Valida le dimensioni, opzionalmente
            ritocco AI, poi vai in pianificazione.
          </p>
        </Link>

        <Link
          to="/workflow/select"
          className="group rounded-xl border border-[var(--story-border)] bg-[var(--story-surface)] p-6 transition hover:border-[var(--story-accent)]/60 hover:bg-[var(--story-accent)]/5"
        >
          <p className="text-lg font-medium group-hover:text-[var(--story-accent)]">
            Carica da Google Drive
          </p>
          <p className="mt-2 text-sm text-[var(--story-muted)]">
            Percorso classico: seleziona asset dal Drive, batch Story AI, approvazione e
            pianificazione.
          </p>
        </Link>
      </div>
    </div>
  );
}
