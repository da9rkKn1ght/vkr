import { Link, NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

function navClassName(active: boolean): string {
  return active
    ? "rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white"
    : "rounded-full px-4 py-2 text-sm font-semibold text-slate-600 transition hover:bg-slate-200";
}

export function AppLayout() {
  const { user, isAdmin, logout } = useAuth();

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_12%_12%,rgba(26,157,139,0.22),transparent_40%),radial-gradient(circle_at_84%_6%,rgba(244,157,55,0.22),transparent_36%),linear-gradient(165deg,#f7fafc_0%,#eaf1f6_100%)] text-ink">
      <header className="sticky top-0 z-40 border-b border-white/60 bg-white/75 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-3 md:px-8">
          <Link to="/" className="font-display text-lg font-semibold tracking-tight text-ink">
            Монитор дисциплины
          </Link>
          <nav className="flex items-center gap-1 rounded-full border border-slate-200 bg-white/90 p-1">
            <NavLink to="/" className={({ isActive }) => navClassName(isActive)} end>
              Дашборд
            </NavLink>
            <NavLink to="/incidents" className={({ isActive }) => navClassName(isActive)}>
              Инциденты
            </NavLink>
            {isAdmin && (
              <NavLink to="/cameras" className={({ isActive }) => navClassName(isActive)}>
                Камеры
              </NavLink>
            )}
          </nav>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-600 sm:inline">{user?.username}</span>
            <button
              type="button"
              onClick={logout}
              className="rounded-full border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-ink hover:text-ink"
            >
              Выйти
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl px-4 py-8 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}
