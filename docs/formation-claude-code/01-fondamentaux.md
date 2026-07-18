# Module 1 — Fondamentaux et prise en main (2 h)

## Objectifs

- Comprendre ce qu'est Claude Code et ce qui le distingue d'un chat ou d'un autocomplete
- Installer, authentifier et lancer une première session productive
- Maîtriser les interactions de base : prompts, interruption, historique, raccourcis

## 1. Qu'est-ce que Claude Code ?

Claude Code est un **agent de code** : il ne se contente pas de suggérer du texte,
il **agit** dans votre environnement — il lit des fichiers, exécute des commandes,
modifie du code, lance des tests, crée des commits. Trois idées clés :

1. **Boucle agentique** : vous décrivez un objectif ; l'agent enchaîne lui-même
   lecture → modification → vérification jusqu'au résultat.
2. **Outils** : chaque action passe par un outil (Read, Edit, Bash, Grep…) que
   vous pouvez autoriser, refuser ou restreindre.
3. **Contexte** : l'agent ne « connaît » que ce qui est dans sa fenêtre de
   contexte. Toute la discipline professionnelle consiste à bien la gérer
   (module 2).

### Les surfaces disponibles

| Surface | Usage typique |
|---|---|
| CLI (`claude` dans le terminal) | Usage quotidien, serveurs, SSH |
| Application desktop (Mac/Windows) | Sessions multiples, confort visuel |
| Extensions IDE (VS Code, JetBrains) | Diffs inline, contexte de l'éditeur |
| Web (claude.ai/code) | Sessions cloud, machines distantes |
| Mode headless (`claude -p`) | Scripts et CI/CD (module 8) |

## 2. Installation et authentification

```bash
# Installation (npm) — ou installeur natif selon la plateforme
npm install -g @anthropic-ai/claude-code

# Premier lancement dans un projet
cd mon-projet
claude
```

Au premier lancement : authentification via compte Claude (abonnement Pro/Max)
ou clé API (facturation à l'usage). En entreprise : Amazon Bedrock ou Google
Vertex AI sont aussi supportés.

Commandes de diagnostic à connaître : `claude --version`, `/doctor` (vérifie
l'installation), `/status` (session en cours, modèle, coût).

## 3. Anatomie d'une session

Démonstration formateur sur le dépôt d'exercice :

```
> Explique-moi l'architecture de ce projet
> Où est gérée l'authentification des utilisateurs ?
> Corrige le bug : la page /profile renvoie une 500 quand l'utilisateur n'a pas d'avatar
```

Points à observer avec les participants :

- L'agent **explore d'abord** (Grep, Read) avant de modifier
- Chaque modification de fichier ou commande shell demande une **permission**
  (comportement par défaut — on le raffinera au module 3)
- L'agent **vérifie son travail** (relance les tests) si on le lui demande —
  et il faut le lui demander systématiquement

## 4. Interactions essentielles

### Écrire de bons prompts d'agent

Un bon prompt d'agent = **objectif + critère de réussite + contraintes**.

- ❌ « corrige le login »
- ✅ « Le test `test_login_expired_token` échoue depuis le commit abc123.
  Trouve la cause, corrige, et vérifie que toute la suite `tests/auth/` passe.
  Ne modifie pas l'API publique. »

Règles pratiques :

- Donner les **chemins de fichiers** quand on les connaît (`src/auth/session.py`)
- Coller les **messages d'erreur complets**, pas des paraphrases
- Préciser ce qu'il ne faut **pas** faire (périmètre)
- Pour une tâche floue : demander d'abord un **plan** (module 4)

### Commandes et raccourcis à connaître dès le jour 1

| Action | Commande / touche |
|---|---|
| Interrompre l'agent en cours d'action | `Échap` |
| Revenir en arrière dans la conversation (rewind) | `Échap` `Échap` |
| Vider le contexte (nouveau sujet) | `/clear` |
| Compacter le contexte (garder l'essentiel) | `/compact` |
| Aide et liste des commandes | `/help` |
| Changer de modèle | `/model` |
| Réflexion approfondie (extended thinking) | `Tab` (activer/désactiver) |
| Coller une image (capture d'écran, maquette) | Ctrl+V / glisser-déposer |
| Reprendre la session précédente | `claude --continue` / `claude --resume` |

**Réflexe professionnel n° 1 :** interrompre tôt. Si l'agent part dans la
mauvaise direction, `Échap` immédiatement et reformuler — ne pas le laisser
finir « pour voir ».

**Réflexe professionnel n° 2 :** un sujet = une session (ou `/clear`). Le
contexte pollué par une tâche précédente dégrade la qualité.

## 5. TP guidé (45 min)

Sur le dépôt d'exercice :

1. Lancer `claude`, demander une explication de l'architecture du projet.
2. Faire corriger le bug n° 1 du backlog en fournissant le message d'erreur
   complet ; exiger que les tests passent avant de considérer la tâche finie.
3. Interrompre volontairement l'agent en pleine action (`Échap`), reformuler
   la demande avec une contrainte supplémentaire.
4. Utiliser `Échap` `Échap` pour revenir avant la correction et demander une
   approche différente.
5. `/clear`, puis demander une petite fonctionnalité (bug n° 2 du backlog) en
   appliquant la structure objectif + critère + contraintes.

## Checklist de validation

- [ ] Je sais installer, authentifier et diagnostiquer Claude Code
- [ ] Je sais formuler un prompt avec objectif, critère de réussite et contraintes
- [ ] Je sais interrompre, rembobiner (`Échap` `Échap`) et repartir proprement
- [ ] Je sais quand utiliser `/clear` vs `/compact`
- [ ] J'exige systématiquement une vérification (tests) en fin de tâche
