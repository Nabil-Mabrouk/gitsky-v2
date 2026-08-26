# Le Catalogue de Modules de GitSky

## Introduction

GitSky n'est pas destiné à un projet unique. Il est conçu comme un **template industriel** capable de porter un grand nombre de projets web indépendants, hébergés ensemble sur la même flotte. Les premières versions de ce livre organisaient cela autour d'un système à trois paliers (T0/T1/T2) empruntés à la logique de la *startup factory* — un projet gagnait en complexité au fur et à mesure qu'il prouvait un signal de traction. Cette logique convenait à un usage précis (tester des idées jetables), mais elle imposait une rigidité inutile dès que GitSky sert à héberger des projets qui existent déjà, ou qui n'ont simplement pas vocation à suivre une trajectoire de croissance mesurée par des seuils.

La version actuelle du template abandonne les paliers. Chaque projet est créé **complet dès le départ** — sa propre base PostgreSQL isolée, ses propres conteneurs, son propre domaine — et l'opérateur choisit, module par module, les fonctionnalités dont ce projet précis a besoin. Un module non activé ne charge aucune route, aucun modèle SQL, aucune migration Alembic : un projet léger reste léger non pas parce qu'il est enfermé dans un palier inférieur, mais simplement parce que le code inutile n'entre jamais dans le process qui tourne.

## 1. Le Principe : un Catalogue à Plat, Pas d'Escalier

Chaque module de GitSky s'active ou se désactive indépendamment via une variable d'environnement `MODULE_*`, sans dépendre d'un profil imposé. Deux modules forment le **socle toujours actif** — sans eux, il n'y a pas de projet exploitable — et le reste du catalogue est optionnel.

| Module | Statut | Ce qu'il apporte |
|---|---|---|
| Authentification (JWT + refresh) & gestion des utilisateurs | Core, toujours actif | Comptes, rôles, sessions — présent dès la création de tout projet |
| SEO dynamique | Core, toujours actif | Sitemap, robots.txt, meta tags — pas de flag `MODULE_*`, fait partie du chassis (Chap 10) |
| Admin shell | Optionnel | Dashboard `/admin` : gestion des utilisateurs, waitlist, et un onglet par module activé qui en expose un (Chap 9) |
| Analytics GeoIP + carte du monde | Optionnel | Suivi de trafic, visites, conversion (Chap 13) |
| Onboarding dynamique | Optionnel | Profilage progressif d'un nouvel utilisateur (Chap 12) |
| Content system (tutoriaux/leçons) | Optionnel | Contenu pédagogique ou documentation gérable depuis l'admin (Chap 11) |
| Framework agentic IA | Optionnel | Services IA outillés (agents, outils, quotas) pour le projet (Chap 15) |
| Monétisation boutique (Stripe) | Optionnel | Produits, achats ponctuels (Chap 16) |
| Monétisation abonnements (Stripe) | Optionnel | Abonnements récurrents (Chap 16) |
| Security middleware | Optionnel | Détection d'intrusion, journal `security_events` (Chap 14) |
| Internationalisation (i18n) | Optionnel | Contenu multilingue FR/EN (Chap 8) |
| Fleet | Réservé au dashboard de flotte lui-même | Jamais activé sur un projet applicatif ordinaire — uniquement sur l'app qui pilote la flotte (Chap 19) |

Le principe reste celui déjà énoncé dans les versions précédentes du chassis : **un module désactivé ne coûte rien**, à l'exécution comme à la construction — mais il n'existe plus de combinaison de modules "interdite" ou "réservée à un palier supérieur". Un projet peut activer la monétisation sans l'admin shell, ou l'agentic sans l'analytics, si c'est ce dont il a besoin.

## 2. Empreinte : une Question de Modules, Pas de Palier

L'empreinte mémoire d'un projet dépend directement des modules qu'il active, pas d'une catégorie qui lui serait assignée. Le tableau ci-dessous donne des combinaisons typiques à titre indicatif — ce ne sont pas des paliers imposés, seulement des repères pour dimensionner un VPS :

| Combinaison typique | Modules actifs | RAM indicative |
|---|---|---|
| Landing seule | Core (auth + SEO) uniquement | ~50-80 Mo |
| Application avec compte utilisateur | Core + admin + analytics | ~180-250 Mo |
| SaaS complet | Core + admin + analytics + i18n + monétisation + agentic | ~700 Mo à 1 Go |

