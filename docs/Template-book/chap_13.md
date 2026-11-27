# Mesure d'Audience : Umami, Service Partagé

## Introduction

> **Écart assumé (27 novembre 2026) : le module `analytics` maison est retiré, Umami le remplace.** Ce chapitre décrivait un module `analytics` : un `TrackingMiddleware` dans le backend, une table `visits`, un service GeoIP partagé (base MaxMind GeoLite2) et un onglet Analytics dans l'admin. Il avait un défaut de conception : il tournait dans le **backend**, donc il voyait chaque appel à `api.<domaine>`, mais pas les pages de l'application React (changer de page dans une SPA ne contacte pas l'API). Le « top des URLs » montrait des endpoints (`/api/auth/me`) au lieu de pages, une page à cinq appels comptait pour cinq visites, un visiteur qui lisait la landing sans rien déclencher n'était pas compté, et le temps passé, la provenance ou l'appareil restaient hors de portée.
>
> Umami, branché le 26 novembre, faisait mieux sur tout ce qui compte. Le module a donc été retiré du châssis, avec le service `geoip`, le one-shot `geoipupdate`, son cron mensuel et le compte MaxMind. La migration core `0005` supprime les tables `visits` et `alembic_version_analytics` des bases déjà déployées, seulement si cette table de version existe : une table métier qui s'appellerait aussi `visits` n'est jamais touchée. Un vieux `analytics: true` dans les réponses copier, ou `MODULE_ANALYTICS=true` dans un `.env`, est ignoré sans erreur. Seule perte : le comptage des appels API faits sans navigateur (scripts, robots), sans usage réel.

La mesure d'audience de GitSky est confiée à **Umami**, open source et auto-hébergé comme service partagé de la flotte (Chap 18 §8, `https://stats.0-hitl.com`). Il fournit, pour tous les projets dans un seul tableau de bord : visiteurs uniques, pages vues, durée des visites, taux de rebond, provenance, appareils et carte des pays.

Ce n'est pas un module du catalogue : le composant de suivi fait partie du **châssis**, présent dans tout projet, et reste inerte tant que l'opérateur n'a pas branché le projet.

## Brancher un projet

À l'exécution, sans rebuild :

1. Dans Umami, l'opérateur crée un site pour le projet (nom et domaine exact, sans `www`), puis copie son identifiant (`website id`, un UUID non secret).
2. Il pose deux valeurs dans le `.env.local` du projet, sur le serveur :

   ```bash
   UMAMI_SCRIPT_URL=https://stats.0-hitl.com/s.js
   UMAMI_WEBSITE_ID=4f6c…-…
   ```

3. Le backend les renvoie dans `GET /health`, que le frontend lit déjà pour son nom et ses modules : `"umami": {"script_url": "...", "website_id": "...", "domains": "<domaine du projet>"}`. La clé est **absente** tant qu'elles ne sont pas posées, ou si elles sont douteuses (adresse sans HTTPS, identifiant qui n'est pas un UUID) : ces valeurs finissent dans une balise `<script>`, et le backend préfère n'en servir aucune.
4. Le composant `UmamiTracker` du châssis, monté dans `main.tsx` et non dans `App.tsx` que les projets personnalisent, injecte alors **une seule fois** le script de suivi, avec trois attributs : `data-website-id`, `data-domains` limité au domaine du projet (aucune donnée envoyée depuis un environnement de développement ou une copie du site), et `data-do-not-track="true"` (respect du réglage « Ne pas me suivre » du navigateur). Umami suit lui-même les changements de page de la SPA.

Pas de valeur de build (`VITE_*`) : l'activer ou changer d'identifiant ne demande qu'un redémarrage du backend, et la valeur vit dans `.env.local`, que `copier update` ne réécrit jamais (Chap 23).

❌ Conclure « le suivi ne marche pas » parce que sa propre visite n'apparaît pas.
✅ Vérifier depuis un navigateur sans bloqueur (téléphone en 4G) : les bloqueurs de pub, le réglage « Ne pas me suivre » et la protection anti-pistage stricte excluent la visite, comme ils excluent une partie des vrais visiteurs. Umami sous-estime donc l'audience, comme tout outil de mesure.

## Dans l'admin du projet

L'onglet Analytics a disparu. À sa place, le menu admin affiche un lien **Audience ↗**, qui ouvre le tableau de bord Umami dans un nouvel onglet. L'adresse est l'origine du script de suivi (`https://stats.0-hitl.com`), lue dans `GET /health`. Le lien n'apparaît que lorsque le projet est branché.

## Conformité RGPD

Umami ne pose aucun cookie. Il identifie une visite par une empreinte calculée côté serveur, avec un sel qui change régulièrement, et ne garde pas l'IP. Une mesure d'audience anonyme, à finalité limitée, entre dans l'exemption de consentement prévue par la CNIL. L'opérateur doit le vérifier pour son usage, et mentionner l'outil dans sa politique de confidentialité.

## Rétention et sauvegarde

Les données d'Umami vivent dans la base `umami` du PostgreSQL partagé, sauvegardée chaque nuit par `backup-fleet.sh` avec les autres bases de ce serveur (Chap 18 §8, Chap 23).

---

*La mesure d'audience étant traitée, nous voyons dans le chapitre suivant le module `security` qui journalise les tentatives d'intrusion via un middleware dédié.*
