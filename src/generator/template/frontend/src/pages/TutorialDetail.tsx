import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";

interface LessonSummary {
  id: number;
  title: string;
  order: number;
}

interface TutorialDetailData {
  id: number;
  title: string;
  slug: string;
  lang: string;
  access_role: string;
  lessons: LessonSummary[];
}

// Liste des leçons d'un tutoriel (Chap 11) — GET /api/content/tutorials/{slug}
// est public, le contrôle d'accès réel se fait par leçon (LessonView).
export default function TutorialDetail() {
  const { t } = useTranslation();
  const { slug } = useParams<{ slug: string }>();
  const [tutorial, setTutorial] = useState<TutorialDetailData | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    setTutorial(null);
    setNotFound(false);
    apiFetch(`/api/content/tutorials/${slug}`).then(async (r) => {
      if (r.ok) setTutorial((await r.json()) as TutorialDetailData);
      else setNotFound(true);
    });
  }, [slug]);

  if (notFound) return <p className="text-sm text-red-600">{t("learn.detail.notFound")}</p>;
  if (!tutorial) return <p>{t("learn.detail.loading")}</p>;

  return (
    <section>
      <Link to="/learn" className="text-sm opacity-70">
        {t("learn.detail.back")}
      </Link>
      <h1 className="mt-2 text-2xl font-bold">{tutorial.title}</h1>
      <ol className="mt-4 grid gap-2">
        {[...tutorial.lessons]
          .sort((a, b) => a.order - b.order)
          .map((lesson) => (
            <li key={lesson.id} className="rounded border p-3">
              <Link to={`/learn/${tutorial.slug}/lessons/${lesson.id}`} className="font-medium">
                {lesson.title}
              </Link>
            </li>
          ))}
      </ol>
    </section>
  );
}
