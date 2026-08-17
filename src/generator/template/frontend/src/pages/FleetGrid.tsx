import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiFetch } from "../api";

// Grille de projets de la flotte (Chap 19) — vue MVP : liste triable de
// GET /api/fleet/projects, réservée à l'admin côté API (require_admin). Les
// onglets par projet, alertes et agrégation de coûts restent hors périmètre
// (aucune source de données pour eux n'existe encore côté backend).
interface FleetProject {
  id: number;
  name: string;
  tier: string;
  domain: string | null;
  status: string;
  publish_status: string;
  template_version: string | null;
}

type SortKey = keyof Pick<
  FleetProject,
  "name" | "tier" | "domain" | "status" | "publish_status"
>;

export default function FleetGrid() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<FleetProject[] | null>(null);
  const [error, setError] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    apiFetch("/api/fleet/projects").then(async (r) => {
      if (r.ok) setProjects((await r.json()) as FleetProject[]);
      else setError(true);
    });
  }, []);

  const sorted = useMemo(() => {
    if (!projects) return [];
    const copy = [...projects];
    copy.sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
    return copy;
  }, [projects, sortKey, sortAsc]);

  function onSort(key: SortKey) {
    if (key === sortKey) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  if (error) return <p className="text-sm text-red-600">{t("fleet.grid.error")}</p>;
  if (!projects) return <p>{t("fleet.grid.loading")}</p>;
  if (projects.length === 0) return <p>{t("fleet.grid.empty")}</p>;

  const columns: { key: SortKey; label: string }[] = [
    { key: "name", label: t("fleet.grid.columns.name") },
    { key: "tier", label: t("fleet.grid.columns.tier") },
    { key: "domain", label: t("fleet.grid.columns.domain") },
    { key: "status", label: t("fleet.grid.columns.status") },
    { key: "publish_status", label: t("fleet.grid.columns.publishStatus") },
  ];

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">{t("fleet.grid.title")}</h1>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b">
            {columns.map((col) => (
              <th key={col.key} className="p-2">
                <button
                  onClick={() => onSort(col.key)}
                  className="font-medium"
                  aria-sort={
                    sortKey === col.key
                      ? sortAsc
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  {col.label}
                  {sortKey === col.key ? (sortAsc ? " ▲" : " ▼") : ""}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={p.id} className="border-b">
              <td className="p-2">{p.name}</td>
              <td className="p-2 uppercase">{p.tier}</td>
              <td className="p-2">{p.domain ?? "—"}</td>
              <td className="p-2">{p.status}</td>
              <td className="p-2">{p.publish_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
