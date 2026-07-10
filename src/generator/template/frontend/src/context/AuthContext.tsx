import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { apiFetch } from "../api";

interface User {
  id: number;
  email: string;
  role: string;
}

interface AuthState {
  user: User | null;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const API = import.meta.env.VITE_API_URL ?? "";
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (localStorage.getItem("access_token")) {
      apiFetch("/api/auth/me").then(async (r) => {
        if (r.ok) setUser((await r.json()) as User);
      });
    }
  }, []);

  async function login(email: string, password: string): Promise<boolean> {
    const res = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { access_token: string };
    localStorage.setItem("access_token", data.access_token);
    const me = await apiFetch("/api/auth/me");
    if (me.ok) setUser((await me.json()) as User);
    return true;
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans AuthProvider");
  return ctx;
}
