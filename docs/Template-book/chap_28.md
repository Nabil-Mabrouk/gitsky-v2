# Refonte Visuelle du Dashboard

## Introduction

Les cinq chapitres précédents (Chap 19, 23, 26, 27) ont construit la matière du fleet dashboard — grille de projets, monitoring de disponibilité, intégration GitHub, assistant de création — sans jamais s'arrêter sur sa présentation : jusqu'ici, un tableau HTML brut, aucun thème sombre, aucun signal visuel de santé par projet, et deux journaux d'événements (`fleet_lifecycle_events`, `fleet_maintenance_runs`) consultables séparément mais jamais l'un à côté de l'autre. Ce chapitre clôt la roadmap (Phase F) par un vrai passage de design sur le shell admin, la grille, et un nouvel onglet Activité — sans changer un seul contrat d'API existant.

> Ce chapitre documente un état volontairement partiel. Le shell admin (`AdminLayout`), la grille de flotte (`FleetGrid`) et le nouvel onglet Activité ont reçu la refonte complète. Les autres onglets — Leads, Maintenance, Utilisateurs, Waitlist, Analytics, Sécurité — héritent du nouveau thème de couleurs (ils sont rendus à l'intérieur du même shell) mais gardent leur mise en page d'origine : ce n'est pas caché, c'est listé en fin de chapitre.

## Le Système de Tokens Admin

`admin-theme.css` (chargé uniquement par `AdminLayout.tsx`, jamais globalement) reprend le patron déjà en place pour la landing (`landing.css`, Chap 24) : un jeu de tokens CSS clairs par défaut sur `:root`, redéfinis dans un unique `@media (prefers-color-scheme: dark)` — aucun bouton de bascule, aucun JavaScript, le thème suit le système d'exploitation du navigateur.

Les tokens sont préfixés `--admin-*` (`--admin-bg`, `--admin-surface`, `--admin-surface-raised`, `--admin-text`, `--admin-text-muted`, `--admin-border`, `--admin-shadow`, et une paire fond/texte par variante de badge : `success`/`warning`/`danger`/`info`/`neutral`) — délibérément distincts des tokens `--bg`/`--surface`/`--text`/`--border` de `landing.css`. Le frontend n'est pas code-splitté par route : toutes les feuilles de style importées finissent dans le même bundle CSS, et deux fichiers qui définiraient les mêmes noms sur `:root` s'écraseraient silencieusement selon l'ordre de chargement. `--color-primary`/`--color-primary-foreground` (Chap 24, `theme.css.jinja`) restent inchangés et partagés partout — l'identité de marque ne varie ni entre pages, ni entre les deux modes.

## Composants Partagés

Deux composants React neufs, sous `src/components/admin/`, réutilisés par la grille et l'onglet Activité :

- **`Badge`** : un pastille de statut à cinq variantes (`success`/`warning`/`danger`/`info`/`neutral`), posée uniquement sur les tokens `--admin-*` — jamais de couleur en dur, donc correcte en dark mode sans code spécifique.
- **`Card`** : une surface avec bordure et ombre légère (`.admin-card`), utilisée pour chaque carte de projet et chaque ligne d'activité.

## La Grille de Flotte, en Cartes

`FleetGrid` (Chap 19) passe d'un tableau trié en colonnes à une grille de cartes (`grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))` — responsive sans media query). Chaque carte affiche :

- le nom du projet (lien vers sa fiche, Chap 19 §Actions) et un badge de **santé** ;
- le domaine ;
- des badges **statut** (`active`/`archived`) et **statut de publication** (`draft`/`preview`/`live`) ;
- l'état du dépôt GitHub : aucun dépôt, dépôt lié sans webhook, ou dépôt lié avec redeploy automatique actif.

Le tri par colonne devient un sélecteur (nom, domaine, statut, statut de publication, santé) — la mécanique de tri elle-même (comparaison sur la clé choisie, sens inversible) est inchangée depuis la version tableau.

### Le Champ `health`

`GET /api/fleet/projects` attache désormais un champ `health` (`"healthy"` / `"failing"` / `"unknown"`) à chaque projet, calculé par `health_monitor.bulk_health_status` **en une seule requête** pour toute la grille (pas de N+1 — une requête par projet aurait été la façon naïve de faire). Le calcul dérive du dernier événement de disponibilité déjà journalisé par le monitoring (Chap 23, `deployment_failed`/`deployment_recovered`) — **rien n'est stocké séparément** ; `fleet_lifecycle_events` reste la seule source de vérité pour la santé comme pour le reste du cycle de vie (Chap 19 §« Le Fleet Dashboard comme Contrat »).

`"unknown"` ne veut pas dire « en panne » : ça veut dire qu'aucun balayage de disponibilité n'a encore eu lieu pour ce projet (venant d'être créé, ou monitoring pas encore passé) — distinct de `"healthy"`, qui suppose qu'au moins un balayage a eu lieu sans jamais détecter de panne, ou que la dernière panne détectée s'est résorbée.

Ce champ `health` n'est calculé **que** par `GET /projects` (la grille) : les autres endpoints qui renvoient aussi un objet projet (`register`, `archive`, `promote`, les endpoints GitHub, la création) renvoient `"unknown"` par défaut sans mentir sur une santé qu'ils n'ont pas recalculée — un choix explicite plutôt qu'un enrichissement systématique qui aurait ajouté une requête à des endpoints qui n'en ont pas besoin.

## Le Nouvel Onglet Activité

`GET /api/fleet/activity` fusionne, triés du plus récent au plus ancien, les deux journaux que la base du fleet dashboard possède réellement :

- `fleet_lifecycle_events` (`born`, `archived`, `deployment_failed`, `deployment_recovered`, `deploy_triggered`, `github_repo_created`, `github_repo_linked`, `publish_preview`, `publish_live`…) ;
- `fleet_maintenance_runs` (Chap 22, sauvegardes et jobs planifiés).

Aucune table n'est créée pour ça — c'est un assemblage de lecture, pas une nouvelle source de vérité (même principe que le champ `health` ci-dessus). Le paramètre `limit` est borné entre 1 et 200 (un `0` ou une valeur négative ne renvoie jamais une liste vide implicite par abus de paramètre — le plancher est 1).

**Ce que ce flux n'inclut délibérément pas : `security_events`.** Chaque projet généré a sa propre base PostgreSQL isolée (Chap 18 §2) — `security_events` y vit, pas dans la base du fleet dashboard. Fusionner ce troisième journal demanderait une requête inter-bases à travers potentiellement des dizaines de conteneurs PostgreSQL indépendants, une infrastructure qui n'existe pas et que ce chapitre ne fabrique pas pour donner l'illusion d'un flux complet. L'onglet Sécurité (Chap 19) reste, pour l'instant, le seul endroit où consulter les événements de sécurité — projet par projet.

## Le Shell Admin

`AdminLayout` (Chap 9) reçoit la barre latérale posée sur les nouveaux tokens (`--admin-surface`, état actif teinté `--color-primary`), et un nouvel onglet **Activité** (`moduleFlag: "fleet"` — même garde que la grille et les leads, pas de flag dédié puisque ce n'est pas un module optionnel mais une vue sur des données déjà exposées par le module `fleet`).

## Ce qui Manque Encore

1. **Les autres onglets n'ont pas reçu la refonte complète.** Leads, Maintenance, Utilisateurs, Waitlist, Analytics, Sécurité restent sur leur mise en page en tableau HTML brut d'origine (Chap 9) — ils héritent du fond/texte du nouveau thème parce qu'ils sont rendus à l'intérieur du même `AdminLayout`, mais leurs propres composants n'ont pas été retouchés. Un passage de design dédié à chacun reste à faire, au cas par cas.
2. **Pas de bascule de thème manuelle.** Comme la landing (Chap 24), le mode sombre suit uniquement les préférences système du navigateur — aucun bouton, aucune préférence persistée côté serveur.
3. **L'onglet Sécurité par projet n'est pas fusionné dans le flux Activité**, pour la raison d'isolation de base expliquée plus haut — resterait à construire une agrégation inter-bases, hors périmètre de ce chapitre.
4. **Pas de rafraîchissement automatique.** La grille et le flux Activité se chargent une fois au montage de la page ; un opérateur qui veut voir l'état à jour recharge la page — pas de WebSocket ni de polling périodique.

## Checklist du Chapitre

- [ ] Je sais où `admin-theme.css` est chargé (uniquement par `AdminLayout.tsx`) et pourquoi ses tokens sont préfixés `--admin-*`
- [ ] Je sais que `health` n'est calculé avec précision que par `GET /api/fleet/projects` — les autres endpoints renvoient `"unknown"` par défaut
- [ ] Je sais que le flux Activité fusionne deux journaux existants sans en créer un troisième, et pourquoi `security_events` en est exclu
- [ ] Je sais que seuls le shell, la grille et l'onglet Activité ont reçu la refonte complète — les autres onglets gardent leur mise en page d'origine

---

*Ce chapitre clôt la roadmap en six phases ouverte au Chap 2 : catalogue de modules à plat, flotte sans mécanisme de kill automatique, intégration GitHub, assistant de création, et maintenant une présentation du dashboard qui ne cache plus ses propres limites derrière un tableau gris. Ce qui reste — les onglets non retouchés, la fusion des événements de sécurité, un flux temps réel — est listé, pas promis.*
