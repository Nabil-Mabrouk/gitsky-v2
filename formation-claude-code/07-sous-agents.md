# Module 7 — Sous-agents et parallélisation (1,5 h)

## Objectifs

- Comprendre ce qu'est un sous-agent et ce qu'il apporte (isolation de contexte)
- Utiliser les sous-agents intégrés (exploration, planification)
- Créer un sous-agent personnalisé pour un rôle d'équipe
- Choisir le bon patron de parallélisation (sous-agents vs worktrees vs sessions cloud)

## 1. Le principe : déléguer avec un contexte propre

Un **sous-agent** est une instance de Claude lancée par l'agent principal
pour une tâche déléguée. Propriétés clés :

- **Contexte isolé** : le sous-agent explore, lit des dizaines de fichiers…
  et seul son **rapport final** revient dans la conversation principale.
  C'est l'outil n° 1 contre la saturation de contexte (module 2).
- **Spécialisation** : chaque sous-agent peut avoir son prompt système, ses
  outils autorisés, son modèle (ex. un modèle rapide pour les recherches).
- **Parallélisme** : plusieurs sous-agents peuvent travailler en même temps.

Cas d'usage naturels :

- Recherche large : « trouve tous les endroits où on gère la TVA » —
  le sous-agent d'exploration lit beaucoup, ne rapporte que la synthèse
- Revue spécialisée : un agent « relecteur sécurité » avec sa grille
- Tâches indépendantes en parallèle (docs + tests, ou trois analyses)

Limites à connaître : un sous-agent ne partage pas la conversation — il faut
lui donner **tout** le contexte nécessaire dans sa mission. Les allers-retours
coûtent cher : bien cadrer la mission, attendre un rapport complet.

## 2. Sous-agents personnalisés

Fichiers Markdown dans `.claude/agents/` (projet) ou `~/.claude/agents/`
(personnel) ; l'interface `/agents` aide à les créer et les gérer.

```markdown
---
name: relecteur-securite
description: À utiliser pour relire un diff sous l'angle sécurité
  (injections, authz, secrets, données personnelles).
tools: Read, Grep, Glob, Bash
model: sonnet
---

Tu es relecteur sécurité senior. Pour chaque diff :
1. Cherche injections (SQL, commande, template), problèmes d'authz,
   secrets en dur, PII loggée.
2. Classe chaque constat : critique / important / mineur.
3. Rapporte uniquement les constats vérifiés, avec fichier:ligne et
   proposition de correctif. Pas de remarques de style.
```

Bonnes pratiques :

- Le `description` conditionne la délégation automatique : formuler
  « À utiliser quand... »
- Restreindre les `tools` au nécessaire (un relecteur n'écrit pas)
- Un bon sous-agent a un **format de rapport** imposé : c'est la qualité du
  rapport qui fait la valeur de la délégation
- Versionner les agents projet : c'est un standard d'équipe

## 3. Choisir son patron de parallélisation

| Besoin | Solution |
|---|---|
| Grosse recherche/analyse sans polluer le contexte | Sous-agent (Explore) |
| Regards spécialisés sur un même travail | Sous-agents en parallèle |
| Deux features menées de front, fichiers isolés | `git worktree` + une session par worktree |
| Tâches longues sans occuper votre machine | Sessions cloud / background |

Anti-patterns :

- Paralléliser deux modifications sur **les mêmes fichiers** → conflits
  garantis ; les sous-agents parallèles doivent écrire dans des périmètres
  disjoints (ou ne pas écrire du tout)
- Sur-déléguer les petites tâches : le coût de re-contextualisation du
  sous-agent dépasse le gain
- Chaîner 5 niveaux de délégation : garder une topologie plate
  (un orchestrateur, des exécutants)

## 4. TP guidé (40 min)

1. Demander une analyse transverse du dépôt d'exercice en imposant la
   délégation (« utilise un sous-agent d'exploration ») ; comparer l'usage
   du contexte avec la même question posée en direct.
2. Créer le sous-agent `relecteur-securite` ci-dessus, l'invoquer sur le diff
   du TP module 4, examiner le rapport.
3. Lancer deux sous-agents en parallèle sur deux analyses indépendantes
   (qualité des tests / dette technique) et faire produire une synthèse.

## Checklist de validation

- [ ] Je sais expliquer l'isolation de contexte et pourquoi elle est précieuse
- [ ] Je sais créer un sous-agent avec rôle, outils restreints et format de rapport
- [ ] Je sais choisir entre sous-agents, worktrees et sessions selon le besoin
- [ ] Je connais les anti-patterns (écritures concurrentes, sur-délégation)
