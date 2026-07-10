import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(false);
    if (await login(email, password)) navigate("/learn");
    else setError(true);
  }

  return (
    <form onSubmit={onSubmit} className="grid max-w-sm gap-3">
      <h1 className="text-2xl font-bold">{t("auth.login.title")}</h1>
      <input
        className="rounded border p-2"
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t("auth.login.email")}
      />
      <input
        className="rounded border p-2"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={t("auth.login.password")}
      />
      {error && <p className="text-sm text-red-600">{t("auth.login.error")}</p>}
      <button
        className="rounded p-2 font-medium text-white"
        style={{ background: "var(--color-primary)" }}
      >
        {t("auth.login.submit")}
      </button>
    </form>
  );
}
