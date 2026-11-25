import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, post, type Me } from "./api";

type AuthState = {
  me: Me | null;
  loading: boolean;
  login: (login: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (...roles: string[]) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (login: string, password: string) => {
    await post("/auth/login", { login, password });
    setMe(await api<Me>("/auth/me"));
  }, []);

  const logout = useCallback(async () => {
    try {
      await post("/auth/logout");
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    setMe(null);
  }, []);

  const can = useCallback((...roles: string[]) => !!me && me.roles.some((r) => roles.includes(r)), [me]);

  return <AuthContext.Provider value={{ me, loading, login, logout, can }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider manquant");
  return ctx;
}

// Rôles, comme côté API (services/api/src/urag_api/deps.py).
export const CAN_ASK = ["user", "doc_admin", "org_admin"];
export const DOC_ADMIN = ["doc_admin", "org_admin"];
export const ORG_ADMIN = ["org_admin"];
