# Framework Agentic IA et Services Intelligents

## Introduction au Framework Multi-Agents

Le projet **GitSky** intègre un framework complet d'agents IA permettant de créer des services intelligents automatisés. Ce système multi-agents transforme la plateforme d'apprentissage en un écosystème d'automatisation où différents agents spécialisés collaborent pour exécuter des tâches complexes.

### Philosophie du "GitSky"
Le nom du projet prend tout son sens avec ce framework : l'objectif est de minimiser l'intervention humaine dans les processus répétitifs tout en maximisant la valeur créée par l'intelligence artificielle.

## Architecture du Système Multi-Agents

L'architecture repose sur cinq composants principaux orchestrant la collaboration entre agents :

```text
+--------------------------------------------------+
|          ARCHITECTURE AGENTIC IA                 |
+--------------------------------------------------+
|                                                  |
|  [Service Registry]                              |
|  • Gestion des services disponibles              |
|  • Configuration YAML                            |
|  • Découverte dynamique                          |
|                                                  |
|  [Tool Registry]                                 |
|  • Catalogue d'outils disponibles                |
|  • Catégorisation (web, data, api, etc.)        |
|  • Gestion des permissions                       |
|                                                  |
|  [Agent Orchestrator]                            |
|  • Coordination des workflows multi-étapes       |
|  • Gestion du contexte partagé                  |
|  • Suivi des exécutions                          |
|                                                  |
|  [Memory System]                                 |
|  • Persistance du contexte                      |
|  • Historique des interactions                  |
|  • Apprentissage continu                         |
|                                                  |
|  [Guardrails]                                    |
|  • Validation des entrées/sorties               |
|  • Contrôle de sécurité                         |
|  • Limitations d'usage                           |
+--------------------------------------------------+
```

## Le LLM Proxy Partagé

Un projet GitSky avec `MODULE_AGENTIC=true` n'appelle **jamais directement** les APIs Anthropic ou OpenAI. Tous les appels transitent par un **LLM proxy partagé** hébergé sur le VPS de la flotte, qui apporte quatre bénéfices essentiels :

| Bénéfice | Détail |
|---|---|
| Clé API centralisée | Une seule clé Anthropic (ou OpenAI) sur le VPS, jamais dupliquée dans les projets |
| Quotas par projet | Chaque projet a un budget journalier et mensuel configurable |
| Logs centralisés | Toutes les requêtes LLM sont journalisées avec projet, modèle, tokens, coût |
| Fallback et rotation | Si un modèle est indisponible, le proxy bascule automatiquement vers un modèle équivalent |

L'implémentation recommandée est **LiteLLM** — un proxy open source qui expose une API compatible OpenAI et route vers Anthropic, OpenAI, Groq ou Ollama selon la configuration. L'installation et la configuration côté flotte sont décrites au Chap 18.

Côté projet, l'agent appelle simplement le client :

```python
# app/shared/clients/llm_proxy_client.py
from openai import OpenAI
from app.core.config import get_settings

settings = get_settings()
client = OpenAI(
    base_url=settings.llm_proxy_url,     # http://llm-proxy:4000
    api_key=settings.llm_proxy_token,    # Token de projet, décodé par LiteLLM
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "..."}],
)
```

Le proxy authentifie le projet via son token, décrémente son quota, journalise l'appel, et transmet la requête au fournisseur. En cas de dépassement de quota, il renvoie une erreur `429` que l'agent traite comme un signal de backoff.

## Configuration des Services via YAML

Le framework utilise une configuration déclarative en YAML pour définir les services disponibles. Cette approche permet de modifier le comportement des agents sans toucher au code Python.

### Schéma d'un service

Un service déclare deux choses : des **steps** et des **workflows**.

- Un **step** est une unité de travail nommée, de deux natures possibles :
  - `type: agent` — un appel LLM (modèle + prompt système + température) ;
  - `type: tool` — un appel à un **tool** enregistré (callable Python du registre
    `tools/`), qui encapsule une API externe (génération d'image, d'audio…).
- Un **workflow** est une liste ordonnée de noms de steps. Un même service peut
  en exposer plusieurs (un aperçu court, une génération complète…).
- `async_workflows` liste les workflows **longs**, exécutés en job de fond
  (voir plus bas) ; les autres s'exécutent de façon synchrone.
- `cost_credits` est débité lorsqu'un workflow payant (asynchrone) démarre.

