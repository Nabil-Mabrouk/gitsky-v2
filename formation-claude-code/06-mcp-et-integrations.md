# Module 6 — MCP et intégrations externes (1,5 h)

## Objectifs

- Comprendre ce qu'apporte le Model Context Protocol (MCP)
- Installer, configurer et scoper des serveurs MCP
- Évaluer la sécurité d'un serveur MCP avant adoption
- Connaître les intégrations natives (GitHub, navigateur, IDE)

## 1. MCP en deux mots

Le **Model Context Protocol** est un standard ouvert qui permet de brancher
des outils externes sur l'agent : bases de données, trackers de tickets
(Jira, Linear), navigateur, Figma, Slack, APIs internes… Chaque serveur MCP
expose des **outils** (actions) et parfois des **ressources** (données) que
Claude Code peut appeler — avec le même système de permissions que les autres
outils.

Cas d'usage professionnels typiques :

- « Lis le ticket PROJ-1234 et implémente la correction » (Jira/Linear MCP)
- « Vérifie le schéma réel de la table `orders` » (Postgres MCP en lecture seule)
- « Teste le parcours d'inscription dans le navigateur » (Chrome/Playwright MCP)
- Accès à la doc à jour des frameworks (ex. Context7)

## 2. Installation et portées

```bash
# Ajout d'un serveur (transport stdio, http ou sse)
claude mcp add --transport http github https://api.githubcopilot.com/mcp/
claude mcp add postgres-ro -- npx -y @bytebase/dbhub --dsn "postgresql://readonly@..."

# Gestion
claude mcp list
/mcp          # en session : état, authentification OAuth, outils exposés
```

Trois portées, comme pour les settings :

| Portée | Fichier | Usage |
|---|---|---|
| `local` (défaut) | config personnelle du projet | Essais, accès personnels |
| `project` | `.mcp.json` versionné | Outils standards de l'équipe |
| `user` | config globale | Vos outils transverses |

Le fichier `.mcp.json` versionné est la manière propre de donner à toute
l'équipe les mêmes intégrations (chacun approuve à la première utilisation).

## 3. Sécurité et hygiène MCP

Un serveur MCP, c'est du code tiers qui voit vos données et agit pour vous.
Check-list avant adoption :

- **Provenance** : éditeur officiel ? code source auditable ? version épinglée ?
- **Moindre privilège** : credentials en lecture seule quand c'est possible
  (un MCP base de données en prod = lecture seule, sans exception)
- **Surface** : chaque outil exposé consomme du contexte et élargit la surface
  d'attaque — ne brancher que le nécessaire, désactiver le reste
- **Prompt injection** : les données ramenées par un MCP (tickets, pages web,
  résultats de recherche) sont du contenu non fiable — mêmes réflexes qu'au
  module 3
- Les permissions s'appliquent : on peut `allow`/`deny` des outils MCP
  individuellement (`mcp__serveur__outil`) dans les settings

## 4. Intégrations natives à connaître

- **GitHub** : via le CLI `gh` (déjà couvert) — souvent suffisant, sans MCP
- **IDE (VS Code / JetBrains)** : diffs dans l'éditeur, contexte du fichier
  ouvert, diagnostics partagés avec l'agent
- **Navigateur (Claude in Chrome / MCP Playwright)** : vérifier visuellement
  une UI, reproduire un bug front, tester un parcours
- **Bases de données, observabilité (Sentry…), design (Figma)** : selon la
  stack de l'équipe

## 5. TP guidé (35 min)

1. Ajouter un serveur MCP simple (ex. serveur de documentation ou GitHub MCP),
   vérifier avec `/mcp`, lister les outils exposés.
2. L'utiliser dans une tâche réelle : « récupère la doc de X et applique-la ».
3. Créer un `.mcp.json` de projet avec ce serveur, le versionner, et vérifier
   la demande d'approbation dans une nouvelle session.
4. Restreindre : ajouter une règle `deny` sur un outil du serveur et vérifier
   qu'elle s'applique.

## Checklist de validation

- [ ] Je sais expliquer ce qu'est MCP et citer trois cas d'usage pertinents pour mon équipe
- [ ] Je sais ajouter un serveur et choisir la bonne portée (local/project/user)
- [ ] J'applique la check-list sécurité avant d'adopter un serveur
- [ ] Je sais restreindre des outils MCP via les permissions
