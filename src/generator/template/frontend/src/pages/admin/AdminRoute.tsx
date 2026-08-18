import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";

// Garde côté frontend (Chap 9) — UX seulement, jamais la vraie protection :
// chaque route /api/admin/* vérifie require_admin côté serveur, c'est la
// seule qui compte contre un appel API direct. `loading` évite de renvoyer
// à tort un admin déjà connecté vers / avant que /api/auth/me n'ait résolu.
export default function AdminRoute() {
  const { user, loading } = useAuth();

  if (loading) return null;
  if (!user || user.role !== "admin") return <Navigate to="/" replace />;
  return <Outlet />;
}