```yaml
# app/modules/agentic/agent_services.yaml
services:
  song_generator:
    enabled: true
    name: "Générateur de chanson"
    description: "Écrit les paroles puis génère l'audio via une API externe"
    category: "music"
    cost_credits: 3
    steps:
      analyze:
        type: agent
        model: "claude-sonnet-5"
        system_prompt: "Résume en 3 lignes l'intention artistique..."
        temperature: 0.5
      lyrics:
        type: agent
        model: "claude-opus-4-8"
        system_prompt: "Écris les paroles fidèles au thème et à la structure..."
        temperature: 0.8
      render:
        type: tool               # appel d'API externe (registre tools/)
        tool: suno_generate
    workflows:
      concept: [analyze, lyrics]         # synchrone : aperçu peu coûteux
      song: [analyze, lyrics, render]    # complet
    async_workflows: [song]              # « song » tourne en job de fond
```

> **IDs de modèles.** Utilisez toujours des identifiants Claude à jour
> (`claude-opus-4-8`, `claude-sonnet-5`, `claude-sonnet-4-6`…). Un ID obsolète
> recopié depuis un exemple casse silencieusement le service en production.

### Services de référence

Le châssis embarque `template_service` (démo minimale d'un step agent). L'exemple
complet — un générateur de chanson à pipeline `analyze → lyrics → style → Suno` —
est livré dans `examples/mezouedai/`, avec `agentic: true` activé dans le bloc
`modules:` de son `config.yaml` (clé courte, sans le préfixe `module_` — Chap 17).

## Modèles de Données pour le Tracking des Exécutions

Pour la traçabilité et l'audit, le module utilise trois tables :

```python
# app/modules/agentic/models.py — extraits
class ServiceExecution(Base):
    """Exécution complète d'un workflow."""
    __tablename__ = "service_executions"
    # user_id, service_slug, workflow_name, status, input_params, result,
    # cost_credits, created_at
    # status : pending -> running -> completed | failed
    # cost_credits : le coût réellement débité, PERSISTÉ — condition du
    # remboursement après un redémarrage qui a tué le job en vol (voir §Jobs).

class ExecutionStep(Base):
    """Une étape du workflow — checkpoint pour l'audit et la reprise."""
    __tablename__ = "execution_steps"
    # execution_id, idx, name, kind (agent|tool), status, output, created_at

class CreditAccount(Base):
    """Portefeuille de crédits : une génération payante débite ici."""
    __tablename__ = "credit_accounts"
    # user_id (unique), balance
```

`ServiceExecution` porte aussi `cost_credits` : le coût réellement débité,
**persisté** (et pas seulement passé en paramètre au job). C'est la condition
du remboursement après coup — voir « Reprise après redémarrage » plus bas.

`ExecutionStep` est la « table steps » : chaque étape exécutée y est persistée,
ce qui rend l'exécution auditable et **reprenable** (un job interrompu peut
repartir de sa dernière étape). Des raffinements ultérieurs (résultats médias
détaillés, préférences utilisateur par service) viendront s'ajouter au besoin.

## Le Moteur d'Orchestration

Le moteur (`app/modules/agentic/engine.py`) exécute un workflow : il enchaîne les
steps déclarés, **passe un `context` accumulé** d'une étape à la suivante (la
sortie de `analyze` nourrit `lyrics`, etc.), trace chaque étape dans
`execution_steps`, et remplit le résultat. C'est le pipeline du GitSky Studio
(Chap 24) généralisé et rendu piloté par YAML.

Deux principes hérités du Studio :

- **Stub par défaut, fail-closed en production.** Sans LLM proxy configuré,
  `call_llm` renvoie une réponse simulée déterministe, et un tool comme
  `suno_generate` renvoie une URL d'exemple. On développe et teste **sans aucune
  clé** ; le réel s'active en fournissant les variables d'environnement (proxy
  LLM, `SUNO_API_KEY`). Garde-fou impératif : si `ENVIRONMENT=production` et
  que la clé manque, le client **lève** au lieu de servir le stub — facturer des
  crédits pour une réponse simulée n'est jamais un fallback acceptable. Ce
  contrat vaut pour toute intégration externe du châssis (Stripe compris,
  Chap 16) et est verrouillé par un test paramétré
  (`test_failclosed_contract.py`).
- **Sortie structurée et tracée.** Le résultat expose la sortie de chaque step,
  plus une clé `output` pratique (le dernier texte d'agent — les paroles, pour un
  aperçu).

## Tâches Longues : Job Asynchrone, sans Broker

