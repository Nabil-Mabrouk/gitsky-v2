# Module 2 — Contexte, mémoire et CLAUDE.md (2 h)

## Objectifs

- Comprendre la fenêtre de contexte et son impact sur la qualité des réponses
- Rédiger un `CLAUDE.md` efficace pour un projet
- Utiliser la hiérarchie des fichiers de mémoire (projet, utilisateur, répertoires)
- Gérer le contexte en session longue : `/compact`, `/clear`, checkpoints

## 1. La fenêtre de contexte : la ressource rare

Tout ce que l'agent « sait » pendant une session tient dans sa fenêtre de
contexte : instructions système, `CLAUDE.md`, historique de conversation,
contenus de fichiers lus, sorties de commandes. Quand elle se remplit :

- la qualité se dégrade (l'agent « oublie » des consignes du début),
- le coût augmente (tokens relus à chaque tour),
- Claude Code finit par **compacter automatiquement** (résumé de l'historique).

**Conséquences pratiques :**

- Ne pas faire lire des fichiers énormes « pour info » ; cibler.
- Une tâche indépendante = `/clear` ou nouvelle session.
- `/compact` avant d'enchaîner sur une longue suite de travaux liés
  (on peut guider : `/compact garde les décisions d'architecture`).
- `/context` (ou `/status`) pour visualiser ce qui occupe le contexte.

## 2. CLAUDE.md : le fichier de bord du projet

`CLAUDE.md` (à la racine du dépôt, versionné) est chargé automatiquement au
démarrage de chaque session. C'est le document le plus rentable à soigner :
il évite de répéter les mêmes consignes à chaque session, pour tous les
membres de l'équipe.

### Générer une base : `/init`

La commande `/init` analyse le dépôt et génère un premier `CLAUDE.md`.
C'est un point de départ, **pas** un livrable : il faut l'éditer.

### Que mettre dedans (et ne pas mettre)

✅ À mettre :

- Commandes exactes du projet : build, test, lint, lancement local
- Conventions non déductibles du code : style de commit, langue, patterns imposés
- Pièges connus : « ne jamais éditer les fichiers de `generated/` »,
  « les tests d'intégration nécessitent Docker »
- Architecture en 5 lignes : où sont les entrées, la logique métier, les tests

❌ À éviter :

- Tout ce que l'agent peut découvrir seul en lisant le code
- Des pavés de documentation générale (ça consomme du contexte à chaque session)
- Des consignes contradictoires ou obsolètes — un CLAUDE.md faux est pire
  qu'un CLAUDE.md absent

**Règle d'or : court, exact, actionnable.** Viser < 60 lignes. Chaque ligne
doit changer un comportement de l'agent.

### Exemple type

```markdown
# Projet Facturation

## Commandes
- Tests : `pnpm test` (unitaires) ; `pnpm test:e2e` nécessite Docker
- Lint : `pnpm lint --fix` — toujours lancer avant de conclure
- Dev : `pnpm dev` (port 3000)

## Conventions
- TypeScript strict ; pas de `any`
- Messages de commit en anglais, format Conventional Commits
- Les montants sont TOUJOURS en centimes (integer), jamais en float

## Pièges
- `src/generated/` est généré par Prisma : ne jamais l'éditer à la main
- L'API legacy dans `src/v1/` est gelée : correctifs de sécurité uniquement
```

### Hiérarchie et imports

| Fichier | Portée | Versionné ? |
|---|---|---|
| `CLAUDE.md` (racine du projet) | Toute l'équipe | Oui |
| `CLAUDE.local.md` / règles perso | Vous, sur ce projet | Non (gitignore) |
| `~/.claude/CLAUDE.md` | Vous, tous projets | Non |
| `CLAUDE.md` dans un sous-répertoire | Chargé quand on travaille dedans | Oui |

- Syntaxe d'import : `@chemin/vers/fichier.md` inclut un autre fichier
  (ex. un `AGENTS.md` partagé entre plusieurs outils).
- Astuce quotidienne : commencer un message par `#` propose de mémoriser
  la consigne dans le bon fichier de mémoire. La commande `/memory` ouvre
  ces fichiers pour édition.

### Maintenance en continu

Quand l'agent commet deux fois la même erreur → c'est un signal qu'une ligne
manque dans `CLAUDE.md`. Le fichier se construit par itérations, comme un
runbook. En revue de code, traiter les modifications de `CLAUDE.md` comme du
code : relire, challenger, supprimer l'obsolète.

## 3. TP guidé (50 min)

1. Lancer `/init` sur le dépôt d'exercice ; comparer le résultat avec le
   projet réel ; corriger et réduire le fichier à l'essentiel.
2. Introduire volontairement une convention (« tous les nouveaux tests en
   AAA : Arrange/Act/Assert ») dans `CLAUDE.md`, ouvrir une nouvelle session,
   demander un test et vérifier que la convention est respectée.
3. En cours de session, utiliser `#` pour mémoriser une consigne, puis
   `/memory` pour vérifier où elle a été enregistrée.
4. Remplir le contexte (faire lire plusieurs gros fichiers), observer
   l'indicateur, puis `/compact` avec une instruction de conservation ciblée.
5. Bonus : créer un `~/.claude/CLAUDE.md` personnel avec vos préférences
   (langue des réponses, style de commit).

## Checklist de validation

- [ ] Je sais expliquer pourquoi un contexte saturé dégrade les résultats
- [ ] Je sais rédiger un `CLAUDE.md` court, exact et actionnable
- [ ] Je connais la hiérarchie projet / local / utilisateur et les imports `@`
- [ ] Je sais utiliser `#`, `/memory`, `/compact`, `/clear` à bon escient
- [ ] Je traite `CLAUDE.md` comme un livrable maintenu par l'équipe
