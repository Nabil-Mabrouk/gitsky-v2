# Module Security : Détection d'Intrusion

## Introduction

Le module `security` de GitSky ajoute un `SecurityMiddleware` qui inspecte chaque requête entrante à la recherche de patterns d'attaque connus, et journalise les événements suspects dans une table `SecurityEvent`. Il est **activé par défaut à partir du tier T1** (`MODULE_SECURITY_MIDDLEWARE=true`) — en T0, la protection est déportée sur le proxy Traefik partagé de la flotte.

## Philosophie : Journaliser, ne pas Bloquer

Le middleware **ne bloque jamais les requêtes** — il journalise uniquement. Cette approche est intentionnelle :

- **Éviter les faux positifs** qui bloqueraient des utilisateurs légitimes.
- **Donner une visibilité complète** sur les menaces sans risquer de casser des flux valides.
- **Déléguer le blocage** à des couches spécialisées (Traefik + `fail2ban`), plus adaptées à la décision temps réel.

Un attaquant qui envoie une charge SQL injection reçoit donc une réponse normale (`200` ou `404` selon la route), mais son comportement est enregistré et visible dans le dashboard admin.

## Types d'Événements Détectés

Le middleware classe les requêtes suspectes en trois catégories :

| Type | Exemples | Sévérité |
|---|---|---|
| `path_scan` | `/.git/`, `/.env`, `/wp-config.php`, `/admin.php` | medium → critical |
| `scanner_detected` | User-Agent de sqlmap, nikto, nmap, nuclei, gobuster | high |
| `injection_attempt` | SQL injection (`' OR 1=1--`), XSS (`<script>`), template injection (`{{7*7}}`) | critical |

Chaque catégorie a ses propres règles de détection dans `app/modules/security/detectors.py`.

## Le Modèle SecurityEvent

Chaque détection produit une entrée SQLAlchemy (voir Chap 4 pour la définition) :

```python
class SecurityEvent(Base):
    __tablename__ = "security_events"
    event_type = Column(String, index=True)
    severity   = Column(String, index=True)
    ip_address = Column(String, index=True)   # IP en clair — attaquants, pas RGPD
    path       = Column(String)
    user_agent = Column(String)
    details    = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

**Note importante :** contrairement au module `analytics` où l'IP est hashée, le module `security` stocke l'IP en clair. La justification RGPD est que les attaquants ne sont pas des utilisateurs légitimes et que la traçabilité prime pour la défense de la plateforme.

## Interface Admin

L'onglet **Sécurité** du dashboard admin (Chap 9) expose :

- **Cartes de synthèse** : total des événements, dernières 24h, critiques, élevés.
- **Top 10 des IPs agressives** : identifier les attaquants récurrents.
- **Journal filtrable** par sévérité, type, IP, période.

```tsx
// Appels API utilisés par l'onglet Sécurité
GET    /api/admin/security/summary?days=7
GET    /api/admin/security/events?severity=critical&page=1&per_page=50
DELETE /api/admin/security/events/old?days=30   // purge périodique
```

## Complémentarité avec Traefik

Le middleware GitSky détecte les attaques applicatives. Le blocage effectif — refuser des connexions au niveau réseau — est délégué à **Traefik + fail2ban** au niveau du VPS partagé :

- Un job périodique lit les événements `SecurityEvent` de sévérité `high` et `critical` de tous les projets.
- Il agrège par IP source sur les 24 dernières heures.
- Les IPs dépassant un seuil (10 événements `critical` ou 50 événements `high`) sont poussées dans une allowlist négative Traefik.
- Traefik refuse ensuite ces IPs sans jamais atteindre les backends GitSky.

Cette architecture à deux niveaux — détection applicative par projet + blocage réseau mutualisé — est décrite en détail au Chap 22 (configuration serveur).

## Purge et Rétention

Les événements de sévérité `low` et `medium` sont purgés au bout de 30 jours. Les événements `high` et `critical` sont conservés 180 jours pour analyse rétrospective. La purge est déclenchée par un cron quotidien.

## Ce que le Middleware ne Fait Pas

Trois choses volontairement absentes :

1. **Pas de blocage** — comme expliqué, c'est le rôle de Traefik.
2. **Pas de notification temps réel** par événement — les alertes agrégées vont dans le fleet dashboard (Chap 19), un email par événement noierait le signal.
3. **Pas de rate limiting** — Traefik gère cela via son propre middleware `RateLimit`. Cette doctrine n'est pas qu'une intention : le générateur émet dans le `docker-compose.yml` de production un routeur Traefik dédié à `/api/auth/login` (5 req/min, burst 10) dès que le module auth est actif — voir Chap 21.
4. **Pas d'inspection des endpoints d'infrastructure** — `/health` (pollé toutes les 60 s par le fleet poller), `/robots.txt` et `/sitemap.xml` sont exclus du middleware, comme du tracking analytics (Chap 13) : journaliser chaque poll noierait les vraies détections et coûterait un commit DB par requête pour rien.

Ces choix maintiennent le module léger et prévisible.

---

*La journalisation défensive étant en place, nous passons dans les chapitres suivants aux modules qui apportent de la valeur métier au projet — framework agentic (Chap 15), monétisation Stripe (Chap 16).*
