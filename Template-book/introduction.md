# Introduction : GitSky, un Template Industriel pour la Startup Factory {.unnumbered}

Cet ouvrage ne décrit pas la construction d'une seule webapp. Il pose les fondations d'un **template industriel** — GitSky — capable de porter simultanément un grand nombre de projets à des stades de maturité très différents, du test rapide d'une idée non validée jusqu'à la webapp en production avec revenus récurrents.

**GitSky, un Template et une Discipline**

GitSky n'est pas un produit fini, c'est un système :

*   **Un template paramétrable** basé sur FastAPI, React et PostgreSQL, capable de générer un projet prêt à démarrer via un générateur automatisé (`create-gitsky-project`).
*   **Un système à trois tiers** — T0 (Landing), T1 (MVP lite), T2 (SaaS complet) — pour ajuster la complexité et le coût de chaque projet à son stade de validation.
*   **Une flotte industrielle** hébergée sur un unique VPS mutualisé, avec services partagés (Traefik, PostgreSQL, LLM proxy, landing-collector) et un fleet dashboard central pour piloter l'ensemble.
*   **Une discipline de portefeuille** avec critères de promotion numériques et mécanisme de kill automatique, pour concentrer les ressources sur les projets qui prouvent leur valeur.

L'objectif est de compresser le temps entre l'idée et la webapp déployée, de plusieurs semaines à quelques heures, tout en préservant la qualité d'une architecture professionnelle.

**Architecture Cible : un Core Léger, des Modules Optionnels**

Au cœur de GitSky se trouve une architecture stricte en couches :

*   **GitSky-core** : Docker infra, FastAPI shell, gestion des utilisateurs et rôles, authentification JWT, admin shell, SEO de base. Présent à tous les tiers.
*   **GitSky-modules** : onboarding dynamique, système de contenu (tutoriaux/leçons), analytics GeoIP, security middleware, framework agentic IA, i18n, monétisation Stripe. Chacun activable indépendamment via variable d'environnement.
*   **GitSky-app** : la couche applicative métier propre à chaque projet (modèles de données, endpoints, UI spécifiques).

Le stack technique est unifié à tous les tiers :

*   **Backend FastAPI** avec SQLAlchemy asynchrone et Pydantic Settings.
*   **Frontend React 19 + Vite + Tailwind 4** pour la vitesse et la réactivité.
*   **PostgreSQL 16** comme socle de persistance, avec une base par projet pour une isolation nette.
*   **Docker Compose** pour l'orchestration, **Traefik partagé** pour le routage HTTPS multi-projets.
*   **Framework agentic** activable pour les projets nécessitant des services IA.

Chaque projet ne paie que le coût des modules qu'il active — un T0 en RAM tient dans quelques dizaines de mégaoctets, un T2 monte à quelques centaines.

**Feuille de Route de l'Ouvrage**

Ce livre est structuré en cinq parties :

1.  **Fondations et Philosophie** — Architecture conteneurisée multi-projets, système à trois tiers.
2.  **GitSky-core** — Ce qui est présent à tous les tiers : initialisation FastAPI, modèles core, authentification, admin shell, frontend, SEO.
3.  **Modules Optionnels** — i18n, onboarding, contenu pédagogique, analytics, sécurité, framework agentic, monétisation Stripe.
4.  **Industrialisation** — Générateur `create-gitsky-project`, services partagés sur un VPS, fleet dashboard, cycle de vie complet d'un projet.
5.  **Production et Maintenance** — Docker prod par tier, configuration serveur Ubuntu 24.04, sauvegardes et surveillance de flotte.

À l'issue de ce parcours, vous disposerez non seulement d'un template exploitable pour lancer un portefeuille de projets, mais surtout d'une discipline opérationnelle pour maintenir la flotte en bonne santé.

***Dr. Nabil MABROUK***
