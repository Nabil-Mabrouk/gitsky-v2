import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../api";

type Singer = { name: string; voice: string; avatar: string; tagline: string };
type Named = { name: string; description?: string };
type Instrument = { name: string; family: string };
type Catalog = {
  singers: Singer[];
  themes: Named[];
  rhythms: Named[];
  instruments: Instrument[];
};

const SECTIONS = ["intro", "couplet", "refrain", "pont", "outro"];

export default function Composer() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [title, setTitle] = useState("Ma chanson");
  const [singer, setSinger] = useState("");
  const [theme, setTheme] = useState("");
  const [rhythm, setRhythm] = useState("");
  const [instruments, setInstruments] = useState<string[]>([]);
  const [structure, setStructure] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const dragIndex = useRef<number | null>(null);

  useEffect(() => {
    apiFetch("/api/songs/catalog")
      .then((r) => r.json())
      .then(setCatalog)
      .catch(() => setMessage("Catalogue indisponible"));
  }, []);

  const toggleInstrument = (name: string) =>
    setInstruments((cur) =>
      cur.includes(name) ? cur.filter((i) => i !== name) : [...cur, name],
    );

  const addSection = (name: string) => setStructure((cur) => [...cur, name]);
  const removeSection = (idx: number) =>
    setStructure((cur) => cur.filter((_, i) => i !== idx));
  const moveSection = (idx: number, dir: -1 | 1) =>
    setStructure((cur) => {
      const next = [...cur];
      const j = idx + dir;
      if (j < 0 || j >= next.length) return cur;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });

  // Drag-and-drop natif (progressive enhancement ; les flèches ↑↓ restent la
  // voie accessible et testable).
  const onDrop = (target: number) => {
    const src = dragIndex.current;
    dragIndex.current = null;
    if (src === null || src === target) return;
    setStructure((cur) => {
      const next = [...cur];
      const [moved] = next.splice(src, 1);
      next.splice(target, 0, moved);
      return next;
    });
  };

  const save = async () => {
    setMessage("");
    const res = await apiFetch("/api/songs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, singer, theme, rhythm, instruments, structure }),
    });
    if (res.ok) {
      const song = await res.json();
      setMessage(`Chanson sauvegardée (#${song.id}).`);
    } else if (res.status === 401) {
      setMessage("Connecte-toi pour sauvegarder.");
    } else {
      setMessage("Échec de la sauvegarde.");
    }
  };

  if (!catalog) return <p>Chargement du catalogue…</p>;

  return (
    <div className="grid gap-8" style={{ maxWidth: 720 }}>
      <h1 className="text-2xl font-bold">Compose ta chanson</h1>

      <label className="grid gap-1">
        <span className="font-medium">Titre</span>
        <input
          aria-label="Titre"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="border rounded p-2"
        />
      </label>

      <section className="grid gap-2">
        <h2 className="font-medium">Chanteur</h2>
        <div className="flex gap-3 flex-wrap">
          {catalog.singers.map((s) => (
            <button
              key={s.name}
              onClick={() => setSinger(s.name)}
              aria-pressed={singer === s.name}
              className={`border rounded p-3 text-left ${singer === s.name ? "ring-2" : ""}`}
            >
              <div className="text-2xl">{s.avatar}</div>
              <div className="font-medium">{s.name}</div>
              <div className="text-sm">{s.tagline}</div>
            </button>
          ))}
        </div>
      </section>

      <label className="grid gap-1">
        <span className="font-medium">Thème</span>
        <select aria-label="Thème" value={theme} onChange={(e) => setTheme(e.target.value)} className="border rounded p-2">
          <option value="">—</option>
          {catalog.themes.map((t) => (
            <option key={t.name} value={t.name}>{t.name}</option>
          ))}
        </select>
      </label>

      <label className="grid gap-1">
        <span className="font-medium">Rythme</span>
        <select aria-label="Rythme" value={rhythm} onChange={(e) => setRhythm(e.target.value)} className="border rounded p-2">
          <option value="">—</option>
          {catalog.rhythms.map((r) => (
            <option key={r.name} value={r.name}>{r.name} ({r.bpm} bpm)</option>
          ))}
        </select>
      </label>

      <section className="grid gap-2">
        <h2 className="font-medium">Instruments</h2>
        <div className="flex gap-3 flex-wrap">
          {catalog.instruments.map((i) => (
            <label key={i.name} className="flex items-center gap-2 border rounded p-2">
              <input
                type="checkbox"
                checked={instruments.includes(i.name)}
                onChange={() => toggleInstrument(i.name)}
              />
              {i.name}
            </label>
          ))}
        </div>
      </section>

      <section className="grid gap-2">
        <h2 className="font-medium">Structure</h2>
        <div className="flex gap-2 flex-wrap">
          {SECTIONS.map((name) => (
            <button key={name} onClick={() => addSection(name)} className="border rounded px-3 py-1">
              + {name}
            </button>
          ))}
        </div>
        <ol className="grid gap-2">
          {structure.map((name, idx) => (
            <li
              key={idx}
              draggable
              onDragStart={() => (dragIndex.current = idx)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => onDrop(idx)}
              className="flex items-center gap-2 border rounded p-2"
              data-testid="section-item"
            >
              <span className="cursor-grab">⠿</span>
              <span className="flex-1">{idx + 1}. {name}</span>
              <button aria-label={`Monter ${name}`} onClick={() => moveSection(idx, -1)}>↑</button>
              <button aria-label={`Descendre ${name}`} onClick={() => moveSection(idx, 1)}>↓</button>
              <button aria-label={`Retirer ${name}`} onClick={() => removeSection(idx)}>✕</button>
            </li>
          ))}
        </ol>
      </section>

      <div className="flex items-center gap-3">
        <button onClick={save} className="border rounded px-4 py-2 font-medium">
          Sauvegarder
        </button>
        <button disabled title="Disponible en T2" className="border rounded px-4 py-2 opacity-50">
          Concept
        </button>
        <button disabled title="Disponible en T2" className="border rounded px-4 py-2 opacity-50">
          Generate
        </button>
        {message && <span role="status">{message}</span>}
      </div>
    </div>
  );
}
