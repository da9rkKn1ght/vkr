import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    try {
      await login(username, password);
      toast.success("Авторизация выполнена");
      const destination = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/";
      navigate(destination, { replace: true });
    } catch {
      toast.error("Неверный логин или пароль");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_10%_20%,rgba(26,157,139,0.26),transparent_36%),radial-gradient(circle_at_88%_12%,rgba(244,157,55,0.24),transparent_36%),linear-gradient(160deg,#f8fafc,#e8eef5)] px-4">
      <section className="w-full max-w-md rounded-3xl border border-white/60 bg-white/85 p-8 shadow-panel backdrop-blur-xl">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink">Вход в систему</h1>
        <p className="mt-2 text-sm text-slate-600">
          Используйте учетную запись администратора или менеджера для доступа к мониторингу.
        </p>
        <form onSubmit={onSubmit} className="mt-8 space-y-4">
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Логин</span>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none ring-accent transition focus:border-accent focus:ring-2"
              placeholder="admin"
              required
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate-700">Пароль</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none ring-accent transition focus:border-accent focus:ring-2"
              placeholder="********"
              required
            />
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-2xl bg-ink px-4 py-3 font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {submitting ? "Выполняется..." : "Войти"}
          </button>
        </form>
      </section>
    </div>
  );
}

