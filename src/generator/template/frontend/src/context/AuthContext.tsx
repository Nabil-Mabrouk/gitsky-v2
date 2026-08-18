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
  loading: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => void;
}

const API = import.meta.env.VITE_API_URL ?? "";
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // Le check initial (/api/auth/me) est async : un guard basé uniquement sur
  // `user` renverrait à tort un admin déjà connecté vers / à chaque
  // rafraîchissement, le temps que ce fetch résolve (AdminRoute, Chap 9).
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (localStorage.getItem("access_token")) {
      apiFetch("/api/auth/me")
        .then(async (r) => {
          if (r.ok) setUser((await r.json()) as User);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
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
    // Expire le cookie refresh HttpOnly côté serveur : sans cet appel, il
    // resterait valable 7 jours sur la machine après la « déconnexion ».
    void fetch(`${API}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    localStorage.removeItem("access_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
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
