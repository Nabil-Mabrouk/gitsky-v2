# MezouedAI — exemple de démonstration GitSky

**MezouedAI** génère des chansons de *mezoued* (musique populaire tunisienne) :
l'utilisateur choisit un chanteur, un thème, un rythme, des instruments, construit
la structure de la chanson (drag-and-drop), puis **Concept** écrit les paroles et
**Generate** produit la chanson complète via un pipeline d'agents appelant l'API Suno.

Ce dossier montre le **même produit généré à trois tiers** — la trajectoire
GitSky *idée → landing → app → produit agentique complet* :

| Tier | Config | Ce qui est démontré |
|------|--------|---------------------|
| **T0** | `config.t0.yaml` | Landing de validation (blocs, SEO, capture d'emails) |
| **T1** | `config.t1.yaml` + overlay | App avec comptes + modèles métier scaffoldés + interface de composition (drag-and-drop) |
| **T2** | `config.t2.yaml` + overlay | Génération agentique de bout en bout : pipeline d'agents + Suno + crédits |

À partir de T1, une partie du code est **bespoke** (routeur métier, pages front)
et ne peut pas s'exprimer en config générateur : elle vit dans `overlay/` et se
copie par-dessus l'arbre généré via `apply-overlay.sh`.

Les briques **réutilisables** que ce produit a forcées (moteur d'agents, tool
d'API externe, job async) vivent dans le générateur (`src/generator/template/`),
pas ici — c'est la logique factory : on paie une fois, on revend à l'infini.

## Générer un tier

Depuis la racine du dépôt, dans l'environnement Python du projet :

```bash
python -c "
import yaml
from copier import run_copy
data = yaml.safe_load(open('examples/mezouedai/config.t0.yaml'))
run_copy('src/generator', 'out/mezouedai-t0', data=data, defaults=True, unsafe=True)
"
```

(Remplacer `t0` par `t1` / `t2` pour les autres tiers.)

### À partir de T1 : appliquer l'overlay bespoke

```bash
./examples/mezouedai/apply-overlay.sh out/mezouedai-t1
```

## Lancer

### Backend + API (tous tiers)

```bash
cd out/mezouedai-t0
docker compose -f docker-compose.dev.yml up --build
```

- API : http://localhost:8000 — santé http://localhost:8000/health
- `sitemap.xml` / `robots.txt` : http://localhost:8000/sitemap.xml

### La landing T0 (statique)

En T0, le livrable est la **landing** (`vitrine/landing.html`). En production elle
est auto-publiée par le GitSky Studio sur un sous-domaine jetable (Chap 24) ; en
local il suffit de la servir en statique :

```bash
cd out/mezouedai-t0/vitrine
python -m http.server 4173      # http://localhost:4173/landing.html
```

> La capture d'email poste vers `/leads` (le collecteur partagé en prod) — sans
> effet en local, c'est normal.

## T2 : générer une chanson

À T2, le compositeur active deux boutons (le stub Suno rend une URL audio
d'exemple, donc aucun secret requis) :

- **Concept** → workflow synchrone `analyze + lyrics` : un aperçu des paroles.
- **Generate** → workflow long `analyze + lyrics + style + suno`, lancé comme
  **job asynchrone** (l'API rend la main tout de suite), suivi par polling
  jusqu'à obtenir l'URL audio. Débite des crédits (10 au départ, 3 par chanson).

Le moteur d'orchestration, le tool Suno et le portefeuille de crédits sont
**réutilisables** (`src/generator/template/app/modules/agentic/`) ; MezouedAI ne
fournit que la déclaration du workflow (`overlay/app/modules/agentic/agent_services.yaml`)
et le câblage UI.
