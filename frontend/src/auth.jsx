import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api, clearToken, hasToken, saveToken } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    if (!hasToken()) {
      setReady(true);
      return () => { alive = false; };
    }
    api("/auth/me")
      .then((profile) => { if (alive) setUser(profile); })
      .catch(() => { clearToken(); if (alive) setUser(null); })
      .finally(() => { if (alive) setReady(true); });
    return () => { alive = false; };
  }, []);

  const value = useMemo(() => ({
    user,
    ready,
    async login(email, password) {
      const result = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      saveToken(result.token);
      setUser(result.user);
      return result.user;
    },
    async register(payload) {
      return api("/auth/register", { method: "POST", body: JSON.stringify(payload) });
    },
    logout() {
      clearToken();
      setUser(null);
    },
  }), [user, ready]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider.");
  return value;
}
