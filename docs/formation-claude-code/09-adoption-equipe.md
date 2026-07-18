# Module 9 — Adoption en équipe et gouvernance (1 h)

## Objectifs

- Standardiser la configuration Claude Code à l'échelle d'une équipe
- Définir une politique d'usage : sécurité, revue, responsabilité
- Suivre les coûts et mesurer la valeur
- Réussir la conduite du changement

## 1. Le socle technique partagé

À versionner dans chaque dépôt (revu comme du code) :

| Artefact | Contenu |
|---|---|
| `CLAUDE.md` | Commandes, conventions, pièges du projet |
| `.claude/settings.json` | Allowlist/denylist, hooks qualité |
| `.claude/skills/` | Procédures de l'équipe (release, scaffolding…) |
| `.claude/agents/` | Rôles partagés (relecteur sécurité, etc.) |
| `.mcp.json` | Intégrations standards (tickets, docs, DB lecture seule) |

Au niveau organisation :

- **Managed settings** (déployés par l'IT) : les interdits non négociables —
  deny secrets, deny endpoints de prod, politique réseau
- **Plugin d'équipe** via marketplace interne : distribuer skills/hooks/agents
  d'un coup, versionnés
- Choix de plateforme : API Anthropic directe, Bedrock ou Vertex selon les
  exigences de conformité (résidence des données, rétention zéro)

## 2. La politique d'usage (charte)

Points que toute charte d'équipe doit trancher :

1. **Responsabilité** : le code généré par l'agent est du code **dont son
   auteur humain répond**. « C'est Claude qui l'a écrit » n'existe pas en
   revue ni en post-mortem.
2. **Revue** : toute PR assistée suit le même circuit de revue ; le
   `/code-review` agent est un pré-filtre, jamais un substitut.
3. **Modes autorisés** : où `acceptEdits` est acceptable, où
   `bypassPermissions` est interdit (partout hors sandbox, typiquement).
4. **Données** : ce qui peut ou non entrer dans le contexte (secrets, données
   clients, code sous NDA tiers).
5. **Traçabilité** : mention de l'assistance dans les commits/PR si l'équipe
   ou la conformité l'exige (ex. trailer `Co-Authored-By`).

## 3. Coûts et mesure

- `/status` et la sortie JSON du headless donnent le coût par session ;
  en entreprise : Claude Code Analytics / la console pour l'agrégé
- Leviers de maîtrise des coûts, dans l'ordre d'impact :
  1. hygiène de contexte (module 2) — le gaspillage n° 1,
  2. choix du modèle par tâche (`/model`) : modèle rapide pour le simple,
  3. sous-agents pour les explorations volumineuses,
  4. skills qui évitent les re-explications
- Mesurer la valeur autrement qu'au feeling : temps de cycle des PR, taux de
  PR assistées mergées sans reprise, couverture de tests, tickets traités

## 4. Conduite du changement

Ce qui marche (retours d'expérience) :

- **Champions** : 2-3 early adopters qui construisent le socle (CLAUDE.md,
  skills) avant la généralisation
- **Pairing sessions** : 1 h à deux sur une vraie tâche vaut mieux qu'un
  slide deck
- **Bibliothèque de prompts/skills interne** : capitaliser les réussites
- **Rituel d'amélioration** : en rétro, un point « qu'est-ce que l'agent a
  raté cette itération et que met-on dans CLAUDE.md/skills/hooks ? »

Ce qui échoue : imposer l'outil sans socle projet (CLAUDE.md vide →
résultats médiocres → rejet), ou l'inverse, laisser chacun bricoler sans
partage (configurations divergentes, pas d'effet d'équipe).

## 5. Atelier (30 min)

En groupes : rédiger la charte d'usage (10 points max) et la structure du
socle partagé pour une équipe fictive (contexte fourni par le formateur :
fintech, 8 devs, code sensible). Restitution croisée.

## Checklist de validation

- [ ] Je sais quels artefacts versionner pour standardiser l'usage en équipe
- [ ] Je sais rédiger une charte couvrant responsabilité, revue, modes, données
- [ ] Je connais les leviers de maîtrise des coûts par ordre d'impact
- [ ] J'ai un plan d'adoption : champions → socle → généralisation → rituel d'amélioration
