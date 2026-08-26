# Introduction : GitSky, un Template Industriel pour Héberger une Flotte de Projets {.unnumbered}

Cet ouvrage ne décrit pas la construction d'une seule webapp. Il pose les fondations d'un **template industriel** — GitSky — capable de porter simultanément un grand nombre de projets web indépendants, chacun avec ses propres modules, son propre domaine, sa propre base de données, hébergés ensemble sur une flotte mutualisée.

**GitSky, un Template et une Discipline**

GitSky n'est pas un produit fini, c'est un système :

*   **Un template paramétrable** basé sur FastAPI, React et PostgreSQL, capable de générer un projet prêt à démarrer via un générateur automatisé (`create-gitsky-project`) ou un assistant de création intégré au dashboard.
*   **Un catalogue de modules à plat** — authentification et SEO en socle toujours actif, admin, analytics, i18n, sécurité, framework agentic, monétisation en options indépendantes — pour que chaque projet n'active que ce dont il a réellement besoin.
*   **Une flotte industrielle** hébergée sur un unique VPS mutualisé, avec services partagés (Traefik, PostgreSQL, LLM proxy, landing-collector optionnel) et un fleet dashboard central pour piloter l'ensemble.
*   **Une intégration GitHub de bout en bout** — chaque projet naît avec son propre dépôt et se redéploie automatiquement à chaque `push`, sans étape manuelle.

L'objectif est de compresser le temps entre le besoin et la webapp déployée, de plusieurs semaines à quelques heures, tout en préservant la qualité d'une architecture professionnelle — et de garder une flotte de dizaines de projets pilotable depuis un seul dashboard, sans que la maintenance ne devienne un travail à plein temps.

**Architecture Cible : un Core Léger, des Modules Optionnels**

Au cœur de GitSky se trouve une architecture stricte en couches :

*   **GitSky-core** : Docker infra, FastAPI shell, gestion des utilisateurs et rôles, authentification JWT, admin shell, SEO de base. Présent dans tout projet.
*   **GitSky-modules** : onboarding dynamique, système de contenu (tutoriaux/leçons), analytics GeoIP, security middleware, framework agentic IA, i18n, monétisation Stripe. Chacun activable indépendamment via variable d'environnement, sans hiérarchie imposée entre eux.
*   **GitSky-app** : la couche applicative métier propre à chaque projet (modèles de données, endpoints, UI spécifiques), développée dans le dépôt GitHub du projet.

Le stack technique est unifié pour tous les projets :

*   **Backend FastAPI** avec SQLAlchemy asynchrone et Pydantic Settings.
*   **Frontend React 19 + Vite + Tailwind 4** pour la vitesse et la réactivité.
*   **PostgreSQL 16** comme socle de persistance, avec une base par projet pour une isolation nette — sans exception.
*   **Docker Compose** pour l'orchestration, **Traefik partagé** pour le routage HTTPS multi-projets.
*   **Framework agentic** activable pour les projets nécessitant des services IA.

Chaque projet ne paie que le coût des modules qu'il active — une landing minimale tient dans quelques dizaines de mégaoctets de RAM, un projet complet avec tous les modules monte à quelques centaines (Chap 2).

**Feuille de Route de l'Ouvrage**

Ce livre est structuré en cinq parties :

1.  **Fondations et Philosophie** — Architecture conteneurisée multi-projets, catalogue de modules.
2.  **GitSky-core** — Ce qui est présent dans tout projet : initialisation FastAPI, modèles core, authentification, admin shell, frontend, SEO.
3.  **Modules Optionnels** — i18n, onboarding, contenu pédagogique, analytics, sécurité, framework agentic, monétisation Stripe.
4.  **Industrialisation** — Générateur `create-gitsky-project`, services partagés sur un VPS, fleet dashboard, cycle de vie complet d'un projet, intégration GitHub et déploiement automatique, assistant de création.
5.  **Production et Maintenance** — Docker de production (un seul artefact, quels que soient les modules activés), configuration serveur Ubuntu 24.04, sauvegardes et surveillance de flotte, et un guide opérateur de bout en bout : utiliser, déployer, maintenir.

À l'issue de ce parcours, vous disposerez non seulement d'un template exploitable pour lancer un portefeuille de projets, mais surtout d'une discipline opérationnelle pour maintenir la flotte en bonne santé.

***Dr. Nabil MABROUK***
