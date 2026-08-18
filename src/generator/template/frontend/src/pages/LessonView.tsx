import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch } from "../api";

interface LessonData {
  id: number;
  title: string;
  order: number;
  content: string;
}

type LoadState = "loading" | "ok" | "not_found" | "unauthorized" | "forbidden";

// Contenu d'une leçon (Chap 11) — le contrôle d'accès est fait côté API
// (401 non connecté, 403 rôle insuffisant) : ce composant ne fait que
// refléter ces réponses, jamais sa propre logique de permission.
export default function LessonView() {
  const { t } = useTranslation();
  const { slug, lessonId } = useParams<{ slug: string; lessonId: string }>();
  const [lesson, setLesson] = useState<LessonData | null>(null);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    setLesson(null);
    setState("loading");
    apiFetch(`/api/content/tutorials/${slug}/lessons/${lessonId}`).then(async (r) => {
      if (r.ok) {
        setLesson((await r.json()) as LessonData);
        setState("ok");
      } else if (r.status === 401) setState("unauthorized");
      else if (r.status === 403) setState("forbidden");
      else setState("not_found");
    });
  }, [slug, lessonId]);

  const backLink = (
    <Link to={`/learn/${slug}`} className="text-sm opacity-70">
      {t("learn.detail.back")}
    </Link>
  );

  if (state === "loading") return <p>{t("learn.detail.loading")}</p>;
  if (state === "not_found")
    return (
      <div>
        {backLink}
        <p className="mt-2 text-sm text-red-600">{t("learn.detail.notFound")}</p>
      </div>
    );
  if (state === "unauthorized")
    return (
      <div>
        {backLink}
        <p className="mt-2 text-sm">
          {t("learn.lesson.unauthorized")}{" "}
          <Link to="/login" className="underline">
            {t("nav.login")}
          </Link>
        </p>
      </div>
    );
  if (state === "forbidden")
    return (
      <div>
        {backLink}
        <p className="mt-2 text-sm">{t("learn.lesson.forbidden")}</p>
      </div>
    );

  return (
    <article>
      {backLink}
      <h1 className="mt-2 text-2xl font-bold">{lesson!.title}</h1>
      <div className="prose mt-4 max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{lesson!.content}</ReactMarkdown>
      </div>
    </article>
  );
}
