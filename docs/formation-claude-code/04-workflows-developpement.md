# Module 4 — Workflows de développement professionnels (3 h)

## Objectifs

- Structurer une tâche complexe : explorer → planifier → implémenter → vérifier
- Utiliser le plan mode comme outil de cadrage
- Pratiquer le TDD avec un agent
- Intégrer Claude Code au workflow Git/GitHub : commits, PR, revue de code
- Savoir déboguer et reprendre la main quand l'agent s'égare

## 1. Le cycle EPIV : Explorer, Planifier, Implémenter, Vérifier

L'erreur du débutant : demander l'implémentation directement pour toute tâche.
Sur une tâche non triviale, le workflow professionnel est en quatre temps :

1. **Explorer** — faire lire le code pertinent sans rien modifier :
   « Lis le module de paiement et les tests associés. Ne modifie rien. »
2. **Planifier** — exiger un plan et le **critiquer** avant d'exécuter.
3. **Implémenter** — dérouler le plan, par étapes si besoin.
4. **Vérifier** — tests, lint, exécution réelle ; ne jamais accepter
   « ça devrait marcher » sans preuve.

Plus la tâche est grosse, plus les phases 1–2 sont rentables. Pour un typo
fix, on s'en passe.

### Le plan mode

- Activation : `Maj+Tab` jusqu'à `plan`, ou `claude --permission-mode plan`
- L'agent est en **lecture seule** : il explore et produit un plan structuré
- À la sortie du plan mode, vous validez le plan avant toute modification

Usage pro : systématique pour les refactorings, migrations, features
transverses. Le plan est un livrable : on peut le faire écrire dans un
fichier (`docs/plans/2026-07-refonte-auth.md`) pour le partager en équipe
et le réutiliser dans une session fraîche.

**Critiquer le plan est le cœur du métier.** Questions à poser : quelles
alternatives as-tu écartées et pourquoi ? Quel est le risque de régression ?
Quelles parties du plan sont incertaines ?

## 2. TDD avec un agent

Le TDD est **plus** efficace avec un agent qu'en solo, car il donne à l'agent
un critère de réussite mécanique.

Workflow :

```
1. « Écris les tests pour [comportement], d'après ces specs.
   N'écris PAS l'implémentation. Les tests doivent échouer pour l'instant. »
2. Vérifier/committer les tests.
3. « Maintenant implémente pour faire passer ces tests.
   Ne modifie pas les tests. Itère jusqu'à ce que tout passe. »
4. Revue du diff, refactoring éventuel, commit.
```

Points de vigilance :

- Interdire explicitement la modification des tests en phase 3 (sinon l'agent
  peut « tricher » en adaptant le test au bug)
- Se méfier des implémentations qui sur-spécialisent pour le test (hardcoding) ;
  demander un test supplémentaire en cas de doute

## 3. Git et GitHub au quotidien

Claude Code manipule Git nativement et GitHub via le CLI `gh`.

### Commits

- « Commit ce travail » : l'agent rédige un message à partir du diff réel —
  relire, c'est vous qui signez
- Conventions de message dans `CLAUDE.md` (langue, format)
- Bonnes pratiques : petits commits fréquents = meilleurs points de rewind

### Pull requests et revue

- « Crée une PR » : branche, push, description générée (`gh pr create`)
- `/review` : faire relire une PR existante
- `/code-review` : revue du diff courant avant de pousser, avec un niveau
  d'effort (low → high). À intégrer au rituel : **revue agent avant revue
  humaine**, pour que les humains ne perdent pas de temps sur ce qu'une
  machine détecte
- `/security-review` : passe orientée vulnérabilités sur les changements en cours

La revue par l'agent ne remplace pas la revue humaine : elle la **précède**.

### Sessions parallèles et worktrees

Pour mener deux tâches de front sans qu'elles se marchent dessus :

```bash
git worktree add ../projet-feature-x feature-x
# puis lancer claude dans chaque worktree
```

Un agent par worktree = isolation complète des fichiers. C'est le patron
recommandé pour la parallélisation locale (voir aussi module 7).

## 4. Déboguer avec l'agent — et déboguer l'agent

### Déboguer avec l'agent

- Fournir : message d'erreur complet, étapes de reproduction, contexte
  (« ça marchait avant le commit X »)
- Demander la **cause racine**, pas seulement le correctif : « explique la
  cause avant de corriger » — évite les patchs symptomatiques
- Exiger un test de non-régression avec le correctif

### Quand l'agent s'égare

Signaux : il tourne en rond, réécrit le même fichier, « corrige » en
supprimant des tests, propose une réécriture géante pour un petit bug.

Réflexes :

1. `Échap` — arrêter tout de suite
2. `Échap` `Échap` — rembobiner au dernier point sain
3. Rétrécir le problème : donner le fichier exact, l'approche à suivre
4. Si le contexte est pollué : `/clear` et repartir avec un prompt qui intègre
   ce qu'on a appris (« l'approche A échoue à cause de B ; pars sur C »)

**Anti-pattern : négocier 10 tours de suite avec un agent embourbé.** Deux
corrections infructueuses = on rembobine et on reformule.

## 5. TP guidé (1 h 15)

1. **Plan mode** : en mode plan, cadrer la feature n° 3 du backlog ; critiquer
   le plan (au moins deux questions), le faire amender, puis exécuter.
2. **TDD** : implémenter la feature n° 4 en TDD strict (tests d'abord,
   commit, implémentation sans toucher aux tests).
3. **PR** : créer une branche, committer, faire générer la PR ; lancer
   `/code-review` et traiter au moins une remarque avant de pousser.
4. **Récupération** : le formateur fournit un prompt piégé (tâche ambiguë) ;
   détecter l'égarement, rembobiner, reformuler, réussir.

## Checklist de validation

- [ ] Je sais dérouler le cycle Explorer → Planifier → Implémenter → Vérifier
- [ ] J'utilise le plan mode pour toute tâche structurante et je critique le plan
- [ ] Je sais mener un TDD avec l'agent en verrouillant les tests
- [ ] Je fais précéder toute revue humaine d'un `/code-review`
- [ ] Je reconnais un agent qui s'égare et j'applique interruption → rewind → reformulation
