import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { t } from "../i18n";

export function Login() {
  const { me, login } = useAuth();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (me) return <Navigate to={(location.state as { from?: string } | null)?.from ?? "/"} replace />;

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setPending(true);
    setError(null);
    try {
      await login(String(form.get("login") ?? ""), String(form.get("password") ?? ""));
    } catch (err) {
      setError(err instanceof ApiError && err.status < 500 ? t.login.invalid : t.login.unavailable);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="login-page">
      <form className="login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="brand">
          <img src="/logo.svg" alt="" />
          <div>
            <div className="brand-name">{t.product}</div>
            <div className="brand-tag">{t.tagline}</div>
          </div>
        </div>
        <h1 id="login-title">{t.login.title}</h1>
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}
        <div className="field">
          <label htmlFor="login">{t.login.login}</label>
          <input className="input" id="login" name="login" autoComplete="username" required autoFocus />
        </div>
        <div className="field">
          <label htmlFor="password">{t.login.password}</label>
          <input className="input" id="password" name="password" type="password" autoComplete="current-password" required />
        </div>
        <button className="btn btn-primary" type="submit" disabled={pending}>
          {pending ? t.login.pending : t.login.submit}
        </button>
      </form>
    </main>
  );
}