La génération média délègue le gros du travail à une **API externe** (Suno) : le
backend ne calcule rien, il **attend**. Inutile donc d'introduire un worker
Celery + broker (qui casserait la densité de la flotte, Chap 2/21). Le pattern
retenu, pour un workflow listé dans `async_workflows` :

1. `execute` débite les crédits, crée l'exécution `pending`, lance le pipeline en
   **tâche de fond in-process** (`asyncio`) et **rend la main immédiatement**
   (submit-and-return) — la connexion HTTP n'est jamais tenue pendant des minutes.
2. Le client **suit** l'avancement via `GET /executions/{id}` (polling) jusqu'à
   `completed`.
3. Si une étape échoue, l'exécution passe `failed` et les crédits sont remboursés.

Les étapes étant **I/O-bound** (appels LLM et API), une simple tâche async suffit :
la durabilité vient de la ligne d'exécution persistée + des checkpoints
`ExecutionStep`. Pour une API réellement asynchrone (soumission puis webhook de
fin), l'exécution passerait par un statut `awaiting_callback` repris par un
endpoint webhook — extension documentée, non nécessaire tant que le tool répond
en ligne.

### Reprise après redémarrage

Le revers du « job in-process » : une tâche `asyncio` ne survit pas à un
redémarrage (deploy, crash, OOM). Sans filet, une exécution resterait
`running` pour toujours et ses crédits, débités, ne seraient jamais rendus. Au
démarrage de l'app (`lifespan`), avant que la moindre tâche ne tourne, toute
exécution encore `pending`/`running` est donc **par définition orpheline** :
`recover_orphan_executions` la passe `failed` et rembourse son `cost_credits`
persisté. C'est précisément pourquoi le coût est stocké sur la ligne
d'exécution et pas seulement dans la variable du job.

### Propriété des exécutions

