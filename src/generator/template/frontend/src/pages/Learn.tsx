import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";

interface Tutorial {
  id: number;
  title: string;
  slug: string;
  lang: string;
  access_role: string;
}

// Catalogue public : ne montre que les cours de la langue courante (Chap 11).
export default function Learn() {
  const { t, i18n } = useTranslation();
  const [tutorials, setTutorials] = useState<Tutorial[]>([]);

  useEffect(() => {
    const lang = i18n.language.split("-")[0];
    apiFetch(`/api/content/tutorials?lang=${lang}`).then(async (r) => {
      if (r.ok) setTutorials((await r.json()) as Tutorial[]);
    });
  }, [i18n.language]);

  return (
    <section>
      <h1 className="text-2xl font-bold">{t("learn.title")}</h1>
      <ul className="mt-4 grid gap-2">
        {tutorials.map((tut) => (
          <li key={tut.id} className="rounded border p-3">
            <span className="font-medium">{tut.title}</span>
            {tut.access_role !== "anonymous" && (
              <span className="ml-2 rounded bg-black/10 px-2 py-0.5 text-xs">
                {t("learn.premium")}
              </span>
            )}
          </li>
        ))}
        {tutorials.length === 0 && <li className="text-sm opacity-60">{t("learn.empty")}</li>}
      </ul>
    </section>
  );
}
