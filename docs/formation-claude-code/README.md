# Formation — Maîtriser Claude Code en environnement professionnel

> Formation complète pour développeurs et équipes techniques souhaitant utiliser
> Claude Code de manière professionnelle, sécurisée et productive.

## Public visé

- Développeurs (tous niveaux) souhaitant intégrer un agent de code dans leur quotidien
- Tech leads / architectes voulant encadrer l'usage en équipe
- DevOps souhaitant automatiser des tâches avec des agents

## Prérequis

- Pratique courante de la ligne de commande et de Git
- Un compte Anthropic (Claude Pro/Max ou clé API) et Claude Code installé
- Un dépôt de code d'exercice (fourni ou projet personnel non critique)

## Objectifs pédagogiques

À l'issue de la formation, le participant sait :

1. Piloter Claude Code efficacement (prompting, modes, raccourcis, gestion du contexte)
2. Configurer un projet pour l'agent : `CLAUDE.md`, settings, permissions
3. Sécuriser l'usage : modes de permission, allowlists, revue des actions
4. Mettre en place des workflows pro : plan mode, TDD, commits/PR, revue de code
5. Étendre l'outil : skills (commandes personnalisées), hooks, sous-agents, MCP
6. Automatiser : mode headless, CI/CD, tâches planifiées, Agent SDK
7. Déployer et gouverner l'outil à l'échelle d'une équipe

## Organisation

| Module | Titre | Durée |
|---|---|---|
| 1 | [Fondamentaux et prise en main](01-fondamentaux.md) | 2 h |
| 2 | [Contexte, mémoire et CLAUDE.md](02-contexte-et-memoire.md) | 2 h |
| 3 | [Permissions, sécurité et configuration](03-permissions-et-securite.md) | 2 h |
| 4 | [Workflows de développement professionnels](04-workflows-developpement.md) | 3 h |
| 5 | [Personnalisation : skills et hooks](05-personnalisation-skills-hooks.md) | 2 h |
| 6 | [MCP et intégrations externes](06-mcp-et-integrations.md) | 1,5 h |
| 7 | [Sous-agents et parallélisation](07-sous-agents.md) | 1,5 h |
| 8 | [Automatisation avancée : headless, CI/CD, SDK](08-automatisation-avancee.md) | 2 h |
| 9 | [Adoption en équipe et gouvernance](09-adoption-equipe.md) | 1 h |
| — | [Évaluation et projet final](10-evaluation-projet-final.md) | 3 h |

**Durée totale : ~20 h** (3 jours en présentiel, ou 5 demi-journées à distance).

Chaque module suit la même structure : objectifs → apports théoriques →
démonstration → **TP guidé** → checklist de validation des acquis.

## Modalités pédagogiques

- 30 % d'exposé / démonstration, 70 % de pratique sur machine
- Un dépôt d'exercice par participant (projet web simple avec tests)
- Évaluation : quiz par module + projet final noté (module 10)

## Matériel formateur

- Un poste par participant avec Claude Code installé et authentifié
- Un dépôt Git d'exercice contenant : un petit projet avec tests, quelques bugs
  volontaires, et un backlog d'améliorations
- Accès GitHub (ou GitLab) pour les modules 4 et 8
