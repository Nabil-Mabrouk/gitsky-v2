# SEO et Optimisation pour la Visibilité

## Introduction

Le SEO fait partie du **core** de GitSky, au même titre que `auth` (Chap 7) — les composants qu'il fournit sont montés sans condition, dans tous les projets, quels que soient les modules optionnels activés. Une landing invisible aux moteurs de recherche perd 80 % de son trafic potentiel, donc l'optimisation est active dès la création du projet.

Ce chapitre couvre les patterns SEO à intégrer dans une application Single Page React : balises meta dynamiques, sitemap généré côté backend, données structurées Schema.org, et intégration avec le module `i18n` (Chap 8) lorsqu'il est activé.

## Gestion Dynamique des Meta Tags

Contrairement aux frameworks comme Next.js qui gèrent les meta tags côté serveur, une application React nécessite une bibliothèque tierce pour modifier les balises `<head>`. GitSky utilise `react-helmet-async`.

### Le Composant SEO Réutilisable

Le core centralise la gestion des balises dans un composant unique. Il gère :

*   Le titre de la page (formaté avec le nom du projet).
*   La description pour Google.
*   Les balises **Open Graph** pour un partage élégant sur Facebook et LinkedIn.
*   Les **Twitter Cards** pour les aperçus sur X.
*   La balise `canonical` pour éviter le contenu dupliqué.

```tsx
<SEO 
  title="Apprendre l'automatisation" 
  description="Découvrez nos tutoriaux HITL"
  url="/learn"
/>
```

## Sitemap et Robots.txt Dynamiques

Pour que les robots d'indexation découvrent tout le contenu, un fichier `sitemap.xml` est indispensable. Comme le contenu peut provenir de modules variables selon le projet (tutoriaux, produits, articles…), ce fichier est **généré dynamiquement par le backend**.

### Génération Côté Backend (FastAPI)

L'endpoint `/sitemap.xml` parcourt les tables publiques exposées par les modules activés — par exemple `Tutorial` si `MODULE_TUTORIALS=true`, `Product` si `MODULE_MONETIZATION_SHOP=true` — et génère un flux XML listant les URLs **indexables** (les pages publiques uniquement). Chaque module importe ses modèles **à l'intérieur du `if`** : c'est le même chargement conditionnel que pour les routeurs (Chap 5 §3), et il garantit qu'un module désactivé n'introduit ni ses URLs ni ses dépendances dans le sitemap.

Le critère « indexable » s'appuie sur les champs réels de chaque modèle : un tutorial l'est quand son `access_role` vaut `anonymous` (page publique, cf. Chap 11), un produit quand il est `is_active`. La stack étant asynchrone (Chap 3), la requête passe par `await db.execute(select(...))`.

```python
# app/core/seo.py — extrait
@router.get("/sitemap.xml")
async def sitemap(db: AsyncSession = Depends(get_db)) -> Response:
    urls = _static_urls()
    if settings.module_tutorials:
        from app.core.models import UserRole
        from app.modules.tutorials.models import Tutorial
        rows = (await db.execute(
            select(Tutorial).where(Tutorial.access_role == UserRole.anonymous)
        )).scalars().all()
        urls += [SeoUrl(path=f"/learn/{t.slug}") for t in rows]
    if settings.module_monetization_shop:
        from app.modules.monetization.models import Product
        rows = (await db.execute(
            select(Product).where(Product.is_active.is_(True))
        )).scalars().all()
        urls += [SeoUrl(path=f"/shop/{p.slug}") for p in rows]
    return Response(content=_render_sitemap(urls), media_type="application/xml")
```

## Données Structurées (JSON-LD)

Pour apparaître sous forme de "Rich Snippets" dans les résultats de recherche, GitSky intègre des données structurées au format **Schema.org**.

Pour la page d'un tutorial exposée par le module `tutorials`, le type `Course` permet à Google d'afficher le nombre de leçons et la durée directement dans ses résultats. Pour un produit du module `monetization`, le type `Product` avec les prix et la disponibilité s'affiche dans Google Shopping.

## Intégration avec le Module i18n

Quand `MODULE_I18N=true`, le composant SEO génère automatiquement les balises `hreflang` :

```html
<link rel="alternate" hreflang="fr"        href="https://mon-projet.com/learn" />
<link rel="alternate" hreflang="en"        href="https://mon-projet.com/en/learn" />
<link rel="alternate" hreflang="x-default" href="https://mon-projet.com/learn" />
```

Le sitemap est également généré **par langue** — chaque URL apparaît une fois par langue supportée, avec la balise `xhtml:link` correspondante. Cette conformité aux directives Google est indispensable pour ne pas être pénalisé sur le contenu dupliqué entre les versions linguistiques.

## Indexation Sélective (`noindex`)

Toutes les pages ne doivent pas être indexées. Les pages de profil utilisateur, le dashboard admin, ou les pages de succès de paiement contiennent des informations privées ou peu utiles au référencement. La propriété `noindex={true}` du composant `SEO` envoie l'instruction aux moteurs de recherche.

## SEO pour un Projet en Phase de Lancement

> **Écart au livre (Phase 6)** : cette section reliait autrefois l'indexation SEO au « kill mechanism » — un mécanisme de notation automatique des signaux de croissance qui pouvait décider seul d'arrêter un projet T0 mal indexé. Ce mécanisme (ainsi que `kill_check.py` et les paliers T0/T1/T2 qu'il pilotait) a été retiré du framework. Les métriques ci-dessous restent pertinentes, mais leur interprétation est désormais entièrement entre les mains de l'opérateur.

Un projet qui ne mobilise que le socle core (une simple landing, sans module optionnel activé) bénéficie déjà de tout le socle SEO ci-dessus. Les métriques à surveiller à ce stade sont différentes :

- **Google Search Console** : la landing est-elle indexée ?
- **Position moyenne** sur les mots-clés cibles (extraits du harvest de la phase idée).
- **Taux de clic** dans les SERPs sur les impressions générées.

Une landing mal indexée après 21 jours est un signal opérationnel fort, mais c'est à l'opérateur humain d'en tirer les conséquences — retravailler le contenu, activer d'autres modules, ou archiver le projet manuellement (`POST /api/fleet/projects/{name}/archive`, voir Chap 20). GitSky ne prend plus cette décision automatiquement.

---

*Notre socle est désormais complet côté frontend et backend, sans condition de palier. La partie suivante détaille les modules optionnels qui viennent enrichir un projet selon ses besoins.*
