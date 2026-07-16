import { NavLink, Outlet } from "react-router-dom";

const workflowLinks = [
  { to: "/", label: "Home", end: true },
  { to: "/workflow/select", label: "① Seleziona" },
  { to: "/workflow/output", label: "② Output AI" },
  { to: "/workflow/approve", label: "③ Approva" },
  { to: "/workflow/plan", label: "④ Pianifica" },
  { to: "/workflow/publish", label: "⑤ Pubblica" },
  { to: "/automation", label: "Automazione" },
];

function navClassName({ isActive }: { isActive: boolean }) {
  return [
    "block rounded-lg px-3 py-2 text-sm transition-colors",
    isActive
      ? "bg-[var(--story-accent)]/20 text-[var(--story-accent)] font-medium"
      : "text-[var(--story-muted)] hover:bg-[var(--story-surface)] hover:text-[var(--story-text)]",
  ].join(" ");
}

export function AppLayout() {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-[var(--story-border)] bg-[var(--story-surface)] p-4 lg:border-b-0 lg:border-r">
        <div className="mb-6">
          <p className="text-xs uppercase tracking-wider text-[var(--story-muted)]">
            Story Social
          </p>
          <h1 className="text-lg font-semibold">Editorial Tool</h1>
          <p className="mt-1 text-xs text-[var(--story-muted)]">
            Drive → AI → approva → pianifica → Meta
          </p>
        </div>
        <nav className="space-y-1">
          <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wide text-[var(--story-muted)]">
            Percorso
          </p>
          {workflowLinks.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end} className={navClassName}>
              {link.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
