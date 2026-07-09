# Les Trois Tiers de GitSky : T0, T1, T2

## Introduction

GitSky n'est pas destiné à un projet unique. Il est conçu comme un **template industriel** capable de porter un grand nombre de projets à des stades de maturité très différents : du test de demande à la webapp en production avec revenus récurrents. Un template mono-taille échoue toujours d'un côté ou de l'autre — surdimensionné pour tester une idée, sous-dimensionné pour porter un produit validé.

La solution retenue est un système à **trois tiers**, activables via un système de feature flags. Un même code base, trois profils : **T0** (Landing), **T1** (MVP lite), **T2** (SaaS complet). Chaque projet naît en T0, monte de tier uniquement s'il fournit un signal mesurable, et est arrêté sinon.

## 1. Le Paradoxe de la Startup Factory

Générer des idées coûte peu. Les valider coûte cher. Les développer coûte encore plus. Cette asymétrie impose une discipline :

- **Beaucoup de tests légers** en amont, pour laisser émerger le signal.
- **Un investissement croissant** à mesure que le signal se confirme.
- **Un mécanisme de kill** systématique pour libérer les ressources des projets sans signal.

Un template GitSky déployé en pleine version pour tester chaque idée serait un gaspillage de ressources (RAM, disque, temps humain) et un frein à la vitesse — chaque instance prendrait des heures à mettre en place. Inversement, une simple page HTML statique ne suffirait plus une fois qu'un projet commence à avoir de vrais utilisateurs.

Les trois tiers réconcilient ces deux exigences dans un seul template.

## 2. Les Trois Tiers en Synthèse

| Tier | Cas d'usage | Temps de déploiement | Empreinte RAM | Coût mensuel indicatif |
|---|---|---|---|---|
| **T0 — Landing** | Test de demande sur une idée non validée | < 5 min | ~50 Mo | ~0,20 €/mois |
| **T1 — MVP lite** | Produit minimal pour valider un usage réel | < 2 h | ~200 Mo | ~2 €/mois |
| **T2 — SaaS complet** | Produit avec traction, monétisation active | 1 à 3 jours | ~700 Mo | ~7 €/mois + coûts LLM/Stripe à l'usage |

Ces coûts sont calibrés sur un **VPS mutualisé de 8 Go de RAM à 20 €/mois**, hébergeant plusieurs projets simultanément derrière un unique Traefik. Sur cette base :

- Le VPS peut porter **100+ instances T0** sans saturation.
- Il peut porter **10 à 20 instances T1** avec confort.
- Il peut porter **3 à 5 instances T2** en production.

Cette économie d'échelle est la raison d'être du choix d'un VPS partagé plutôt que d'un hébergement scale-to-zero externe. Le prix marginal d'un T0 supplémentaire est proche de zéro tant que le VPS n'est pas saturé.

## 3. Ce qui est Activé à Chaque Tier

Chaque module de GitSky peut être activé ou désactivé indépendamment via une variable d'environnement `MODULE_*`. Les trois tiers ne sont que des **profils par défaut** de ces flags — un projet peut toujours surcharger un flag pour un besoin spécifique.

| Module | T0 | T1 | T2 |
|---|:---:|:---:|:---:|
| Authentication (JWT + refresh) | ❌ | ✅ | ✅ |
| Admin shell | ❌ | ❌ | ✅ |
| Internationalisation (i18n FR/EN) | ❌ | ❌ | ✅ |
| Analytics GeoIP + world map | via collector partagé | ✅ | ✅ |
| Onboarding dynamique | ❌ | ❌ | ✅ |
| Content system (tutorials/lessons) | ❌ | ❌ | selon projet |
| Framework agentic IA | ❌ | optionnel | ✅ |
| Monétisation boutique (Stripe) | ❌ | ❌ | ✅ |
| Monétisation abonnements | ❌ | ❌ | ✅ |
| SecurityMiddleware | via proxy Traefik | ✅ | ✅ |
| SEO dynamique | ✅ | ✅ | ✅ |

Le principe : **un module désactivé ne charge aucune route, aucun modèle SQL, aucune migration Alembic**. L'empreinte mémoire d'un T0 est donc effectivement minimale, non pas parce que le code manque, mais parce que le code inutile est court-circuité au démarrage.

Le fichier `.env` d'un T0 typique :

