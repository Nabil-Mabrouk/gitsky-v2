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
const SERVICE = "/api/agent-services";
const EXEC = `${SERVICE}/services/mezoued-song/execute`;
const CREDITS = `${SERVICE}/credits`;

export default function Composer() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [title, setTitle] = useState("Ma chanson");
  const [singer, setSinger] = useState("");
  const [theme, setTheme] = useState("");
  const [rhythm, setRhythm] = useState("");
  const [instruments, setInstruments] = useState<string[]>([]);
  const [structure, setStructure] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  // Génération (T2) : détectée à la volée — indisponible en T1 (pas de module).
  const [genAvailable, setGenAvailable] = useState(false);
  const [credits, setCredits] = useState<number | null>(null);
  const [concept, setConcept] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const dragIndex = useRef<number | null>(null);

  useEffect(() => {
    apiFetch(`${"/api/songs"}/catalog`)
      .then((r) => r.json())
      .then(setCatalog)
      .catch(() => setMessage("Catalogue indisponible"));
    // Détection de la génération agentique (présente uniquement en T2).
    apiFetch(CREDITS)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setGenAvailable(true);
          setCredits(d.balance);
        }
      })
      .catch(() => {});
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

  const voiceOf = (name: string) =>
    catalog?.singers.find((s) => s.name === name)?.voice ?? "";

  const params = () => ({
    title,
    singer,
    voice: voiceOf(singer),
    theme,
    rhythm,
    instruments,
    structure,
  });

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

  // Concept : workflow synchrone (analyze + lyrics) — aperçu des paroles.
  const runConcept = async () => {
    setBusy(true);
    setConcept("");
    setMessage("");
    const res = await apiFetch(EXEC, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_name: "concept", parameters: params() }),
    });
    if (res.ok) {
      const ex = await res.json();
      setConcept(ex.result?.output ?? "");
    } else if (res.status === 401) {
      setMessage("Connecte-toi pour générer.");
    } else {
      setMessage("Échec du concept.");
    }
    setBusy(false);
  };

  // Generate : workflow long asynchrone (submit-and-return) — on poll le job
  // jusqu'à obtenir l'URL audio.
  const runGenerate = async () => {
    setBusy(true);
    setAudioUrl("");
    setMessage("");
    const res = await apiFetch(EXEC, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workflow_name: "song", parameters: params() }),
    });
    if (res.status === 402) {
      setMessage("Crédits insuffisants.");
      setBusy(false);
      return;
    }
    if (!res.ok) {
      setMessage("Échec du lancement.");
      setBusy(false);
      return;
    }
    const job = await res.json();
    for (let i = 0; i < 60; i++) {
      const r = await apiFetch(`${SERVICE}/executions/${job.id}`);
      const ex = await r.json();
      if (ex.status === "completed") {
        setAudioUrl(ex.result?.suno?.audio_url ?? "");
        break;
      }
      if (ex.status === "failed") {
        setMessage("La génération a échoué.");
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 800));
    }
    const cr = await apiFetch(CREDITS);
    if (cr.ok) setCredits((await cr.json()).balance);
    setBusy(false);
  };

  if (!catalog) return <p>Chargement du catalogue…</p>;

  return (
    <div className="grid gap-8" style={{ maxWidth: 720 }}>
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Compose ta chanson</h1>
        {genAvailable && credits !== null && (
          <span className="text-sm border rounded px-2 py-1" data-testid="credits">
            {credits} crédits
          </span>
        )}
      </div>

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

      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={save} className="border rounded px-4 py-2 font-medium">
          Sauvegarder
        </button>
        <button
          onClick={runConcept}
          disabled={!genAvailable || busy}
          title={genAvailable ? "" : "Disponible en T2"}
          className="border rounded px-4 py-2"
        >
          Concept
        </button>
        <button
          onClick={runGenerate}
          disabled={!genAvailable || busy}
          title={genAvailable ? "" : "Disponible en T2"}
          className="border rounded px-4 py-2"
        >
          Generate
        </button>
        {message && <span role="status">{message}</span>}
      </div>

      {concept && (
        <section className="grid gap-2">
          <h2 className="font-medium">Paroles (aperçu)</h2>
          <pre className="border rounded p-3 whitespace-pre-wrap">{concept}</pre>
        </section>
      )}

      {audioUrl && (
        <section className="grid gap-2">
          <h2 className="font-medium">Ta chanson</h2>
          <audio controls src={audioUrl} data-testid="audio-player" />
        </section>
      )}
    </div>
  );
}
