# Module 10 — Évaluation et projet final (3 h)

## Format

- **Quiz de synthèse** (30 min, 20 questions) — 30 % de la note
- **Projet final pratique** (2 h 30, en autonomie) — 70 % de la note

## Projet final : « Reprendre un projet en main avec Claude Code »

Le participant reçoit un dépôt inconnu (petit projet web avec dette technique,
2 bugs ouverts, 1 feature demandée, aucune configuration Claude Code) et doit,
en 2 h 30, livrer :

### Livrables et barème

| # | Livrable | Points | Critères |
|---|---|---|---|
| 1 | Socle projet : `CLAUDE.md` + `.claude/settings.json` | /20 | Concis, exact ; allowlist pertinente ; deny secrets |
| 2 | Correction du bug n° 1 (avec test de non-régression) | /15 | Cause racine identifiée ; test ; suite verte |
| 3 | Feature en TDD (branche + PR) | /25 | Tests d'abord ; tests non modifiés ensuite ; PR propre |
| 4 | Passage de `/code-review` + traitement des remarques | /10 | Remarques triées et traitées ou justifiées |
| 5 | Une skill projet réutilisable | /15 | Description déclenchante ; procédure testée |
| 6 | Un hook de qualité (format ou garde-fou) | /10 | Fonctionne ; choix hook vs skill justifié |
| 7 | Journal de bord (15 lignes max) | /5 | Décisions clés : plan mode, rewind, délégations |

**Seuil de réussite : 70/100.** Le journal de bord sert à évaluer la
*démarche* (a-t-il planifié ? critiqué ? vérifié ?) au-delà du résultat.

### Règles

- Tout doit être fait **avec** Claude Code (c'est l'objet de l'évaluation)
- Le formateur observe : un participant qui accepte tout sans lire les diffs
  perd des points même si « ça marche »
- Bug n° 2 en bonus (+10) pour les rapides

## Quiz de synthèse — extrait (10 des 20 questions)

1. Quelle est la différence entre `/clear` et `/compact`, et quand utiliser
   chacun ?
2. Citez trois choses à mettre dans un `CLAUDE.md` et deux à ne pas y mettre.
3. Quelle règle l'emporte entre `allow` et `deny` ? Où placer une règle
   d'équipe vs personnelle ?
4. Pourquoi `bypassPermissions` est-il réservé aux environnements isolés ?
   Quelles sont les trois conditions à ne jamais cumuler ?
5. Décrivez le cycle EPIV et le rôle du plan mode.
6. En TDD avec agent, quelle contrainte explicite faut-il poser en phase
   d'implémentation, et pourquoi ?
7. Hook vs skill vs CLAUDE.md : donnez un exemple d'usage correct de chacun.
8. Qu'est-ce qu'un sous-agent apporte du point de vue du contexte ?
9. Citez trois précautions indispensables pour `claude -p` en CI.
10. Un collègue dit « c'est Claude qui a introduit le bug ». Que répond la
    charte d'équipe ?

## Grille d'auto-évaluation post-formation (à 30 jours)

À remplir un mois après, en conditions réelles :

- [ ] Mon/mes projets ont un `CLAUDE.md` maintenu et des settings versionnés
- [ ] J'utilise le plan mode sur les tâches structurantes
- [ ] J'ai créé au moins une skill et un hook utilisés en vrai
- [ ] Mes PR assistées passent la revue sans reprise majeure
- [ ] J'ai un réflexe d'interruption/rewind au lieu de négocier avec l'agent
- [ ] Mon équipe a une charte et un rituel d'amélioration du socle

## Ressources pour aller plus loin

- Documentation officielle : https://docs.anthropic.com/en/docs/claude-code
- Best practices agentic coding (Anthropic Engineering) :
  https://www.anthropic.com/engineering/claude-code-best-practices
- Agent SDK : https://docs.anthropic.com/en/api/agent-sdk/overview
- MCP : https://modelcontextprotocol.io
