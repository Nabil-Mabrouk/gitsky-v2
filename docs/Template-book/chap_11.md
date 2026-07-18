# Créer un Module Métier : L'Exemple de l'Université Virtuelle

## Introduction

Ce chapitre illustre la création d'un **module métier** de bout en bout, en prenant pour exemple l'université virtuelle — un catalogue de tutoriaux et leçons Markdown qui a servi de projet applicatif de référence à GitSky.

Le module `tutorials` que nous décrivons ici suit exactement le même contrat que les modules du core décrits aux chapitres précédents : un dossier `app/modules/tutorials/` qui apporte ses modèles, ses routeurs, ses schémas, ses migrations, et une entrée dans le shell admin.

Activation : `MODULE_TUTORIALS=true` (T2 par défaut, ou selon le projet).

## Anatomie du Module

```text
app/modules/tutorials/
├── __init__.py           # Exporte `router` — contrat d'interface
├── models.py             # Tutorial + Lesson (voir Chap 4)
├── schemas.py            # Schémas Pydantic
├── routers.py            # Endpoints publics + admin
├── content_renderer.py   # Moteur de rendu Markdown
└── migrations/           # Chaîne Alembic dédiée
```

Chaque fichier a une responsabilité précise. Ce découpage est **la convention** pour tous les modules GitSky : le générateur `create-gitsky-project` (Chap 17) scaffolde cette structure lorsqu'un nouveau module est déclaré.

## Le Catalogue Public

Le catalogue est la porte d'entrée pour l'apprenant. Il doit être clair et intelligent — ne proposer que le contenu pertinent au visiteur.

### Filtrage par Langue et Rôle

Grâce à l'intégration du module `i18n` (Chap 8) côté frontend et d'un paramètre `lang` côté API, l'utilisateur ne voit que les cours disponibles dans sa langue. Un système de badges indique si un cours est **Gratuit** ou **Premium** :

```tsx
// Learn.tsx — extrait
useEffect(() => {
  const lang = i18n.language.split("-")[0];
  fetch(`${API}/api/content/tutorials?lang=${lang}`)
    .then(data => setTutorials(data));
}, [i18n.language]);
```

## Le Moteur de Rendu Markdown

Pour un contenu technique, le format **Markdown** est idéal — les auteurs écrivent rapidement, avec support natif du code, des tableaux et des liens. Le composant `MarkdownRenderer` du module est basé sur `react-markdown`.

### Fonctionnalités Avancées

1.  **GFM (GitHub Flavored Markdown) :** support des tableaux, listes de tâches et liens automatiques.
2.  **Syntax Highlighting :** coloration syntaxique du code via `rehype-highlight` et le thème GitHub Dark.
3.  **Embeds Multimédia :** balises personnalisées `[video:URL]`, `[audio:URL]`.
4.  **Intégration YouTube :** détection automatique des liens YouTube transformés en `iframe`.

```tsx
// Exemple de pré-traitement du contenu
const processed = content.replace(
  /\[video:(.*?)\]/g,
  (_, url) => `<video controls src="${url}"></video>`
);
```

## Contrôle d'Accès au Contenu

La sécurité est gérée à deux niveaux :

- **Frontend** : les liens vers le contenu Premium sont masqués pour les utilisateurs non autorisés.
- **Backend** : les permissions sont systématiquement vérifiées via une dépendance FastAPI avant de délivrer le contenu d'une leçon.

Ne jamais se fier uniquement au filtrage frontend — un attaquant peut appeler l'API directement.

## L'Onglet Admin du Module

Le module contribue un onglet **Contenu** au dashboard admin (voir Chap 9). Il permet à un administrateur de :

- Créer et modifier des tutoriaux.
- Ajouter des leçons Markdown avec preview en direct.
- Uploader des médias via la bibliothèque intégrée.
- Publier ou dépublier du contenu.

L'onglet est déclaré dans `AdminLayout` avec `enabled: modules.tutorials` — il n'apparaît que si le module est activé.

## Le Contrat d'Interface, Point par Point

Pour créer un module métier propre, quatre engagements sont à respecter :

| Engagement | Fichier concerné | Vérifié par |
|---|---|---|
| Exposer un unique `router` FastAPI | `__init__.py` | Le core lors du chargement |
| Ne jamais importer d'autres modules | tout le dossier | Convention (revue de code) |
| Fournir sa propre chaîne de migrations | `alembic/modules/<module>/` | Runner `scripts/migrate.py` |
| Rester désactivable via `MODULE_*` | `config.py` | Test : lancer sans le flag doit fonctionner |

Un module qui viole ce contrat introduit du couplage et casse la promesse d'isolation qui rend le template industrialisable.

## Reproduire ce Pattern pour son Propre Métier

Pour ajouter un module métier à un projet GitSky :

1. Créer `app/modules/mon_module/` avec la structure décrite plus haut.
2. Déclarer les modèles SQLAlchemy dans `models.py`.
3. Générer la migration initiale : `alembic --name mon_module revision --autogenerate -m "initial"`.
4. Ajouter le flag `module_mon_module: bool = False` dans `Settings`.
5. Ajouter le chargement conditionnel dans `main.py`.
6. Écrire les schémas Pydantic dans `schemas.py`.
7. Implémenter les endpoints dans `routers.py`.
8. (Optionnel) Ajouter un onglet dans `AdminLayout` avec `enabled: modules.mon_module`.

Le générateur `create-gitsky-project` (Chap 17) automatise entièrement ces étapes lorsqu'un nouveau module est déclaré dans le `config.yaml` du projet.

---

*Après cet exemple concret, le chapitre suivant présente un autre module fourni en standard : le moteur d'onboarding dynamique — utile pour tout projet qui souhaite profiler ses utilisateurs à l'inscription.*
