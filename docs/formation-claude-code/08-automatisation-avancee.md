# Module 8 — Automatisation avancée : headless, CI/CD, SDK (2 h)

## Objectifs

- Utiliser Claude Code en mode non interactif (headless) dans des scripts
- Intégrer l'agent dans la CI (GitHub Actions) de façon sécurisée
- Mettre en place des tâches planifiées et des boucles de fond
- Savoir quand passer à l'Agent SDK pour construire ses propres agents

## 1. Mode headless : `claude -p`

Le flag `-p` (print) exécute un prompt sans interface interactive — la brique
de base de toute automatisation :

```bash
# Usage simple
claude -p "Liste les TODO du code avec fichier:ligne" 

# Sortie structurée pour un pipeline
claude -p "Analyse ce log et résume les erreurs" \
  --output-format json < error.log

# Contrôle strict des outils (indispensable en automatisation)
claude -p "Corrige les erreurs de lint" \
  --allowedTools "Read,Edit,Bash(npm run lint:*)" \
  --permission-mode acceptEdits

# Limiter le budget d'itérations
claude -p "..." --max-turns 10
```

Règles d'or du headless :

- **Toujours** restreindre les outils (`--allowedTools`) : pas d'humain pour
  refuser une action dangereuse
- Prévoir un budget (`--max-turns`, timeout) : un agent peut boucler
- Sortie `--output-format json` (ou `stream-json`) pour l'intégration ;
  le JSON inclut le résultat, le coût et les métadonnées de session
- Traiter le résultat comme non vérifié : faire suivre d'une étape de
  validation mécanique (tests, lint, diff review)

Cas d'usage : triage de logs, génération de rapports, migrations de masse
(boucler `claude -p` sur une liste de fichiers), pré-traitement d'issues.

## 2. Claude Code dans la CI (GitHub Actions)

L'action officielle `anthropics/claude-code-action` permet de déclencher
l'agent depuis GitHub : mention `@claude` dans une issue ou PR, ou déclencheur
automatique.

Cas d'usage éprouvés :

- **Revue automatique de PR** : l'agent commente chaque PR ouverte
- **Issue → PR** : « @claude corrige cette issue » produit une PR prête à relire
- **Maintenance planifiée** : mise à jour de deps, régénération de docs

Sécurité CI (non négociable) :

- Clé API en secret GitHub, jamais en clair
- Permissions du workflow minimales (`contents: write` seulement si nécessaire)
- L'agent CI ne pousse **jamais** directement sur main : il ouvre des PR
- Attention à la prompt injection via le contenu des issues publiques :
  restreindre les déclencheurs aux membres autorisés

## 3. Tâches planifiées et boucles

- **Tâches planifiées (cloud)** : programmer des agents récurrents
  (« chaque matin, trie les nouvelles issues et propose une priorisation »)
- **Boucles locales** (`/loop` ou script cron autour de `claude -p`) :
  surveillance d'un déploiement, relance de tests flaky, polling d'un état
- **Tâches de fond** : lancer un serveur ou un build en arrière-plan pendant
  que l'agent continue ; l'agent est notifié à la fin

Patron « **usine à PR** » : planificateur → `claude -p` sur une tâche du
backlog → tests en CI → PR → revue humaine. L'humain reste le point de
contrôle final ; l'automatisation produit des **candidats**, pas des merges.

## 4. L'Agent SDK : construire ses propres agents

Quand les besoins dépassent le CLI (produit interne, agent métier, UI dédiée),
l'**Agent SDK** (TypeScript / Python) expose le même harnais que Claude Code :
boucle agentique, outils fichiers/shell, MCP, sous-agents, hooks, permissions.

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Analyse les tickets de support de la semaine et produis une synthèse",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Grep"],
        max_turns=15,
    ),
):
    print(message)
```

À retenir pour la formation : savoir **que ça existe et quand y aller** —
critère : « je veux distribuer un agent à des non-utilisateurs de Claude
Code » ou « je veux des garde-fous programmatiques fins ». La construction
d'agents SDK justifie une formation dédiée.

## 5. TP guidé (50 min)

1. Écrire un script `audit.sh` qui appelle `claude -p` avec outils restreints
   pour produire un rapport JSON des TODO/FIXME du dépôt ; l'exécuter.
2. Enchaîner : un deuxième appel `claude -p` transforme le JSON en rapport
   Markdown priorisé.
3. Sur un dépôt GitHub d'essai : installer `claude-code-action`, ouvrir une
   issue, la faire traiter par `@claude`, relire la PR produite.
4. Discussion : identifier dans le workflow de l'équipe une tâche récurrente
   automatisable et esquisser son pipeline (déclencheur → agent → validation).

## Checklist de validation

- [ ] Je sais lancer `claude -p` avec outils restreints et sortie JSON
- [ ] Je sais pourquoi et comment borner un agent non supervisé (outils, tours, validation aval)
- [ ] Je sais mettre en place une revue de PR automatique en CI de façon sécurisée
- [ ] Je sais positionner l'Agent SDK par rapport au CLI
