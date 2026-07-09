# Module Onboarding : Profilage Dynamique

## Introduction

Le module `onboarding` est un moteur d'évaluation par flux JSON qui profile un utilisateur à son inscription (ou lors d'une mise à jour de profil), et lui attribue un label technique et un score exploitables par le reste de l'application.

Activation : `MODULE_ONBOARDING=true` (par défaut en T2, mais peut être activé dès T1 pour les projets où le profilage est un enjeu de conversion).

Contrairement à une inscription classique, l'onboarding transforme un formulaire administratif en **question sur le besoin de l'utilisateur** — ce qui améliore à la fois l'engagement initial et la qualité de la segmentation ensuite.

## Le Flow JSON : Règles Métier sans Code

Le cœur du module est un **moteur de scoring** qui évalue des flows au format JSON. Cette approche permet de modifier les règles sans toucher au code Python — un chargé de produit peut ajuster le questionnaire directement dans le fichier.

```json
// backend/app/modules/onboarding/flows/user_profiling.json — extrait
{
  "questions": [
    { "id": "role",      "label": "Quel est votre rôle ?",       "options": ["dev", "pm", "designer", "other"] },
    { "id": "team_size", "label": "Taille de votre équipe ?",    "options": ["solo", "small", "medium", "large"] },
    { "id": "goal",      "label": "Objectif principal ?",         "options": ["speed", "quality", "learning"] }
  ],
  "scoring": {
    "rules": [
      { "conditions": { "role": "dev", "team_size": "solo" }, "result": { "profile": "solo_builder", "score": 80 } },
      { "conditions": { "role": "pm",  "goal": "quality" },   "result": { "profile": "quality_pm",   "score": 70 } }
    ],
    "default": { "profile": "explorer", "score": 30 }
  }
}
```

Le moteur évalue les règles dans l'ordre, retourne la première correspondance, ou le `default` sinon :

```python
# app/modules/onboarding/engine.py
def evaluate_scoring(flow: dict, answers: dict[str, str]) -> dict:
    for rule in flow["scoring"]["rules"]:
        if all(answers.get(k) == v for k, v in rule["conditions"].items()):
            return rule["result"]
    return flow["scoring"]["default"]
```

## L'Expérience Utilisateur (Frontend)

Le composant `Onboarding.tsx` du module gère un automate à trois phases :

1.  **Phase Questions :** affichage séquentiel des questions chargées dynamiquement depuis l'API.
2.  **Phase Résultat :** affichage du score et du profil calculé (ex : *Solo Builder*).
3.  **Phase Inscription :** formulaire de création de compte pré-rempli avec le contexte du profil.

Un indicateur de progression encourage l'utilisateur à terminer. Chaque réponse est stockée localement avant d'être envoyée pour évaluation.

## Modes d'Utilisation

Le composant est conçu pour deux cas d'usage majeurs :

- **Mode Inscription :** nouveau visiteur arrivant sur la plateforme.
- **Mode Mise à jour :** utilisateur connecté qui redéfinit son profil.

Le mode est déterminé automatiquement :

```tsx
const isUpdate = (searchParams.get("update") === "true") || (user !== null);
```

## L'Endpoint d'Évaluation

Lorsque l'utilisateur répond à la dernière question, le frontend appelle `POST /api/onboarding/evaluate` :

```python
# app/modules/onboarding/routers.py
@router.post("/evaluate")
async def evaluate(answer: OnboardingAnswer) -> OnboardingResult:
    flow = load_flow(answer.flow_id)
    result = evaluate_scoring(flow, answer.answers)
    result_screen = load_result_screen(result["profile"])
    return OnboardingResult(**result, **result_screen)
```

Le backend retourne :

1. **Scoring Result :** le profil technique calculé et le score.
2. **Result Screen :** configuration visuelle personnalisée (titre, description, CTA) selon le profil.

## Persistance du Profil

Une fois le compte créé ou mis à jour, les réponses brutes et le profil calculé sont sauvegardés dans la table `UserProfile` (voir Chap 4). Cela permet de :

- Personnaliser l'interface de la page profil.
- Adapter dynamiquement le catalogue ou les recommandations selon le profil.
- Fournir des analytics précis sur la typologie de l'audience (module `analytics`, Chap 13).

## Créer un Flow d'Onboarding pour son Projet

Pour utiliser le module dans un contexte différent (par exemple profiler des acheteurs sur un e-shop) :

1. Créer un nouveau fichier `app/modules/onboarding/flows/mon_flow.json` avec ses questions et règles.
2. Créer les écrans de résultat associés dans `app/modules/onboarding/screens/`.
3. Déclencher le flow depuis le frontend en passant `flow_id="mon_flow"` à l'endpoint.

Aucun code Python à écrire — le moteur générique traite n'importe quel flow respectant le schéma.

---

*L'utilisateur étant profilé, nous passons aux visualisations que le module `analytics` construit à partir de ces données, dans le chapitre suivant.*
