import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiRequest } from "../lib/api";
import { clearTokens, getStoredAccessToken, getStoredRefreshToken, saveTokens } from "../lib/storage";
import type { AuthTokens, UserMe } from "../types";

type AuthContextValue = {
  user: UserMe | null;
  accessToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  ensureUser: () => Promise<UserMe | null>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(getStoredAccessToken());
  const [refreshToken, setRefreshToken] = useState<string | null>(getStoredRefreshToken());
  const [user, setUser] = useState<UserMe | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const logout = useCallback(() => {
    clearTokens();
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
  }, []);

  const fetchMe = useCallback(
    async (token: string): Promise<UserMe> => {
      return apiRequest<UserMe>("/auth/me", { token });
    },
    [],
  );

  const refreshAccessToken = useCallback(async (): Promise<string | null> => {
    if (!refreshToken) {
      return null;
    }
    try {
      const tokens = await apiRequest<AuthTokens>("/auth/refresh", {
        method: "POST",
        body: { refresh_token: refreshToken },
      });
      saveTokens(tokens.access_token, tokens.refresh_token);
      setAccessToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);
      return tokens.access_token;
    } catch {
      return null;
    }
  }, [refreshToken]);

  const ensureUser = useCallback(async (): Promise<UserMe | null> => {
    if (!accessToken) {
      return null;
    }
    try {
      const me = await fetchMe(accessToken);
      setUser(me);
      return me;
    } catch {
      const refreshed = await refreshAccessToken();
      if (!refreshed) {
        logout();
        return null;
      }
      try {
        const me = await fetchMe(refreshed);
        setUser(me);
        return me;
      } catch {
        logout();
        return null;
      }
    }
  }, [accessToken, fetchMe, logout, refreshAccessToken]);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!accessToken) {
        if (active) {
          setIsLoading(false);
        }
        return;
      }
      await ensureUser();
      if (active) {
        setIsLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [accessToken, ensureUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await apiRequest<AuthTokens>("/auth/login", {
        method: "POST",
        body: { username, password },
      });
      saveTokens(tokens.access_token, tokens.refresh_token);
      setAccessToken(tokens.access_token);
      setRefreshToken(tokens.refresh_token);

      const me = await fetchMe(tokens.access_token);
      setUser(me);
    },
    [fetchMe],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      isLoading,
      isAuthenticated: Boolean(accessToken && user),
      isAdmin: user?.role === "admin",
      login,
      logout,
      ensureUser,
    }),
    [accessToken, ensureUser, isLoading, login, logout, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

