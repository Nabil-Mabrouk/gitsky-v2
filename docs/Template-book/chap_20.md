# Cycle de Vie d'un Projet dans la Flotte

## Introduction

Ce chapitre formalise le cycle de vie complet d'un projet GitSky, de sa création à son archivage ou sa sortie de la flotte. Il rassemble sous une même chronologie des concepts distribués dans les chapitres précédents — catalogue de modules (Chap 2), création et générateur (Chap 17), intégration GitHub (Chap 26), assistant de création (Chap 27), fleet dashboard (Chap 19), maintenance (Chap 23).

L'objectif est double : donner à l'opérateur un playbook clair, et documenter le contrat de la flotte pour tout collaborateur qui interviendrait sur un projet.

## Vue d'Ensemble : Six Étapes

```text
+----------+----------------+------------+-------------+-------------+---------------+
| Besoin   | Création       | Personna-  | Déploiement | Maintenance | Archivage ou  |
|          | (wizard/CLI)   | lisation   | continu     |             | sortie flotte |
+----------+----------------+------------+-------------+-------------+---------------+
```

Chaque étape a ses **entrées**, ses **livrables**, et ses **critères de passage à la suivante** — mais contrairement aux versions antérieures de ce livre, aucun de ces critères n'est un seuil numérique évalué automatiquement. Chaque transition est une décision de l'opérateur ou un événement technique (un push Git, par exemple), jamais un score.

## Étape 1 — Création

Le projet naît d'un choix explicite : un nom, un sous-ensemble du catalogue de modules (Chap 2), un domaine, et un dépôt GitHub (nouveau ou existant).

**Entrées :** nom du projet, modules à activer, domaine souhaité, informations GitHub.

**Deux chemins possibles :**

- **L'assistant de création** (Chap 27) — le chemin recommandé : un formulaire dans le fleet dashboard qui couvre les quatre entrées ci-dessus et déclenche la création + le premier déploiement en une action.
- **Le générateur en ligne de commande** (Chap 17) — `copier copy --data-file config.yaml <template> <dest>`, utile pour scripter la création de plusieurs projets ou pour un usage hors dashboard.

**Livrables :** un projet démarrable, un premier commit dans son dépôt GitHub, une entrée dans le fleet dashboard, un premier déploiement en ligne derrière Traefik.

**Critère de passage à l'étape suivante :** le projet répond sur `/health` avec un statut `200`.

## Étape 2 — Personnalisation via GitHub

Le projet généré est un point de départ professionnel, pas un produit fini. La logique métier propre au projet (Chap 11 pour un exemple complet) se développe dans le dépôt GitHub créé à l'étape précédente — localement, comme n'importe quel projet FastAPI/React.

**Activités :**

