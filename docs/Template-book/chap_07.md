# Authentification et Sécurité de Session

## Introduction

> **Écart au livre (Phase 6)** : ce chapitre présentait auparavant l'authentification comme un module activé « à partir du tier T1 », absent des projets « T0 ». Le système de paliers T0/T1/T2 a été retiré du framework. `auth` fait désormais partie du **core** de GitSky, au même titre que le SEO (Chap 10) : monté sans condition, sans flag ni palier qui le débloquerait.

Le module d'authentification fait partie du **core** de GitSky — il est monté sans condition dans tous les projets, qu'ils activent ou non des modules optionnels. Il fournit à la fois l'API backend (JWT + refresh) et le contexte frontend qui suit l'état de connexion à travers l'application.

## Gestion Globale de l'État : AuthContext

Côté React, nous utilisons la **Context API** pour centraliser l'identité de l'utilisateur, son rôle et ses jetons :

```tsx
// src/context/AuthContext.tsx
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(
    localStorage.getItem("access_token")
  );

  // Vérification de la session au chargement
  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (token) fetchProfile(token);
  }, []);

  // … login, logout, refresh
}
```

## Stratégie de Sécurité : JWT et Cookies

GitSky utilise une stratégie hybride pour sécuriser les sessions :

1. **Access Token :** un JWT de courte durée (15 min) stocké en `localStorage` pour les appels API.
2. **Refresh Token :** un jeton stocké dans un cookie **HttpOnly** côté backend, ce qui permet de renouveler la session sans exposer le jeton aux scripts (protection XSS).

Le refresh est déclenché automatiquement par un intercepteur `apiFetch` lorsque l'API renvoie un `401` — l'utilisateur ne perçoit rien.

## Fin de Session et Révocation

Un JWT est *stateless* : une fois émis, le serveur lui fait confiance jusqu'à expiration. Trois mécanismes complètent donc la stratégie hybride :

1. **`POST /api/auth/logout`** — expire le cookie refresh HttpOnly côté serveur. Vider le `localStorage` ne suffit pas : sans cet appel, le refresh resterait valable 7 jours sur la machine. `AuthContext.logout()` l'appelle systématiquement. L'endpoint est volontairement sans auth : il doit fonctionner même avec un access token expiré.
2. **`POST /api/auth/logout-all`** — révoque *tous* les refresh émis pour le compte (« déconnexion partout »). Chaque `User` porte un compteur `token_version`, embarqué dans le refresh (claim `tv`) ; l'endpoint incrémente le compteur, et `/refresh` refuse tout jeton dont le `tv` est périmé — même signé, même non expiré. C'est le seul levier de révocation d'un JWT stateless (cookie exfiltré, machine compromise).
3. **Politique de mot de passe** — 8 caractères minimum, appliquée **au register uniquement** (`RegisterRequest`). Le login reste non contraint : un compte créé avant la règle doit toujours pouvoir se connecter.

❌ `logout()` frontend qui ne vide que le localStorage — le cookie survit.
✅ `logout()` qui appelle l'endpoint, et `logout-all` en cas de doute sur un poste.

Le **rate limiting du login** (5 req/min) n'est pas dans l'application : conformément à la doctrine du Chap 14, il est porté par un routeur Traefik dédié généré dans le `docker-compose.yml` de production (voir Chap 21) — chaque essai coûtant un hachage argon2, un login illimité serait à la fois du credential stuffing et un DoS CPU à bas coût.

## Protection des Routes (Guards)

Toutes les pages ne sont pas accessibles à tout le monde. Trois composants "Guards" encapsulent la logique d'accès :

- **`PrivateRoute`** : redirige vers `/login` si l'utilisateur n'est pas connecté.
- **`AdminRoute`** : vérifie le rôle `admin` — utilisé uniquement quand `MODULE_ADMIN=true`.
- **`GuestRoute`** : empêche un utilisateur connecté d'accéder aux pages de login/register.

Exemple d'utilisation :

```tsx
<Route path="/admin" element={
  <AdminRoute><AdminDashboard /></AdminRoute>
} />
```

## Rôles et Progression Utilisateur

Le module `auth` gère cinq rôles (voir Chap 4 pour la définition SQLAlchemy) :

| Rôle | Origine | Droits |
|---|---|---|
| `anonymous` | Non connecté | Consultation publique uniquement |
| `waitlist` | Inscrit via le landing-collector partagé ou le module onboarding, sans compte activé | Accès très limité |
| `user` | Utilisateur activé | Fonctionnalités standard |
| `premium` | Attribué par les webhooks Stripe (Chap 16) | Fonctionnalités payantes |
| `admin` | Attribué manuellement en base | Dashboard admin |

Les transitions de rôle (`waitlist` → `user` via activation email, `user` → `premium` via abonnement Stripe) sont **automatiques** et pilotées soit par des events internes, soit par des webhooks externes.

## Authentification et Collecte de Leads en Amont

Le module auth étant **core**, l'API d'authentification complète est disponible dès la création du projet — mais un projet n'est pas obligé d'exposer immédiatement un formulaire d'inscription local. Certains choisissent de collecter d'abord les emails via le landing-collector partagé de la flotte (voir Chap 18) sans créer de comptes, le temps de valider l'intérêt pour le produit.

Quand le projet est prêt, les leads collectés sont importés dans la table `users` avec le rôle `waitlist`, puis invités à créer leur mot de passe via un email transactionnel. Cet import reste une action opérationnelle explicite — il n'est plus déclenché par un mécanisme automatique de progression entre paliers. Le cycle de vie actuel d'un projet (créé → actif → archivé, avec archivage déclenché manuellement par un opérateur) est décrit en détail au Chap 20.

---

*L'infrastructure d'authentification étant en place — et active dans tous les projets dès le départ — nous verrons dans le prochain chapitre comment le module i18n rend l'application accessible à un public international, dès que `MODULE_I18N=true` est activé.*
