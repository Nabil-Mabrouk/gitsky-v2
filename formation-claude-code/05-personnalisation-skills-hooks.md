# Module 5 — Personnalisation : skills et hooks (2 h)

## Objectifs

- Créer des commandes personnalisées (skills / slash commands) pour les tâches récurrentes
- Adopter la discipline **manuel → skill → agent** pour éviter la sur-automatisation
- Comprendre et écrire des hooks pour automatiser et garde-fous
- Savoir quand utiliser skill vs hook vs CLAUDE.md
- Découvrir les plugins pour packager et partager ces extensions

## 1. Skills : encapsuler un savoir-faire répétable

Une **skill** est un dossier contenant un `SKILL.md` (instructions + métadonnées)
et d'éventuelles ressources (scripts, templates). Elle s'invoque par slash
command (`/ma-skill`) ou est déclenchée automatiquement quand la description
correspond à la demande.

Emplacements :

- `.claude/skills/<nom>/SKILL.md` — projet (versionné, partagé avec l'équipe)
- `~/.claude/skills/<nom>/SKILL.md` — personnel (tous projets)

### Anatomie d'une skill

```markdown
---
name: changelog
description: Génère l'entrée de changelog pour la release en cours,
  à partir des commits depuis le dernier tag.
---

# Générer le changelog

1. Lister les commits : `git log $(git describe --tags --abbrev=0)..HEAD --oneline`
2. Grouper par type (feat/fix/chore) selon Conventional Commits.
3. Rédiger l'entrée dans CHANGELOG.md, section [Unreleased],
   au format du fichier existant.
4. Ne pas committer : présenter le diff pour validation.
```

- Le `description` sert au déclenchement automatique : le rédiger comme un
  critère de déclenchement (« Use when... »), pas comme un titre
- `$ARGUMENTS` (ou `$1`, `$2`) injecte les arguments passés à la commande
- Une skill peut embarquer des scripts que l'agent exécutera — la logique
  déterministe en script, le jugement en instructions
- La skill `skill-creator` (plugin Anthropic) guide la création et le test

### Quels candidats à la « skillification » ?

Toute procédure que vous expliquez plus de deux fois : générer un changelog,
préparer une release, créer un composant selon le gabarit maison, rédiger un
rapport d'incident, onboarder un nouveau endpoint API…

**Règle : CLAUDE.md pour ce qui est toujours vrai (conventions), skill pour
ce qui est procédural et déclenché à la demande.**

## 2. Le réflexe pro : manuel → skill → agent

Dès qu'on découvre les skills, la tentation est de tout vouloir automatiser
immédiatement. C'est le meilleur moyen de produire des skills fragiles, qui
cassent au premier cas non prévu et qu'on finit par contourner « pour aller
plus vite ». La discipline professionnelle est inverse et se déroule en trois
temps :

1. **Faire manuellement**, au moins deux ou trois fois. On mesure ce qui est
   stable, ce qui varie, où le jugement est nécessaire, où la procédure casse.
2. **Skillifier ce qui s'est stabilisé.** Une skill = la partie de la procédure
   qui ne change plus. Ce qui relève encore du jugement reste dans le prompt
   qui l'invoque.
3. **Chaîner en agent** (sous-agents, module 7) seulement quand chaque skill
   est fiable en isolement. Un agent qui compose des skills fragiles cumule
   les échecs sans qu'on puisse diagnostiquer laquelle est en cause.

### Pourquoi cet ordre est non négociable

Un agent qui enchaîne trois skills mal calibrées échoue 40 % du temps sans
qu'on sache où le pipeline s'est brisé. Trois skills validées séparément,
puis orchestrées, échouent proprement à une étape identifiable — et on
corrige à la racine.

L'autre bénéfice : en faisant la procédure à la main, on découvre souvent que
la moitié de ce qu'on voulait skillifier était en réalité du jugement humain
mal reconnu comme tel. Skillifier trop tôt fige ce jugement dans une règle
arbitraire.

### Exemple filé : compresser « idée → produit déployé »

Un opérateur solo veut valider et déployer plusieurs projets web en parallèle
(landing pages de test, MVP, déploiement). La bonne progression :

| Étape | Ce qu'on fait | Ce qui devient une skill |
|---|---|---|
| Semaine 1 | Prendre une idée. Chercher les signaux de douleur (Reddit, avis G2), rédiger une landing, la déployer sur Vercel, mesurer les inscriptions. **Tout à la main.** | Rien encore |
| Semaine 2–3 | Répéter sur trois autres idées. Noter ce qui est identique à chaque fois : le prompt de scoring, le gabarit de landing, la commande de déploiement. | On isole `score-idea`, `generate-landing`, `deploy-vercel` |
| Semaine 4 | Chaque skill tourne seule, on la corrige jusqu'à ce qu'elle réussisse cinq exécutions consécutives sans intervention. | Skills stables |
| Semaine 5+ | Un sous-agent d'orchestration enchaîne les skills, avec un point de décision humain entre validation de la landing et build du MVP. | Chaînage validé, avec stage gates |

À aucun moment on ne saute directement à « un agent qui prend une idée et
livre une webapp ». Le raccourci coûte plus cher en corrections qu'il ne
fait gagner au démarrage.

- ❌ « J'écris une skill `startup-machine` qui prend une idée et livre une
  webapp complète. » (Trop ambitieux, non testable, échouera en silence.)
- ✅ « J'ai fait tourner la boucle idée → landing trois fois à la main.
  J'écris `score-idea` qui encode ma checklist de scoring, je la teste sur
  dix idées, puis je passe à `generate-landing`. »

### Anti-patterns fréquents

- **Skillifier trop tôt** : la procédure n'est pas stabilisée, la skill fige
  une convention arbitraire et bloquera les cas suivants.
- **Skill trop large** : `deploy-app` qui gère quatre stacks et trois
  environnements → décomposer en skills par stack, orchestrées ensuite.
- **Agent qui masque l'échec** : un orchestrateur qui rattrape silencieusement
  les erreurs des skills empêche de les corriger. Faire échouer bruyamment.
- **Sauter la mesure** : sans avoir compté combien de fois la procédure a été
  exécutée et où elle a cassé, la skillification est du cargo cult.

**Règle : on ne crée une skill que pour une procédure exécutée manuellement
au moins deux fois. On ne crée un agent que pour orchestrer des skills déjà
validées en isolement.**

## 3. Hooks : l'automatisation garantie

Un **hook** est une commande shell exécutée automatiquement par le harnais à
un moment précis du cycle de vie. Contrairement à une instruction dans
`CLAUDE.md` (que le modèle peut oublier), un hook s'exécute **toujours** :
c'est du déterminisme.

### Événements principaux

| Événement | Moment | Usage type |
|---|---|---|
| `PreToolUse` | Avant un appel d'outil (peut bloquer) | Interdire un pattern de commande, valider un chemin |
| `PostToolUse` | Après un appel d'outil | Formatter le fichier après chaque Edit |
| `UserPromptSubmit` | À l'envoi d'un prompt | Injecter du contexte, valider la demande |
| `Stop` | Quand l'agent finit son tour | Notification, vérification finale |
| `SessionStart` | Au démarrage | Charger un état, préparer l'environnement |

### Exemple : format automatique après chaque édition

```json
// .claude/settings.json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          { "type": "command",
            "command": "npx prettier --write \"$CLAUDE_FILE_PATHS\"" }
        ]
      }
    ]
  }
}
```

### Exemple : bloquer les commits sur main (garde-fou)

Un hook `PreToolUse` sur `Bash` peut inspecter la commande (reçue en JSON sur
stdin) et renvoyer un code de sortie 2 pour bloquer avec un message que
l'agent lira — il s'adaptera (ex. « crée une branche d'abord »).

Points d'attention :

- Les hooks s'exécutent avec **vos droits**, sans confirmation : les traiter
  comme du code de prod (revue obligatoire s'ils sont versionnés)
- Un hook lent ralentit chaque action : rester léger
- Débogage : `claude --debug` montre les exécutions de hooks

### Skill vs hook vs CLAUDE.md — arbre de décision

- Doit se produire **à coup sûr**, à chaque fois → **hook**
- Procédure riche déclenchée **à la demande** ou sur un type de tâche → **skill**
- Convention permanente qui teinte tout le travail → **CLAUDE.md**

## 4. Plugins : packager et distribuer

Un plugin regroupe skills, hooks, agents et serveurs MCP en un paquet
installable (`/plugin`). Intérêt en entreprise : distribuer un standard
d'équipe (« notre plugin qualité : skills de release + hooks de lint +
agent de revue ») via un marketplace interne.

## 5. TP guidé (50 min)

1. Créer une skill projet `/new-endpoint` qui scaffolde un endpoint selon le
   gabarit du dépôt d'exercice (route + test + doc). **Avant de coder la
   skill, faire tourner la procédure une fois à la main** pour identifier ce
   qui est stable (à mettre dans la skill) vs ce qui varie (à laisser au
   prompt appelant). La tester, l'ajuster.
2. Ajouter un hook `PostToolUse` qui lance le formatter sur chaque fichier
   modifié ; vérifier son déclenchement.
3. Ajouter un hook `PreToolUse` qui bloque `git push --force` avec un message
   explicatif ; tester en demandant à l'agent de force-pusher.
4. Discussion : chaque participant identifie deux procédures de son équipe
   candidates à la skillification. Pour chacune, préciser combien de fois
   elle a déjà été exécutée manuellement et quelles étapes sont assez stables
   pour être skillifiées dès maintenant.

## Checklist de validation

- [ ] Je sais créer, tester et versionner une skill projet
- [ ] Je sais rédiger une description de skill qui déclenche au bon moment
- [ ] Je fais tourner une procédure à la main au moins deux fois avant de la skillifier
- [ ] Je ne chaîne des skills dans un agent qu'après les avoir validées en isolement
- [ ] Je sais écrire un hook PostToolUse (automatisation) et PreToolUse (garde-fou)
- [ ] Je sais choisir entre hook, skill et CLAUDE.md pour un besoin donné
- [ ] Je mesure le risque des hooks (exécution sans confirmation) et je les revois comme du code