Un projet peut parfaitement se situer entre ces repères, ou les dépasser — rien dans l'architecture n'impose de rester dans une case. Sur un VPS mutualisé de 8 Go à ~20 €/mois, ces ordres de grandeur permettent d'héberger simultanément plusieurs dizaines de projets légers, ou un nombre plus restreint de projets complets, ou un mélange des deux (voir Chap 1 pour l'architecture d'hébergement mutualisé).

## 3. Choisir ses Modules à la Création

Le générateur (Chap 17) expose un bloc `modules` dans le `config.yaml` de chaque projet — une simple liste de booléens, sans logique de profil à résoudre au préalable :

```yaml
modules:
  admin: true
  analytics: true
  monetization_subscription: true
  agentic: false
```

Tout module omis du bloc reste désactivé par défaut (sauf le socle core, toujours actif). Rien n'empêche de revenir sur ce choix plus tard : activer un module supplémentaire après coup est un changement de configuration (`.env` du projet + redéploiement), jamais une réécriture — puisque GitSky ne construit qu'**un seul Dockerfile**, identique quels que soient les modules choisis (Chap 21). Le Chapitre 27 décrit l'assistant de création qui rend ce choix accessible depuis le dashboard, sans édition manuelle de YAML.

## 4. Cycle de Vie d'un Projet : Créé → Actif → Archivé

Sans paliers, il n'y a plus de critère numérique de promotion ni de mécanisme de kill automatique. Le cycle de vie d'un projet GitSky tient en trois états :

- **Créé** : le projet vient d'être généré et déployé (Chap 17, Chap 27), il apparaît dans le fleet dashboard.
- **Actif** : le projet tourne normalement. L'opérateur peut à tout moment ajuster ses modules, son domaine, ou consulter son état de santé et de sécurité depuis le dashboard (Chap 19).
- **Archivé** : l'opérateur a décidé, manuellement, d'arrêter le projet. Le dashboard exécute alors la procédure d'archivage — arrêt des conteneurs, sauvegarde froide de la base conservée, libération du domaine après un délai de grâce (détaillé au Chap 19 et Chap 20).

Aucune bascule n'est automatique : ni la mise en route d'un module, ni l'archivage. C'est un choix délibéré — GitSky ne pose plus d'hypothèse sur la trajectoire attendue d'un projet (test d'idée, produit établi, projet client…), donc il ne peut plus décider à sa place quand un projet a "réussi" ou "échoué". Le dashboard reste néanmoins un allié actif : il continue de faire remonter des alertes (coût, santé, sécurité — Chap 19) pour que la décision d'archiver reste éclairée, même si elle n'est plus prise par un script.

## 5. Anti-Patterns à Éviter

**Activer tous les modules "au cas où".** Chaque module actif ajoute de la RAM, de la surface d'attaque, et des migrations à maintenir. Le catalogue à plat rend cela tentant puisqu'il n'y a plus de palier qui le décourage explicitement — la discipline doit venir de l'opérateur : n'activer que ce que le projet utilise réellement aujourd'hui.

**Dupliquer un projet en copiant ses fichiers plutôt qu'en le régénérant.** Comme au Chap 17 : un clone hérite des dérives et ne bénéficie plus jamais de `copier update`.

**Laisser un projet inactif tourner indéfiniment faute de décision.** Sans kill automatique, un projet mort ne s'arrête plus tout seul — il consomme des ressources et de l'attention jusqu'à ce que l'opérateur agisse. La routine matinale sur le fleet dashboard (Chap 19, Chap 23) est ce qui remplace la discipline qu'apportait autrefois le mécanisme de kill : elle doit rester un réflexe, pas une option.

## Checklist du Chapitre

- [ ] Je sais quels modules sont core (toujours actifs) et lesquels sont optionnels
- [ ] Je choisis les modules d'un nouveau projet en fonction de ses besoins réels, pas "par défaut" ou "au cas où"
- [ ] Je sais qu'activer un module plus tard ne demande qu'une reconfiguration, jamais une réécriture
- [ ] Je consulte régulièrement le fleet dashboard pour repérer moi-même les projets à archiver
- [ ] Je comprends que l'archivage est désormais une décision humaine, pas un script automatique

---

*Ce catalogue de modules structure tout le reste de l'ouvrage : la Partie II décrit le core présent à tout projet, la Partie III les modules optionnels que chaque projet active à la carte, et la Partie IV le générateur et la flotte qui rendent l'ensemble opérationnel à grande échelle — génération (Chap 17), assistant de création et intégration GitHub (Chap 26-27), services partagés (Chap 18), fleet dashboard (Chap 19) et cycle de vie (Chap 20). Dans le prochain chapitre, nous détaillons l'initialisation du backend FastAPI, socle commun à tout projet GitSky.*
