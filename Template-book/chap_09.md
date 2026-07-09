# Dashboard Admin : Shell Extensible

## Introduction

Le dashboard admin de GitSky suit le même principe modulaire que le backend : le **core** fournit un **shell** — l'authentification admin, la mise en page, la navigation, le squelette d'onglets — que **chaque module activé** contribue à peupler par ses propres composants et endpoints.

Le shell est disponible dès `MODULE_ADMIN=true` (soit à partir du tier T2 par défaut). En T0 et T1, il n'existe simplement pas — pas de route `/admin`, pas de rôle `admin` à attribuer.

## Architecture du Shell

Le dashboard est structuré autour d'un `AdminLayout` qui compose une barre latérale et un espace principal. La barre latérale est **peuplée dynamiquement** selon les modules activés :

```tsx
// frontend/src/pages/admin/AdminLayout.tsx — extrait
const tabs = [
  { key: "users",     label: "Utilisateurs", path: "/admin/users",     enabled: true }, // shell
  { key: "waitlist",  label: "Waitlist",     path: "/admin/waitlist",  enabled: true }, // shell
  { key: "analytics", label: "Analytics",    path: "/admin/analytics", enabled: modules.analytics },
  { key: "content",   label: "Contenu",      path: "/admin/content",   enabled: modules.tutorials },
  { key: "security",  label: "Sécurité",     path: "/admin/security",  enabled: modules.security },
  { key: "shop",      label: "Boutique",     path: "/admin/shop",      enabled: modules.monetization },
];
```

Le flag `modules.<nom>` est fourni au frontend via un endpoint `/api/admin/modules` qui expose la configuration côté backend. Un onglet dont le module n'est pas activé n'apparaît ni dans la barre latérale ni comme route valide.

## Onglets du Shell (Toujours Présents)

Deux onglets sont apportés par le shell lui-même et ne dépendent d'aucun module optionnel.

### Utilisateurs

Gestion des comptes, rôles et suspensions. L'interface permet de modifier dynamiquement le rôle d'un utilisateur (par exemple `user` → `premium` en cas d'attribution manuelle), de suspendre un accès en cas de comportement suspect, et de consulter le profil complet.

### Waitlist

Pour gérer une croissance progressive, un projet GitSky peut utiliser une liste d'attente. Les administrateurs envoient ou renvoient des invitations d'un clic, générant automatiquement des jetons d'invitation stockés en base et transmis par email transactionnel.

## Onglets Apportés par les Modules

Chaque module optionnel qui expose une surface admin contribue à son propre onglet :

| Onglet | Module | Détails |
|---|---|---|
| Analytics | `analytics` | Cartes mondiales, timelines, filtres par rôle (voir Chap 13) |
| Contenu | `tutorials` | Gestion des tutoriaux et leçons Markdown (voir Chap 11) |
| Sécurité | `security` | Journal des événements du SecurityMiddleware (voir Chap 14) |
| Boutique | `monetization` | Produits, ventes, abonnements (voir Chap 16) |

Le pattern est le suivant. Chaque module fournit :

1. **Un routeur backend** exposé sous `/api/admin/<module>` (protégé par vérification de rôle `admin` côté backend).
2. **Une page React** rendue à l'URL `/admin/<module>`.
3. **Une entrée de menu** dans la configuration du `AdminLayout`.

## Bibliothèque de Médias

Un composant de médias peut être proposé par le module `tutorials` pour fournir un gestionnaire de fichiers depuis le dashboard : upload d'images, vidéos ou PDF ensuite insérables dans le contenu via des snippets Markdown (`[video:URL]`, `[audio:URL]` — voir Chap 11 pour le rendu). Ce composant n'a pas de flag propre — il est disponible dès que `MODULE_TUTORIALS=true`.

## Sécurité du Dashboard

L'accès au dashboard est doublement protégé :

1. **Côté frontend** : `AdminRoute` (Chap 7) redirige tout utilisateur non-admin vers `/`.
2. **Côté backend** : chaque endpoint `/api/admin/*` vérifie le rôle via une dépendance `require_admin` avant tout traitement.

Ne jamais se fier uniquement à la protection frontend — un attaquant peut appeler l'API directement, la vérification serveur est la seule qui compte.

---

*Le shell admin étant posé, le prochain chapitre décrit le SEO — dernier composant présent à tous les tiers — avant d'aborder les modules optionnels qui viennent enrichir le shell.*