`GET /executions/{id}` ne renvoie l'exécution qu'à **son propriétaire** (un
admin gardant l'accès pour le support). Pour tout autre utilisateur, la réponse
est `404`, pas `403` : renvoyer `403` confirmerait l'existence de l'id (fuite
par énumération). Le débit de crédits, lui, est un `UPDATE` conditionnel
atomique (`balance >= coût`) et non un lire-puis-écrire — sans quoi deux
requêtes concurrentes pourraient dépenser deux fois le même solde.

## API Agent-Services

Le backend expose une API REST complète pour interagir avec le framework :

### Endpoints Principaux

```python
# app/modules/agentic/router.py

# Catalogue des services (public)
GET  /api/agent-services/services
GET  /api/agent-services/services/{service_slug}

# Solde de crédits de l'utilisateur (auth)
GET  /api/agent-services/credits

# Exécution d'un workflow (auth)
POST /api/agent-services/services/{service_slug}/execute
Body: { "workflow_name": "song", "parameters": {...} }
#  - workflow court           -> synchrone : renvoie `completed` + résultat ;
#  - workflow dans async_workflows -> submit-and-return : renvoie `pending` + id.

# Suivi / polling d'une exécution (auth)
GET  /api/agent-services/executions/{execution_id}
```

Il n'y a pas d'endpoint « liste des outils » : un tool n'est pas exposé seul, il
est un **type de step** référencé par nom depuis le YAML (`type: tool`).

### Exemple d'Exécution

```python
import requests

# Lancer la génération complète (workflow asynchrone)
response = requests.post(
    "https://api.votre-domaine.com/api/agent-services/services/song_generator/execute",
    headers={"Authorization": "Bearer <token>"},
    json={
        "workflow_name": "song",
        "parameters": {"singer": "Slah", "theme": "Exil", "rhythm": "Saltana"},
    },
)
job_id = response.json()["id"]      # statut initial : "pending"

# Puis suivre le job jusqu'à "completed" (polling)
requests.get(
    f"https://api.votre-domaine.com/api/agent-services/executions/{job_id}",
    headers={"Authorization": "Bearer <token>"},
)
```

## Dashboard Agentic Frontend

Le frontend inclut une interface dédiée pour interagir avec les services agents :

### Structure des Composants

```
frontend/src/
├── agent-dashboard/
│   ├── DashboardLayout.tsx      # Layout principal
│   └── ServiceCard.tsx          # Carte de service
├── agent-services/
│   └── (composants spécifiques par service)
└── agent-commons/
    └── (utilitaires partagés)
```

### Fonctionnalités du Dashboard

1. **Catalogue de Services** : Vue grid des services disponibles avec filtrage par catégorie
2. **Exécution en 1-Click** : Lancement des workflows prédéfinis
3. **Historique des Exécutions** : Suivi en temps réel des tâches en cours
4. **Gestion des Préférences** : Personnalisation des paramètres par défaut
5. **Documentation des Outils** : Explorer les capacités disponibles

## Création d'un Nouveau Service Agentic

### Étapes de Développement

1. **Définir le service dans le YAML**
   ```yaml
   services:
     mon_nouveau_service:
       name: "Mon Nouveau Service"
       description: "Description du service"
       category: "custom"
       steps: { ... }          # agents et/ou tools
       workflows: { ... }      # listes ordonnées de noms de steps
   ```

2. **Implémenter la logique métier**
   ```python
   # backend/app/agents/services/mon_service/
   #   ├── __init__.py
   #   └── implémentation des agents
   ```

3. **Créer l'interface frontend**
   ```typescript
   // frontend/src/agent-services/mon-service/
   //   ├── MonServiceInterface.tsx
   //   └── MonServiceResults.tsx
   ```

4. **Tester l'intégration**
   - Vérifier l'apparition dans le catalogue
   - Tester l'exécution du workflow
   - Valider la persistance des résultats

### Bonnes Pratiques

- **Isolation** : Chaque service doit être indépendant
- **Idempotence** : Les exécutions doivent être reproductibles
- **Journalisation** : Logs détaillés pour le debugging
- **Gestion d'erreurs** : Retours d'erreur clairs pour les utilisateurs
- **Performance** : Timeouts appropriés et traitement asynchrone

## Intégration avec les Autres Composants de GitSky

### Authentification et Autorisation
- Les services respectent le système de rôles existant (user, premium, admin)
- Certains services peuvent être réservés aux utilisateurs premium
- Audit via les logs d'activité existants

### Analytics et Monitoring
- Les exécutions sont trackées dans les statistiques admin
- Performance mesurée (temps d'exécution, succès/échec)
- Intégration avec le système de notification

### Gestion des Données
- Persistance des résultats dans PostgreSQL
- Support des fichiers multimédias via le système d'upload existant
- Nettoyage automatique des données temporaires

## Scénarios d'Utilisation Avancés

### Workflows Croisés
Combiner plusieurs services pour des processus complexes :
```yaml
workflow_complexe:
  steps:
    - service: research_agent
      workflow: literature_review
      params: {topic: "AI ethics"}
    - service: news_scraper
      workflow: daily_news_digest
      params: {topics: ["AI ethics news"]}
    - service: custom_service
      workflow: generate_report
      params: {format: "pdf"}
```

### Planification Automatique
Exécution périodique de services via le scheduler intégré :
```python
# Configuration dans le scheduler
schedule.every().day.at("09:00").do(
    execute_service,
    service_slug="news_scraper",
    workflow_name="daily_news_digest"
)
```

### Personnalisation Dynamique
Adaptation des services basée sur le profil utilisateur :
```python
# Utilisation des préférences utilisateur
prefs = get_user_service_preferences(user_id, "news_scraper")
params = merge_params(default_params, prefs.get("custom_params", {}))
```

## Dépannage et Maintenance

### Diagnostic des Problèmes

1. **Vérifier l'état des services**
   ```bash
   # Logs des exécutions
   docker logs gitsky_backend | grep -i "agent\|service"

   # État de la base de données
   psql -U hitl_user -d hitl_db -c "SELECT * FROM service_executions ORDER BY created_at DESC LIMIT 5;"
   ```

2. **Tester manuellement un service**
   ```bash
   curl -X POST http://localhost:8000/api/agent-services/services/template_service/execute \
        -H "Authorization: Bearer <token>" \
        -H "Content-Type: application/json" \
        -d '{"workflow_name": "example_workflow"}'
   ```

3. **Vérifier la configuration YAML**
   ```bash
   python -c "import yaml; data = yaml.safe_load(open('backend/app/config/agent_services.yaml')); print(data.keys())"
   ```

### Maintenance Courante

- **Nettoyage des anciennes exécutions** : Script de rétention configurable
- **Mise à jour des modèles IA** : Rotation des versions d'API
- **Optimisation des performances** : Monitoring des temps d'exécution
- **Sécurité** : Revue régulière des permissions et accès

---

*Ce framework transforme GitSky d'une plateforme statique en un véritable écosystème d'automatisation intelligente. Le prochain chapitre présente le dernier module standard : la monétisation Stripe, qui permet à un projet ayant activé `module_monetization_shop` et/ou `module_monetization_subscription` de générer du revenu récurrent ou de vendre des produits numériques.*