```env
GITSKY_TIER=t0
PROJECT_NAME=pain-scraper
VITE_API_URL=https://pain-scraper.mystudio.com
# Tous les MODULE_* sont désactivés par défaut du profil T0
```

Un T2 avec agentic activé :

```env
GITSKY_TIER=t2
PROJECT_NAME=code-reviewer-pro
MODULE_AGENTIC=true                       # surcharge du profil T2 si besoin
MODULE_MONETIZATION_SUBSCRIPTION=true
STRIPE_SECRET_KEY=sk_live_xxx
ANTHROPIC_API_KEY=sk-ant-xxx
```

## 4. Critères de Promotion entre Tiers

Un projet ne monte pas de tier par décision arbitraire. Chaque promotion est **conditionnée à un signal numérique mesurable**, collecté par le landing-collector partagé ou le tracking analytics du projet.

### T0 → T1 : Le Signal de Demande

Un projet T0 est promu en T1 lorsqu'il satisfait **au moins une** des conditions suivantes, mesurées sur les 21 premiers jours d'exposition :

| Signal | Seuil |
|---|---|
| Conversion visiteurs → captures email | ≥ 3 % sur trafic qualifié (≥ 500 visites) |
| Nombre absolu d'inscriptions | ≥ 30 emails collectés |
| Retours qualitatifs actionables | ≥ 3 réponses à un email de suivi décrivant un besoin précis |

Le seuil de 3 % est calibré sur des benchmarks courants de landings B2B — en dessous, la traction est probablement fortuite. Le seuil de 500 visites élimine les projets qui n'ont pas encore été testés en conditions réelles.

### T1 → T2 : Le Signal d'Usage et de Volonté de Payer

Un projet T1 est promu en T2 lorsqu'il satisfait **toutes** les conditions suivantes après 30 jours d'exposition :

| Signal | Seuil |
|---|---|
| Utilisateurs actifs (usage ≥ 3 fois par semaine) | ≥ 10 |
| Rétention D7 (utilisateurs revenant à J+7) | ≥ 30 % |
| Signal de volonté de payer | ≥ 1 paiement réel OU ≥ 3 déclarations explicites |

La rétention D7 est le meilleur prédicteur simple de la survie d'un produit. En dessous de 30 %, ajouter de la monétisation ne convertira personne — le problème n'est pas le paiement, c'est l'usage.

### La Règle Inverse : Ne Jamais Naître en T2

L'anti-pattern le plus coûteux est de démarrer directement en T2, en pariant qu'une idée « évidente » réussira. Le coût :

- **Semaines de développement** avant le moindre test utilisateur.
- **Opportunité perdue** sur les autres idées non testées pendant ce temps.
- **Attachement émotionnel** au produit fini, qui rend le kill quasi impossible.

**Règle absolue : chaque projet naît en T0. Aucune exception.**

## 5. Comment Monter un Projet de Tier

La montée d'un tier n'est jamais une réécriture — c'est une **activation de modules** et une migration de données incrémentale.

### T0 → T1

1. **Mise à jour du `.env`** : `GITSKY_TIER=t1`, activation de `MODULE_AUTH` et des modules métier propres au projet.
2. **Migration des leads en users** : les emails collectés en T0 dans le landing-collector partagé sont importés dans la table `users` du projet avec `role=waitlist`.
3. **Alembic upgrade** : les tables nécessaires aux modules activés (users, sessions, tables métier) sont créées.
4. **Rebuild et déploiement** : `docker compose build && docker compose up -d`. Le sous-domaine reste identique (`pain-scraper.mystudio.com`).
5. **Notification** : un email est envoyé aux leads migrés pour les inviter à créer leur compte.

### T1 → T2

1. **Mise à jour du `.env`** : `GITSKY_TIER=t2`, activation de `MODULE_ADMIN`, `MODULE_I18N`, `MODULE_MONETIZATION_*` selon la stratégie de revenus.
2. **Configuration Stripe** : produits ou abonnements créés dans le dashboard Stripe partagé du studio.
3. **Domaine dédié (optionnel)** : passage de `pain-scraper.mystudio.com` à un domaine premier (`pain-scraper.com`), avec ajustement des labels Traefik.
4. **Alembic upgrade** : tables `products`, `purchases`, `subscriptions`, `security_events`, etc.
5. **Contenu i18n** : rédaction des traductions EN si le marché cible n'est pas exclusivement francophone.
6. **Communication** : email d'annonce aux utilisateurs T1 existants, éventuellement avec une offre early adopters.

