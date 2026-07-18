import { Routes, Route, Link } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import Composer from "./pages/Composer";
import Login from "./pages/Login";

// MezouedAI : l'app EST le compositeur. On remplace le App.tsx du châssis
// (overlay projet) — bespoke assumé, hors propagation `copier update`.
export default function App() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <nav className="flex items-center gap-4 border-b p-4">
        <Link to="/" className="font-bold">
          🎵 MezouedAI
        </Link>
        <span className="flex-1" />
        {user ? (
          <button onClick={logout}>Déconnexion</button>
        ) : (
          <Link to="/login">Connexion</Link>
        )}
      </nav>
      <main className="p-6">
        <Routes>
          <Route path="/" element={<Composer />} />
          <Route path="/login" element={<Login />} />
        </Routes>
      </main>
    </div>
  );
}
