// frontend/src/context/AuthContext.tsx

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { API_BASE_URL } from "../services/api";

export type Role = "admin" | "supervisor" | "officer";

export interface AuthUser {
  user_id: number;
  full_name: string;
  badge_number: string | null;
  email: string;
  role: Role;
  role_label: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
  permissions: string[];
}

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  can: (permission: string) => boolean;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "itms_token";
const USER_KEY = "itms_user";

async function fetchMe(token: string): Promise<AuthUser> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Token invalid.");
  }

  return response.json() as Promise<AuthUser>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    token: null,
    loading: true,
  });

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    const cachedUser = localStorage.getItem(USER_KEY);

    if (!token) {
      setState({ user: null, token: null, loading: false });
      return;
    }

    if (cachedUser) {
      try {
        setState({
          user: JSON.parse(cachedUser) as AuthUser,
          token,
          loading: false,
        });
      } catch {
        localStorage.removeItem(USER_KEY);
      }
    }

    fetchMe(token)
      .then((user) => {
        localStorage.setItem(USER_KEY, JSON.stringify(user));
        setState({ user, token, loading: false });
      })
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        setState({ user: null, token: null, loading: false });
      });
  }, []);

  async function login(email: string, password: string): Promise<void> {
    const form = new URLSearchParams();
    form.append("username", email);
    form.append("password", password);

    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: form,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail ?? "Login failed. Check your credentials.");
    }

    const data = await response.json();
    const token = data.access_token as string;

    const user = await fetchMe(token);

    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));

    setState({
      user,
      token,
      loading: false,
    });
  }

  function logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setState({
      user: null,
      token: null,
      loading: false,
    });
  }

  function can(permission: string): boolean {
    return state.user?.permissions.includes(permission) ?? false;
  }

  function hasRole(...roles: Role[]): boolean {
    if (!state.user) return false;
    return roles.includes(state.user.role);
  }

  return (
    <AuthContext.Provider
      value={{
        ...state,
        login,
        logout,
        can,
        hasRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>.");
  }

  return context;
}
