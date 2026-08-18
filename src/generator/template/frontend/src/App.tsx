import { Routes, Route, Link, Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./context/AuthContext";
import Learn from "./pages/Learn";
import Login from "./pages/Login";
import FleetGrid from "./pages/FleetGrid";
import TutorialDetail from "./pages/TutorialDetail";
import LessonView from "./pages/LessonView";
import AdminRoute from "./pages/admin/AdminRoute";
import AdminLayout from "./pages/admin/AdminLayout";

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
          <Link to="/admin" className="font-medium">
            {t("admin.nav")}
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
          <Route path="/learn/:slug" element={<TutorialDetail />} />
          <Route path="/learn/:slug/lessons/:lessonId" element={<LessonView />} />
          <Route path="/login" element={<Login />} />
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<Navigate to="fleet" replace />} />
              <Route path="fleet" element={<FleetGrid />} />
            </Route>
          </Route>
        </Routes>
      </main>
    </div>
  );
}