Chaque étape est **réversible** tant qu'on ne détruit pas de données — un simple retour au `.env` précédent suivi d'un Alembic downgrade suffit à revenir au tier antérieur.

## 6. Le Kill Mechanism : Arrêter à Temps

Un projet qui ne remplit pas ses critères de promotion doit être arrêté. Sans ce mécanisme, la flotte se remplit de zombies qui consomment ressources et attention sans jamais rembourser leur coût.

### Règles de Kill Automatique

Un cron quotidien (`kill_check`) évalue chaque projet et marque les candidats au shutdown :

| Tier | Condition de kill | Coût cumulé maximal |
|---|---|---|
| **T0** | Aucun des signaux du §4 atteint à J+21 | 100 € en trafic + infra |
| **T1** | Rétention D7 < 15 % à J+30 OU aucun signal WTP à J+45 | 500 € en cumul |
| **T2** | Churn mensuel > 20 % sur 3 mois consécutifs OU MRR < 100 € à J+90 | évaluation manuelle |

Les seuils T0 et T1 déclenchent un shutdown automatique. Le seuil T2 déclenche une **alerte au fleet dashboard** — la décision reste humaine à ce niveau, car un produit T2 peut avoir des raisons contextuelles de sous-performer (saisonnalité, changement d'algorithme SEO, panne prolongée).

### Procédure de Shutdown

Le shutdown n'est jamais brutal :

1. **J-2 avant kill** : email au propriétaire du projet + entrée `pending_kill` dans le fleet dashboard.
2. **J-0 kill** : `docker compose down`, retrait des labels Traefik, désactivation des enregistrements DNS pointant vers le sous-domaine.
3. **Sauvegarde froide** : dump PostgreSQL compressé archivé sur S3 ou Backblaze pendant 90 jours (permet une réactivation si signal tardif).
4. **Libération des ressources** : le sous-domaine retourne dans le pool disponible, la DB est marquée `archived`.
5. **Journalisation** : le projet est marqué `killed` dans le fleet dashboard avec date, tier atteint, raison, coût total.

### Ce que le Kill n'Est Pas

Un kill n'est pas un échec du projet — c'est le **succès du protocole**. Sur 30 idées testées, on s'attend statistiquement à en tuer 25. Les 5 restantes financent les 25 par leur montée en T1/T2. Refuser de tuer, c'est refuser de valider le portefeuille de projets.

## 7. Anti-Patterns à Éviter

Trois erreurs récurrentes que le système de tiers rend particulièrement coûteuses :

**Démarrer en T2 « parce que je connais mon marché »**
Les cimetières de startups sont pleins d'idées « évidentes ». Le T0 coûte quelques euros — la conviction subjective ne coûte rien de moins qu'à celui qui l'a réellement testée.

**Monter en T2 sur un signal T1 flou**
Si les seuils T1 → T2 ne sont pas franchement atteints, ajouter de l'admin, de l'i18n et de la monétisation ne créera pas la demande manquante — cela consommera du temps qui aurait servi à tester d'autres idées.

**Refuser de tuer un projet attaché**
Un projet dans lequel on a investi du temps devient émotionnellement coûteux à arrêter. Le kill mechanism automatique protège l'opérateur de sa propre inertie.

## Checklist du Chapitre

- [ ] Je démarre systématiquement chaque nouveau projet en T0
- [ ] J'ai des critères numériques explicites pour la promotion T0 → T1 → T2
- [ ] Je sais quels modules s'activent à chaque tier et pourquoi
- [ ] Le mécanisme de kill est armé et testé sur mon environnement
- [ ] Je préserve les données d'un projet tué pendant 90 jours avant destruction définitive
- [ ] Je considère un kill comme un succès du protocole, pas comme un échec

---

*Ce système de tiers structure tout le reste de l'ouvrage : la Partie II décrit le core présent à tous les tiers, la Partie III les modules optionnels que chaque tier active, et la Partie IV le générateur et la flotte qui rendent l'ensemble opérationnel à grande échelle. Dans le prochain chapitre, nous détaillons l'initialisation du backend FastAPI, socle commun aux trois tiers.*
