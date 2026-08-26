# L'Assistant de Création

## Introduction

Les Chap 2, 17 et 26 posent chacun une pièce : le catalogue de modules, le générateur Copier, l'intégration GitHub. L'assistant de création est ce qui les assemble en un seul parcours, accessible depuis le fleet dashboard, sans édition manuelle de YAML ni ligne de commande : nom du projet, modules, GitHub, domaine — et un clic pour créer et déployer.

> **État d'implémentation.** Comme le Chap 26, ce chapitre documente la conception cible de l'assistant (feuille de route, phase E) — l'interface et le point d'entrée backend qu'il décrit sont à construire par-dessus les fondations déjà posées (générateur, fleet dashboard, catalogue de modules).

## 1. Le Parcours en Cinq Étapes

### Étape 1 — Nom du Projet

Un champ texte, validé en direct contre le registre du fleet dashboard (Chap 19) pour éviter un doublon. Le nom choisi devient `PROJECT_NAME` et préfixe toutes les ressources Docker (Chap 1).

### Étape 2 — Modules

Une liste à cocher reprenant le catalogue du Chap 2 — le socle (auth, SEO) est coché et grisé, non désactivable. Chaque case cochée met à jour une estimation d'empreinte RAM affichée en direct, sur la base des repères du Chap 2, pour que l'opérateur voie le compromis avant de valider.

### Étape 3 — GitHub

Deux choix, décrits en détail au Chap 26 :

- **Créer un nouveau dépôt** — l'assistant propose un nom de dépôt dérivé du nom du projet, modifiable.
- **Lier un dépôt existant** — un champ pour l'URL du dépôt ; l'assistant indique si la GitHub App y a accès (webhook installable) ou non (repli sur redéploiement manuel).

### Étape 4 — Domaine

- **Sous-domaine de la flotte** (par défaut) — `<nom-du-projet>.mystudio.com`, disponible immédiatement grâce au certificat wildcard partagé (Chap 1).
- **Domaine dédié** — l'opérateur saisit un domaine déjà pointé vers l'IP du VPS ; l'assistant avertit si la résolution DNS n'est pas encore en place (la génération du certificat Let's Encrypt échouera sinon — Chap 22 FAQ).

### Étape 5 — Récapitulatif

Une synthèse des quatre choix précédents, avec un bouton unique : **Créer & Déployer**.

## 2. Ce qui se Passe Après le Clic

Un nouvel endpoint backend orchestre la création :

```
POST /api/fleet/projects
```

Séquence :

1. **Assemblage du payload** — le formulaire est traduit côté serveur en l'équivalent d'un `config.yaml` (Chap 17), sans jamais exposer sa syntaxe à l'opérateur.
2. **Génération** — le générateur est invoqué via l'**API Python de Copier** (`copier.run_copy(...)`), pas par un appel CLI shell-out : cela permet de contrôler précisément la portée de `unsafe=True` (l'équivalent programmatique de `--trust`) plutôt que de la déléguer à un sous-processus.
3. **GitHub** — création ou liaison du dépôt, push du commit initial, installation du webhook (Chap 26).
4. **Premier déploiement** — `docker compose up -d --build`, migrations, contrôle de santé (Chap 21/25 §2).
5. **Enregistrement** — le projet apparaît dans le fleet dashboard (Chap 19).

Cette séquence prend un temps réel (générer, pousser sur GitHub, builder les images, démarrer les conteneurs — potentiellement plusieurs minutes). L'assistant ne bloque pas silencieusement : chaque étape met à jour un indicateur de progression dans l'interface (streaming via SSE, ou interrogation périodique du statut) : *Génération du projet… → Création du dépôt GitHub… → Premier déploiement… → Vérification de la santé… → Prêt.*

## 3. Validation et Gestion des Erreurs

- **Nom déjà pris** ou **domaine déjà utilisé par un autre projet** : bloqué avant tout appel au générateur.
- **Domaine dédié mal résolu** : avertissement à l'étape 4, mais création possible quand même (l'opérateur corrigera le DNS avant que le certificat ne soit tenté) — l'assistant ne doit pas empêcher un cas d'usage légitime (préparer un projet avant que le DNS ne se propage).
- **Échec en cours de séquence** (ex. le dépôt GitHub est créé mais le premier déploiement échoue) : l'assistant ne repart pas de zéro. Le projet est marqué `creation_failed` dans le fleet dashboard, avec la dernière étape atteinte visible, et l'opérateur reprend depuis le bouton « Redéployer » (Chap 19, Chap 26 §5) plutôt que de régénérer un doublon.

## 4. Après la Création

L'assistant redirige vers la page détail du projet dans le fleet dashboard (Chap 19), avec un rappel des prochaines étapes : cloner le dépôt, développer la logique métier (Chap 20 étape 2), pousser — le déploiement continu (Chap 26) prend le relais automatiquement.

## Anti-Patterns à Éviter

- **Bloquer l'interface sans retour de progression.** La séquence de création dure plusieurs minutes ; un assistant silencieux donne l'impression d'un plantage.
- **Autoriser des noms de projet dupliqués.** Casserait le préfixage `PROJECT_NAME` et les routes Traefik d'un projet existant.
- **Cacher l'estimation d'empreinte des modules.** L'opérateur doit voir le compromis RAM avant de cocher "tous les modules par réflexe" (anti-pattern déjà signalé au Chap 2).
- **Réactiver toute la séquence depuis zéro après un échec partiel.** Un dépôt GitHub déjà créé ne doit pas être dupliqué à chaque nouvel essai.

## Checklist du Chapitre

- [ ] Je peux créer un projet complet (nom, modules, GitHub, domaine) sans écrire de YAML
- [ ] Je vois l'empreinte RAM estimée avant de valider mes choix de modules
- [ ] Je comprends ce qui se passe entre le clic et le projet en ligne
- [ ] Je sais qu'un échec partiel se rattrape depuis le dashboard, pas en recommençant tout

---

*L'assistant de création clôt la boucle "utiliser" du guide opérateur (Chap 25) : un opérateur n'a plus jamais besoin de toucher une ligne de commande pour faire naître un nouveau projet dans la flotte.*
