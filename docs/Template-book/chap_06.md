# Le Frontend Moderne avec React et Vite

## Pourquoi cette Stack ?

Pour l'interface utilisateur de **GitSky**, nous avons privilégié la réactivité, la vitesse de développement et une esthétique "Dark Mode" soignée. Le choix s'est porté sur :

1.  **React 19 :** La dernière version du framework de Meta, offrant une gestion d'état simplifiée et des performances accrues.
2.  **Vite :** Le remplaçant moderne de Webpack. Il offre un démarrage instantané et un rechargement à chaud ultra-rapide pendant le développement.
3.  **Tailwind CSS 4 :** Une bibliothèque utilitaire de CSS qui permet de construire des interfaces complexes sans quitter le code HTML/JSX.
4.  **Radix UI & shadcn/ui :** Une base de composants accessibles et stylisables qui nous évite de réinventer la roue pour les boutons, les boîtes de dialogue ou les menus.

## Structure du Projet Frontend

Nous suivons une architecture claire pour séparer les responsabilités :

```text
frontend/
├── src/
│   ├── assets/         # Images, icônes, logos
│   ├── components/     # Composants réutilisables (Navbar, WaitlistForm)
│   │   ├── ui/         # Composants de base (Button, Input, Card)
│   │   └── analytics/  # UmamiTracker : mesure d'audience (Chap 13)
│   ├── context/        # Gestion globale de l'état (AuthContext)
│   ├── lib/            # Utilitaires (cn, apiFetch)
│   ├── pages/          # Pages principales de l'application
│   │   └── admin/      # Interface d'administration
│   ├── domain/         # Pages métier du projet (project-owned)
│   │   └── routes.tsx  # Leurs routes (export domainRoutes)
│   ├── App.tsx         # Routage principal (React Router)
│   ├── main.tsx        # Point d'entrée de l'application
│   └── i18n.ts         # Configuration multi-langue
├── public/             # Fichiers statiques et locales JSON
└── vite.config.ts      # Configuration de Vite
```

> **Écart assumé : `frontend/src/domain/routes.tsx`, le point d'extension des pages métier.** Côté backend, le code métier a toujours eu sa place réservée (`app/domain/routers.py`, monté automatiquement). Côté frontend, rien d'équivalent n'existait : `App.tsx` est un fichier châssis, que `copier update` met à jour dans tous les projets, et c'était pourtant le seul endroit où déclarer une page. Avant cette correction, politique-ia, f-ynd et ai-qube l'avaient chacun modifié à la main (27, 44 et 47 routes), et chaque mise à jour du châssis y produisait un conflit, ou une fusion silencieuse. Le problème a été remonté par l'agent dev de 0-hl.
>
> Le châssis génère désormais `frontend/src/domain/routes.tsx` une seule fois. Ce fichier est protégé par `_skip_if_exists`, comme `landing-manifest.json`. Il exporte `domainRoutes`, un fragment de `<Route>` vide par défaut, et `App.tsx` se contente de l'insérer dans le shell du site. Les pages métier ont donc la Navbar et le Footer, comme `/learn` ou `/login`, et passent par la redirection « mot de passe à changer ». Leurs chemins sont relatifs, sans `/` initial.
>
> Le nom `domainRoutes` est un contrat : un projet qui a déjà son propre `routes.tsx` le garde à chaque mise à jour, donc renommer l'export dans le châssis casserait son build. Un garde frontend n'étant que de l'UX, une page réservée aux comptes connectés doit aussi être protégée côté serveur.

## Tailwind CSS 4 et le Design System

Tailwind 4 apporte une simplification majeure dans la configuration. Le template GitSky l'utilise pour imposer une identité visuelle forte mais **paramétrable par projet** — le générateur `create-gitsky-project` (Chap 17) injecte la couleur primaire, la police et le logo depuis le `config.yaml` du projet :

*   **Dark Mode natif :** Utilisation systématique des couleurs `zinc` et `black`, avec un accent primaire configurable via la variable CSS `--color-primary`.
*   **Typographie :** `Geist` par défaut, surchargeable via `branding.font_family` dans le config.
*   **Transitions :** Utilisation de `tw-animate-css` pour des micro-interactions fluides.

Exemple d'un bouton primaire dont la couleur est paramétrée au niveau du projet :

```tsx
<button className="bg-primary text-primary-foreground font-semibold px-6 py-2.5 
                   rounded-lg hover:bg-primary/90 transition shadow-lg">
  Rejoindre la plateforme
</button>
```

Grâce à cette paramétrisation, chaque instance GitSky affiche sa propre identité visuelle sans modification du code des composants.

## Gestion des Alias de Chemin

Pour éviter les imports complexes du type `../../components`, nous utilisons des alias. `@/` pointe directement vers le dossier `src/`.

```tsx
// Au lieu de :
import { Button } from "../../components/ui/button";

// Nous écrivons :
import { Button } from "@/components/ui/button";
```

## L'importance de Vite en Développement

En local, Vite ne compile pas l'intégralité de l'application au démarrage. Il sert le code source via des modules ES natifs du navigateur. Résultat : peu importe la taille du projet, l'application est prête en moins de 300ms.

---

*L'interface étant configurée, nous allons maintenant voir comment gérer l'authentification et sécuriser les accès à notre plateforme dans le chapitre suivant.*
