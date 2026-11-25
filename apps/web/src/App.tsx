import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";
import { DOC_ADMIN, ORG_ADMIN, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { t } from "./i18n";
import { Admin } from "./pages/Admin";
import { Assistant } from "./pages/Assistant";
import { Dashboard } from "./pages/Dashboard";
import { Documents } from "./pages/Documents";
import { Login } from "./pages/Login";
import { Sources } from "./pages/Sources";

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="center">Chargement…</div>;
  if (!me) return <Navigate to="/connexion" replace state={{ from: location.pathname }} />;
  return children;
}

function RequireRole({ roles, children }: { roles: string[]; children: ReactNode }) {
  const { can } = useAuth();
  return can(...roles) ? children : <div className="center">{t.errors.forbidden}</div>;
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
          <Route path="tableau-de-bord" element={<RequireRole roles={DOC_ADMIN}><Dashboard /></RequireRole>} />
          <Route path="administration" element={<RequireRole roles={ORG_ADMIN}><Admin /></RequireRole>} />
          <Route path="sources" element={<RequireRole roles={DOC_ADMIN}><Sources /></RequireRole>} />
          <Route path="documents" element={<RequireRole roles={DOC_ADMIN}><Documents /></RequireRole>} />
          <Route path="*" element={<div className="center">{t.errors.notFound}</div>} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
