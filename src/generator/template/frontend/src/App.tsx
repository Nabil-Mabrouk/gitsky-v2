import { Routes, Route, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./context/AuthContext";
import Learn from "./pages/Learn";
import Login from "./pages/Login";
import FleetGrid from "./pages/FleetGrid";

export default function App() {
  const { t, i18n } = useTranslation();
  const { user, logout } = useAuth();

  const toggleLang = () =>
    i18n.changeLanguage(i18n.language.startsWith("fr") ? "en" : "fr");

  return (
    <div className="min-h-screen">
      <nav className="flex items-center gap-4 border-b p-4">
        <Link to="/learn" className="font-medium">
          {t("nav.learn")}
        </Link>
        {user?.role === "admin" && (
          <Link to="/fleet" className="font-medium">
            {t("fleet.nav")}
          </Link>
        )}
        <button onClick={toggleLang} className="text-sm uppercase">
          {i18n.language.slice(0, 2)}
        </button>
        <span className="flex-1" />
        {user ? (
          <button onClick={logout}>{t("nav.logout")}</button>
        ) : (
          <Link to="/login">{t("nav.login")}</Link>
        )}
      </nav>
      <main className="p-6">
        <Routes>
          <Route path="/" element={<Learn />} />
          <Route path="/learn" element={<Learn />} />
          <Route path="/login" element={<Login />} />
          <Route path="/fleet" element={<FleetGrid />} />
        </Routes>
      </main>
    </div>
  );
}
