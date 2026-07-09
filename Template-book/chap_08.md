# Internationalisation (Module i18n)

## Introduction

Le module `i18n` de GitSky rend une application multilingue **à partir du tier T2**. Il n'est jamais activé en T0 ou T1 — la traduction est un investissement dont le retour n'apparaît qu'à un stade avancé du produit, quand le marché domestique est validé.

Activation : `MODULE_I18N=true`.

Sur les projets où l'internationalisation n'est pas pertinente (marché exclusivement francophone, produits techniques anglophones dès le départ), le flag reste à `false` et l'application tourne en une seule langue sans surcoût.

## Architecture i18n

L'implémentation repose sur deux composants coordonnés :

- **Côté frontend :** `react-i18next` charge les traductions à la demande et met à jour l'interface sans rechargement.
- **Côté backend :** un endpoint de type `GET /api/content/tutorials?lang=fr` filtre le contenu selon la langue demandée.

Les traductions sont découpées par **namespace** pour rester maintenables :

```text
frontend/public/locales/
├── fr/
│   ├── common.json    # Navigation, footer, actions génériques
│   ├── auth.json      # Login, register, mot de passe oublié
│   ├── learn.json     # Contenu pédagogique
│   └── admin.json     # Dashboard admin
└── en/
    ├── common.json
    ├── auth.json
    ├── learn.json
    └── admin.json
```

## Configuration

Le fichier `src/i18n.ts` initialise `react-i18next` :

```ts
// src/i18n.ts
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import Backend from "i18next-http-backend";
import { initReactI18next } from "react-i18next";

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "fr",
    supportedLngs: ["fr", "en"],
    ns: ["common", "auth", "learn", "admin"],
    backend: {
      loadPath: "/locales/{{lng}}/{{ns}}.json",
    },
  });
```

## Utilisation dans un Composant

```tsx
import { useTranslation } from "react-i18next";

function Navbar() {
  const { t, i18n } = useTranslation("common");
  return (
    <nav>
      <a href="/learn">{t("nav.learn")}</a>
      <a href="/pricing">{t("nav.pricing")}</a>
      <LangSelector current={i18n.language} />
    </nav>
  );
}
```

Le `LangSelector` permet à l'utilisateur de basculer de langue à chaud sans rechargement — le choix est persisté dans le `localStorage`.

## Contenu Multilingue en Base

Pour les modules qui gèrent du contenu (comme `tutorials`), le modèle SQLAlchemy inclut une colonne `lang` (voir Chap 4). Le filtrage se fait côté backend :

```python
@router.get("/tutorials")
async def list_tutorials(lang: str = "fr", db: Session = Depends(get_db)):
    return db.query(Tutorial).filter(Tutorial.lang == lang).all()
```

## Bonnes Pratiques

- **Une clé de traduction par intention**, pas par écran. `auth.login.submit` est plus réutilisable que `login_page_submit_button`.
- **Fallback vers le français** en cas de clé manquante en anglais — mieux qu'un `[missing key]`.
- **Extraction automatique** avec `i18next-parser` en pré-commit hook pour éviter les traductions manquantes.
- **Pluralisation gérée par i18next**, jamais en concaténation :

```json
{
  "notifications.count": "{{count}} notification",
  "notifications.count_plural": "{{count}} notifications"
}
```

## Impact sur le SEO

Un site multilingue impose des balises `hreflang` et un `sitemap.xml` par langue. Le module SEO de GitSky (Chap 10) gère ces balises automatiquement quand `MODULE_I18N` est activé, en générant une entrée par (URL, langue) dans le sitemap.

---

*Avec l'authentification et l'i18n en place côté core, le prochain chapitre décrit le shell admin — surface d'administration extensible que chaque module optionnel viendra peupler.*
