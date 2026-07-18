# Cycle de Vie d'un Projet dans la Flotte

## Introduction

Ce chapitre formalise le cycle de vie complet d'un projet GitSky, depuis l'idée jusqu'à son archivage (kill) ou son émancipation (succès). Il rassemble sous une même chronologie les concepts distribués dans les chapitres précédents — tiers (Chap 2), création de module métier (Chap 11), kill mechanism (Chap 2), promotion de tier (Chap 2), fleet dashboard (Chap 19).

L'objectif est double : donner à l'opérateur un playbook clair, et documenter le contrat de la flotte pour tout collaborateur qui interviendrait sur un projet.

## Vue d'Ensemble : Cinq Stages

```text
+----------+--------+---------+---------+-----------+
| Harvest  | T0     | T1      | T2      | Émancip.  |
| (idée)   | Landing| MVP     | SaaS    | ou Kill   |
+----------+--------+---------+---------+-----------+
   |         |        |         |         |
   0€        ~20€    ~200€     ~1000€    variable
   ~1 jour   14-21j  30-45j    variable  final
```

Chaque stage a ses **entrées** (ce qu'on collecte), ses **livrables** (ce qu'on produit), ses **critères de sortie** (ce qui déclenche le passage au suivant), et son **coût plafonné** (au-delà, kill automatique).

## Stage 0 — Harvest

Précède l'existence du projet dans GitSky.

**Entrées :** sources de signal (Reddit, G2 reviews, HackerNews threads, job boards).

**Activités :**

- Extraction de patterns de douleur sur une source (via LLM proxy, script custom).
- Clustering des signaux similaires en "idée".
- Scoring initial (volume de signal, prix des solutions adjacentes, gap concurrentiel).

**Livrables :** un `config.yaml` prêt pour le générateur, avec le nom du projet, le tier T0, et le copy de landing rédigé dans la langue verbatim de la source.

**Critère de sortie :** l'idée passe le score minimum. Coût de ce stage : ~0 € hors temps opérateur.

## Stage 1 — Tier T0 (Landing)

Le projet naît. Le générateur produit un T0 en < 5 minutes.

**Entrées :** `config.yaml`, actifs de branding.

**Activités :**

- Déploiement automatique via `copier copy && docker compose up -d`.
- Trafic dirigé vers la landing depuis la source d'origine du signal (post Reddit, ads ciblées, SEO sur les queries identifiées).
- Collecte des emails via le landing collector partagé.

**Livrables :**

- Une landing live à `<nom>.mystudio.com`.
- Une entrée dans le fleet dashboard.
- Des métriques de conversion suivies quotidiennement.

**Critère de sortie (T0 → T1) :** l'un des trois signaux du Chap 2 — conversion ≥ 3 % sur 500 visites, ou ≥ 30 signups, ou ≥ 3 retours qualitatifs — sur 21 jours.

**Critère de kill T0 :** aucun signal atteint à J+21 OU coût cumulé > 100 € en trafic et infra. Kill automatique.

## Stage 2 — Tier T1 (MVP Lite)

Le projet a un signal de demande. Il devient un produit utilisable.

**Activités opérateur :**

- Éditer le `config.yaml` : `tier: t1`, activer les modules nécessaires (auth, éventuellement onboarding).
- Ajouter les `data_models` du domaine métier.
- Lancer `copier update`.
- Redéployer.
- Migrer les leads T0 vers `users` (rôle waitlist), envoyer les invitations.

**Activités développeur :**

- Implémenter la feature métier core dans `app/domain/`.
- Ajouter les composants React nécessaires.
- Rédiger le contenu d'accueil et la fonctionnalité minimale.

**Livrables :** MVP fonctionnel utilisable par les leads T0 devenus users.

**Critère de sortie (T1 → T2) :** ≥ 10 actifs (usage ≥ 3 fois par semaine), rétention D7 ≥ 30 %, ≥ 1 paiement réel OU ≥ 3 déclarations WTP explicites — voir Chap 2.

**Critère de kill T1 :** rétention D7 < 15 % à J+30 OU aucun signal WTP à J+45 OU coût cumulé > 500 €. Kill automatique.

## Stage 3 — Tier T2 (SaaS Complet)

Le projet a de la traction. Il devient un produit commercialisable.

**Activités opérateur :**