- Cloner le dépôt (`git clone`, ou via la clé de déploiement/l'installation GitHub App si le dépôt est privé — Chap 26).
- Ajouter les modèles et routeurs métier dans `app/domain/`.
- Ajouter les composants React nécessaires côté frontend.
- Committer et pousser sur la branche par défaut.

**Livrable :** un dépôt GitHub qui contient à la fois le chassis GitSky et le code métier du projet.

## Étape 3 — Déploiement Continu

Chaque push sur la branche par défaut déclenche un redéploiement, sans intervention manuelle — décrit en détail au Chap 26.

**Le chemin automatique (dépôt créé par GitSky, webhook actif) :**

1. GitHub notifie le webhook du fleet dashboard.
2. Le pipeline exécute `git pull`, applique un `copier update` si le template a évolué, reconstruit et redémarre les conteneurs (`docker compose up -d --build`), applique les migrations via le service `migrate`.
3. Un contrôle de santé (`/health`) confirme le succès ; l'échec est journalisé et visible au dashboard (Chap 19).

**Le chemin manuel (dépôt existant lié sans droits webhook) :** l'opérateur déclenche le redéploiement d'un clic depuis le dashboard, qui exécute la même séquence à la demande plutôt que sur événement `push`.

## Étape 4 — Maintenance

Un projet en production n'est jamais "terminé" — il entre dans le régime de maintenance mutualisée décrit au Chap 23 : sauvegardes 3-2-1 automatiques, monitoring de disponibilité, revue hebdomadaire des `security_events`, rotation périodique des secrets.

Le fleet dashboard (Chap 19) continue de faire remonter des alertes tout au long de cette étape — coût inhabituel, échec de santé prolongé, événements de sécurité en rafale. Ces alertes ne déclenchent plus aucune action automatique : elles informent l'opérateur, qui décide.

## Étape 5 (optionnelle) — Migration Sous-Domaine → Domaine Premier

Un projet créé sur un sous-domaine de la flotte (`mon-projet.mystudio.com`) peut, à tout moment où l'opérateur le juge pertinent, migrer vers un domaine dédié (`mon-projet.com`). Cette migration doit préserver le SEO déjà acquis et ne pas casser les liens partagés par des utilisateurs. Procédure en quatre étapes :

### Étape 1 — Provisionnement du Nouveau Domaine (J-7)

- Achat du domaine.
- Configuration DNS chez le registrar : enregistrement `A` vers l'IP du VPS, `MX` vers le SMTP relay partagé si le projet reçoit des emails, `CAA` autorisant Let's Encrypt.
- Ajout des labels Traefik du projet pour accepter les **deux domaines simultanément**.
- Génération du certificat pour le nouveau domaine (Let's Encrypt HTTP-01 — pas DNS-01, ce n'est pas un wildcard).

### Étape 2 — Préparation SEO (J-4)

- Email aux utilisateurs annonçant le nouveau domaine.
- Mise à jour du `canonical` de toutes les pages vers le **nouveau** domaine (Chap 10).
- Mise à jour du `sitemap.xml`, soumission à Google Search Console pour le nouveau domaine.

### Étape 3 — Bascule Primaire (J-0)

- Inversion du `PROJECT_DOMAIN` dans le `.env` : le nouveau domaine devient primaire.
- L'ancien sous-domaine renvoie une **redirection 301** via un middleware Traefik :

```yaml
labels:
  - "traefik.http.middlewares.redirect-old.redirectregex.regex=^https://mon-projet.mystudio.com/(.*)"
  - "traefik.http.middlewares.redirect-old.redirectregex.replacement=https://mon-projet.com/$${1}"
  - "traefik.http.middlewares.redirect-old.redirectregex.permanent=true"
```

- Email de confirmation aux utilisateurs.

### Étape 4 — Suivi (J+30)

- Vérification que Google indexe le nouveau domaine et déprécie l'ancien.
- Vérification du trafic organique : la baisse initiale (~30-40 %) doit se résorber en 6-8 semaines.
- L'ancien sous-domaine reste actif **en redirection au moins 12 mois** — jamais supprimé tant que des liens externes peuvent exister.

### Anti-Patterns à Éviter

- **Suppression brutale du sous-domaine** — casse tous les liens externes accumulés, perte SEO définitive.
- **Absence de redirection 301** — Google traite le nouveau domaine comme un site vierge.
- **Migration pendant une campagne active** — la baisse SEO temporaire tue le rendement des campagnes en cours.

## Étape 6 — Archivage ou Sortie de Flotte

### Option A — Rester dans la flotte

Le cas par défaut : le projet continue à bénéficier des services partagés indéfiniment, tant que l'opérateur ne décide pas de l'archiver.

### Option B — Archivage

L'opérateur archive un projet manuellement depuis le fleet dashboard — jamais via un `docker compose down` ad hoc, sinon la sauvegarde et la journalisation ne se font pas. La procédure :

1. `docker compose down` dans le dossier du projet.
2. Retrait des labels Traefik.
3. Dump PostgreSQL compressé archivé sur stockage froid (S3, Backblaze) — conservé au minimum 90 jours.
4. Le sous-domaine reste réservé pendant 30 jours (garde contre le squatting immédiat) avant d'être libéré.
5. Journalisation dans le fleet dashboard : statut `archived`, date, raison saisie par l'opérateur.

### Option C — Sortie de la Flotte (Émancipation)

Quand un projet devient suffisamment important pour justifier une infrastructure dédiée — charge, exigences de conformité, revenus qui dépassent ce qu'une flotte mutualisée doit raisonnablement porter — l'opérateur peut l'en extraire :

- Migration vers un compte Stripe propre (rattachement à une entité juridique dédiée).
- Migration vers un VPS dédié (ou cluster).
- Extraction de la base PostgreSQL du service partagé vers une base dédiée.
- Retrait des labels Traefik du proxy partagé.

Cette procédure est décrite dans le playbook `docs/emancipation.md` du repo `startup-factory-configs/`. Elle est réversible en cas de sur-anticipation.

### Option D — Vente ou Acqui-Hire

Un projet à traction significative peut être vendu. L'isolation stricte de la flotte (une DB, un domaine, un compte Stripe metadata-namespacé, un dépôt GitHub propre) rend cette extraction mécanique.

## Reconstitution d'un Projet Archivé

Un projet archivé peut être ressuscité si un besoin resurgit :

1. Extraire le dump PostgreSQL du stockage froid.
2. Regénérer le projet via `copier copy` avec le même `config.yaml` (versionné dans `startup-factory-configs/`).
3. Restaurer la base.
4. Redéployer, réactiver le webhook GitHub si nécessaire.

Cette procédure prend environ 30 minutes. La conservation des dumps pendant 90 jours minimum rend cette option disponible.

## Le Journal de la Flotte

Chaque événement du cycle de vie (création, redéploiement, mise à jour de template, changement de domaine, archivage) est journalisé dans une table `fleet_lifecycle_events` interrogeable depuis le fleet dashboard. Ce journal permet de calculer :

- Le nombre de projets actifs vs. archivés dans le temps.
- L'ancienneté moyenne d'un projet dans la flotte.
- La fraction de la flotte à jour du dernier `copier update` — utile pour prioriser la propagation d'un correctif de sécurité.

---

*Ce chapitre clôt la partie industrialisation. La dernière partie du livre couvre la production et la maintenance : configuration du serveur Ubuntu, sauvegardes de flotte et bonnes pratiques opérationnelles.*
