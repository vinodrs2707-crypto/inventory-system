import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getTokens, request, setOnAuthLost, setTokens } from "./api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getTokens()));

  useEffect(() => {
    setOnAuthLost(() => setUser(null));
    if (!getTokens()) return;
    request("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await request("/auth/login", { method: "POST", body: { email, password }, auth: false });
    setTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
    const me = await request("/auth/me");
    setUser(me);
    return me;
  }, []);

  const register = useCallback(
    async (fullName, email, password) => {
      await request("/auth/register", {
        method: "POST",
        body: { full_name: fullName, email, password },
        auth: false,
      });
      return login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    setTokens(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      setUser,
      isAdmin: user?.role === "administrator",
      isStaff: user?.role === "administrator" || user?.role === "inventory_manager",
    }),
    [user, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}