- Éditer le `config.yaml` : `tier: t2`, activer `admin`, `i18n`, `monetization_*`.
- Configurer Stripe (produits ou plans d'abonnement) dans le compte partagé, avec la métadonnée `project_name` (voir Chap 16).
- Passer sur un domaine dédié (`<nom>.com`) si le projet mérite l'investissement DNS.
- Rédiger les traductions EN si le marché cible est international.

**Activités développeur :**

- Compléter les surfaces admin.
- Ajouter les modules métier avancés.
- Optimiser le SEO et la conversion.

**Livrables :** SaaS opérationnel avec revenus mesurés.

**Critère de kill T2 :** churn > 20 %/mois sur 3 mois consécutifs OU MRR < 100 € à J+90 — évaluation manuelle par l'opérateur, alerte au fleet dashboard.

## Migration Sous-Domaine → Domaine Premier

Quand un projet monte en T2 et mérite son propre domaine (`pain-scraper.com` au lieu de `pain-scraper.mystudio.com`), la migration doit préserver le SEO déjà acquis et ne pas casser les liens partagés par des utilisateurs. Voici la procédure en quatre étapes.

### Étape 1 — Provisionnement du Nouveau Domaine (J-7)

- Achat du domaine.
- Configuration DNS chez le registrar :
  - Enregistrement `A` pointant vers l'IP du VPS.
  - Enregistrements `MX` vers le SMTP relay partagé si le projet reçoit des emails.
  - Enregistrement `CAA` autorisant Let's Encrypt.
- Ajout des labels Traefik du projet pour accepter les **deux domaines simultanément**.
- Génération du certificat pour le nouveau domaine (Let's Encrypt HTTP-01 standard — pas DNS-01 puisque ce n'est pas un wildcard).

À ce stade, les deux URLs répondent — l'ancienne reste primaire, la nouvelle est en accueil.

### Étape 2 — Préparation SEO (J-4)

- Email aux utilisateurs annonçant le nouveau domaine (motif : identité de marque forte).
- Mise à jour du `canonical` de toutes les pages pour pointer vers le **nouveau** domaine (via composant SEO du Chap 10).
- Mise à jour du `sitemap.xml` pour lister les URLs sous le nouveau domaine.
- Soumission du sitemap à Google Search Console pour le nouveau domaine, revendication de propriété.

Le `canonical` pointant vers le nouveau signale à Google la préférence sans encore casser l'ancien.

### Étape 3 — Bascule Primaire (J-0)

- Inversion du `PROJECT_DOMAIN` dans le `.env` : le nouveau domaine devient primaire.
- L'ancien sous-domaine renvoie désormais une **redirection 301** vers le nouveau, gérée par un middleware Traefik :

```yaml
labels:
  - "traefik.http.middlewares.redirect-old.redirectregex.regex=^https://pain-scraper.mystudio.com/(.*)"
  - "traefik.http.middlewares.redirect-old.redirectregex.replacement=https://pain-scraper.com/$${1}"
  - "traefik.http.middlewares.redirect-old.redirectregex.permanent=true"
```

- Envoi d'un email de confirmation aux utilisateurs.

### Étape 4 — Suivi (J+30)

- Vérification que Google indexe le nouveau domaine et déprécie l'ancien.
- Vérification du trafic organique : la baisse initiale (~30-40 %) doit se résorber en 6-8 semaines.
- L'ancien sous-domaine reste actif **en redirection au moins 12 mois** — jamais supprimé tant que des liens externes peuvent exister.

### Anti-Patterns à Éviter

- **Suppression brutale du sous-domaine** — casse tous les liens externes accumulés, perte SEO définitive.
- **Absence de redirection 301** — Google traite le nouveau domaine comme un site vierge, perte de tout le PageRank.
- **Migration pendant une campagne active** — la baisse SEO temporaire tue le rendement des campagnes en cours.

### Timing Recommandé

Idéal : juste après validation T1 → T2, **avant** le lancement d'une grosse acquisition (Product Hunt, article invité, campagne payante) qui ferait converger du trafic vers l'ancien domaine.

## Stage 4 — Émancipation ou Consolidation

Un projet qui atteint une taille significative peut suivre plusieurs voies.

### Option A — Rester dans la flotte

Le projet continue à bénéficier des services partagés. C'est le cas par défaut jusqu'à ce que le projet dépasse ~1 000 € de MRR.

### Option B — Émancipation

Au-delà de ce seuil, l'opérateur peut décider de sortir le projet de la flotte partagée :

- Migration vers un compte Stripe propre (rattachement à une entité juridique dédiée).
- Migration vers un VPS dédié (ou cluster).
- Extraction de la base PostgreSQL du service partagé vers une base dédiée.
- Retrait des labels Traefik du proxy partagé.

Cette procédure est décrite dans le playbook `docs/emancipation.md` du repo `startup-factory-configs/`. Elle est réversible en cas de sur-anticipation.

### Option C — Vente ou acqui-hire

Un projet à traction significative peut être vendu. La flotte étant conçue avec isolation stricte (une DB, un domaine, un compte Stripe metadata-namespacé), cette extraction est mécanique.

## Logique d'Évaluation du `kill_check`

Le cron `kill_check` est le mécanisme le plus critique de la flotte — il exécute automatiquement les kills sur des projets sans surveillance humaine. Sa logique doit être auditable et son évaluation reproductible.

### Fréquence et Fenêtre d'Exécution

- Exécution quotidienne à **03:00 UTC** (après backup à 02:00, pour préserver la dernière sauvegarde d'un projet sur le point d'être tué).
- Fenêtre d'évaluation glissante : 21 jours pour T0, 30 jours pour T1, 90 jours pour T2.
- Ancre temporelle : `first_deployed_at` du projet (colonne dans `fleet_lifecycle_events`).

### Données Collectées par Tier

Pour chaque projet actif, le cron collecte :

**T0 (Landing) :**

| Variable | Source | Description |
|---|---|---|
| `signup_count` | `leads` (landing collector) | Nombre de leads collectés depuis `first_deployed_at` |
| `visit_count` | `leads` + tracking landing | Visites totales |
| `qualitative_feedback_count` | `leads.feedback` | Réponses à l'email de suivi |
| `total_cost` | `fleet_manual_costs` + amortissement infra | Trafic + infra + LLM |
| `days_since_deploy` | `now() - first_deployed_at` | Jours écoulés |

**T1 (MVP Lite) :**

| Variable | Source | Description |
|---|---|---|
| `active_users_last_7d` | table `sessions` du projet | Users avec ≥ 3 sessions sur 7 j |
| `retention_d7` | cohortes `users` × `visits` | Cohorte à J+7 / cohorte initiale |
| `paid_users_count` | `subscriptions` + `purchases` | Abonnements actifs ou achats réels |
| `wtp_declarations` | `feedbacks.wtp` | Réponses positives à un email « would you pay for X » |
| `total_cost` | idem T0 étendu | Trafic + infra + LLM cumulés |

**T2 (SaaS Complet) :**

| Variable | Source | Description |
|---|---|---|
| `mrr` | `subscriptions.status IN (active, trialing)` | SUM `Subscription.plan_price` |
| `churn_rate_3m` | Delta `subscriptions.cancelled` / initial | Taux de churn cumulé 90 jours |
| `days_below_mrr_threshold` | Historique MRR quotidien | Jours consécutifs avec MRR < 100 € |

### Règles d'Évaluation

Chaque tier évalue un verdict parmi `healthy | pending_kill | kill_now | manual_review`.

**T0 :**

```python
def evaluate_t0(m):
    if m.days_since_deploy < 19:
        return "healthy"
    if (m.signup_count >= 30
        or (m.visit_count >= 500 and m.conversion_rate >= 0.03)
        or m.qualitative_feedback_count >= 3):
        return "healthy"   # promotion T1 recommandée à l'opérateur
    if m.days_since_deploy >= 21 or m.total_cost >= 100:
        return "kill_now"
    return "pending_kill"  # zone J+19 à J+21 sans signal
```

**T1 :**

```python
def evaluate_t1(m):
    if m.days_since_deploy < 30:
        return "healthy"
    if (m.retention_d7 >= 0.30
        and (m.paid_users_count >= 1 or m.wtp_declarations >= 3)
        and m.active_users_last_7d >= 10):
        return "healthy"   # promotion T2 recommandée
    if m.retention_d7 < 0.15 and m.days_since_deploy >= 30:
        return "kill_now"
    if m.days_since_deploy >= 45 and m.wtp_declarations == 0:
        return "kill_now"
    if m.total_cost >= 500:
        return "kill_now"
    return "pending_kill"
```

**T2 :**

```python
def evaluate_t2(m):
    if (m.churn_rate_3m > 0.20 and m.days_below_mrr_threshold >= 90):
        return "manual_review"
    if m.days_below_mrr_threshold >= 90 and m.mrr < 100:
        return "manual_review"
    return "healthy"
```

**T2 ne se kill jamais automatiquement.** Les projets à ce tier ont des utilisateurs payants et méritent une évaluation humaine avant tout retrait.

### Pipeline Post-Verdict

| Verdict | Action |
|---|---|
| `healthy` | Rien |
| `pending_kill` | Email opérateur + entrée dashboard, ré-évaluation à J+2 |
| `kill_now` | Procédure de shutdown déclenchée (voir section suivante) |
| `manual_review` | Alerte permanente au dashboard, aucune action automatique |

### Idempotence et Sécurité

- Le cron est idempotent : ré-exécuter deux fois de suite ne double pas les kills (verrou pris sur `fleet_lifecycle_events`).
- Un kill est réversible pendant 90 jours (sauvegarde froide conservée).
- L'opérateur peut annuler un `pending_kill` depuis le dashboard sans avoir à modifier le code.
- Chaque évaluation est journalisée : reproductibilité des verdicts sur demande d'audit.

## Kill Mechanism : le Détail Opérationnel

Le kill mechanism a été défini au Chap 2. Voici son implémentation opérationnelle par le cron `kill_check`.

```bash
# services/kill-check.sh — extrait
#!/bin/bash
# Lancé quotidiennement à 03:00 UTC par le fleet dashboard.

for project in $(curl -s $FLEET/api/projects?status=active | jq -r '.[].name'); do
    metrics=$(curl -s $FLEET/api/projects/$project/metrics)
    verdict=$(echo "$metrics" | python3 evaluate_kill.py)

    case "$verdict" in
        "kill_now")
            curl -X POST $FLEET/api/projects/$project/kill
            ;;
        "pending_kill")
            curl -X POST $FLEET/api/projects/$project/mark-pending-kill
            curl -X POST $FLEET/api/notifications/alert \
                -d "project=$project&type=pending_kill"
            ;;
        "healthy")
            ;;
    esac
done
```

La procédure de kill elle-même, orchestrée par le fleet dashboard :

1. `docker compose down` dans le dossier du projet.
2. Retrait des labels Traefik (rechargement Traefik).
3. Suppression des enregistrements DNS pointant vers le sous-domaine.
4. Dump PostgreSQL compressé archivé sur stockage cold (S3 Glacier ou Backblaze B2 archive).
5. Suppression de la base du service PostgreSQL partagé.
6. Suppression du token LLM proxy du projet.
7. Journalisation dans le fleet dashboard : statut `killed`, date, tier atteint, coût total, raison.

Le sous-domaine est libéré 30 jours après le kill (garde contre le squatting immédiat par un autre projet).

## Reconstitution d'un Projet Killed

Un projet tué peut être ressuscité si un signal tardif émerge — rare mais possible (par exemple un article viral cite la landing archivée) :

1. Extraire le dump PostgreSQL du stockage cold.
2. Regénérer le projet via `copier copy` avec le même `config.yaml` (versionné).
3. Restaurer la base.
4. Redéployer.

Cette procédure prend ~30 minutes. La conservation des dumps pendant 90 jours minimum rend cette option disponible.

## Le Journal de la Flotte

Chaque événement du cycle de vie (naissance, promotion, kill, émancipation) est journalisé dans une table `fleet_lifecycle_events` interrogeable depuis le fleet dashboard. À échéance annuelle, ce journal permet de calculer :

- Taux de survie T0 → T1 → T2.
- Coût moyen par projet à chaque stage.
- ROI global de la flotte.

Ces indicateurs sont la boucle de feedback qui améliore la phase harvest — si le taux de survie T0 est nul, c'est le scoring initial qui est cassé, pas les projets.

---

*Ce chapitre clôt la partie industrialisation. La dernière partie du livre couvre la production et la maintenance : configuration du serveur Ubuntu, sauvegardes de flotte et bonnes pratiques opérationnelles.*
