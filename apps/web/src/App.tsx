import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { t } from "./i18n";
import { Assistant } from "./pages/Assistant";
import { Login } from "./pages/Login";

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="center">Chargement…</div>;
  if (!me) return <Navigate to="/connexion" replace state={{ from: location.pathname }} />;
  return children;
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/connexion" element={<Login />} />
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Assistant />} />
          <Route path="*" element={<div className="center">{t.errors.notFound}</div>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
