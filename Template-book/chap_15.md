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

### Exemple de configuration : News Scraper

```yaml
# backend/app/config/agent_services.yaml
services:
  news_scraper:
    enabled: true
    name: "News Scraper"
    description: "Scrape l'actualité et génère des tweets automatiquement"
    category: "content"
    requires_auth: true
    agents:
      - name: "news_fetcher"
        model: "gpt-4"
        tools: ["web_scraper", "rss_reader", "news_api"]
        system_prompt: "You are a news aggregation assistant..."
        temperature: 0.3
      - name: "tweet_writer"
        model: "claude-3-sonnet"
        tools: ["tone_analyzer", "hashtag_generator", "schedule_post"]
        system_prompt: "You are a social media content creator..."
        temperature: 0.7
    workflows:
      - name: "daily_news_digest"
        description: "Récupère les actualités du jour et génère des tweets"
        steps: ["fetch_news", "summarize", "generate_tweets"]
        default_params:
          topics: ["technology", "ai", "startups"]
          num_articles: 5
          language: "fr"
```

### Services Pré-configurés

Le framework inclut trois services prêts à l'emploi :

1. **News Scraper** : Surveillance d'actualités et génération de contenu social
2. **Research Assistant** : Recherche académique et rédaction de rapports
3. **Crypto Analyst** : Analyse de marchés crypto et génération de rapports multimédias

## Modèles de Données pour le Tracking des Exécutions

Pour assurer la traçabilité et l'audit, le framework utilise quatre tables dédiées :

```python
# backend/app/models.py - Extraits
class ServiceExecution(Base):
    """Exécution complète d'un service."""
    __tablename__ = "service_executions"
    # Champs : user_id, service_slug, workflow_name, status, input_params, result

class ServiceExecutionStep(Base):
    """Étape individuelle dans l'exécution."""
    __tablename__ = "service_execution_steps"
    # Champs : execution_id, step_id, agent_name, input_data, output_data, status

class ServiceResult(Base):
    """Résultats détaillés (fichiers, médias, données)."""
    __tablename__ = "service_results"
    # Champs : execution_id, result_type, content, file_path, metadata

class UserServicePreference(Base):
    """Préférences utilisateur par service."""
    __tablename__ = "user_service_preferences"
    # Champs : user_id, service_slug, preferences, is_favorite, usage_count
```

## API Agent-Services

Le backend expose une API REST complète pour interagir avec le framework :

### Endpoints Principaux

```python
# backend/app/routers/agent_services.py

# Liste des services disponibles
GET /api/agent-services/services

# Détails d'un service spécifique
GET /api/agent-services/services/{service_slug}

# Exécution d'un service
POST /api/agent-services/services/{service_slug}/execute
Body: { "workflow_name": "daily_news_digest", "parameters": {...} }

# Suivi des exécutions
GET /api/agent-services/executions/{execution_id}

# Liste des outils disponibles
GET /api/agent-services/tools
```

### Exemple d'Exécution

```python
import requests

# Exécuter le service News Scraper
response = requests.post(
    "https://api.votre-domaine.com/api/agent-services/services/news_scraper/execute",
    headers={"Authorization": "Bearer <token>"},
    json={
        "workflow_name": "daily_news_digest",
        "parameters": {
            "topics": ["artificial intelligence", "machine learning"],
            "num_articles": 10,
            "language": "en"
        }
    }
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
       agents: [...]
       workflows: [...]
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

*Ce framework transforme GitSky d'une plateforme statique en un véritable écosystème d'automatisation intelligente. Le prochain chapitre présente le dernier module standard : la monétisation Stripe, qui permet à un projet en tier T2 de générer du revenu récurrent ou de vendre des produits numériques.*