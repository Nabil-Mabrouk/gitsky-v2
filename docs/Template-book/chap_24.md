# GitSky Studio : Direction Artistique de Flotte

## Introduction

L'industrialisation d'une flotte crée une tension frontale : un même template qui porte 100 projets pousse vers l'**homogénéité visuelle**. Or 100 landings identiques sont un poison — non seulement la conversion s'effondre, mais surtout la mesure est biaisée : si un design générique plombe *toutes* les landings, on ne teste plus la demande d'une idée, on teste notre skin.

Le levier `branding` du générateur (Chap 17) ne résout pas ce problème : couleur, police et logo restent du *theming*. Deux landings token-personnalisées demeurent visiblement sœurs — même squelette, mêmes sections, même rythme.

Le **GitSky Studio** apporte la réponse : un service partagé d'agents IA qui, à partir du signal d'une idée, **conçoit la direction artistique, rédige le contenu, produit les médias et assemble** une vitrine distincte, aux standards GitSky. Ce n'est pas un module de plus greffé sur le template — c'est le framework agentic (Chap 15) **retourné vers l'intérieur** : GitSky applique à sa propre fabrique la technologie qu'il vend à ses projets.

## Le Châssis et la Vitrine

Le Studio n'a de sens que si l'on scinde d'abord chaque projet en deux couches à cycles de vie opposés :

| | Châssis (partagé) | Vitrine (propre au projet) |
|---|---|---|
| Contenu | backend, auth, sécurité, deps, build, i18n runtime | landing : layout, sections, copy, médias, esthétique |
| Propriété | template | projet |
| `copier update` | propage les correctifs | n'y touche **jamais** |
| Liberté artistique | nulle (c'est le moteur) | totale |

C'est cette frontière qui réconcilie industrialisation et différenciation : on industrialise le moteur, on libère la carrosserie. Le diff à trois voies de Copier (Chap 17) respecte cette frontière dès lors qu'elle est **déclarée explicitement** — la vitrine est une zone `project-owned`, exclue de la propagation.

> **Écart assumé** — la frontière s'est redessinée en cours de route : la vitrine est aujourd'hui rendue, pour tous les projets sans distinction, par les mêmes composants React que le reste du frontend (`frontend/src/pages/Landing.tsx` et `frontend/src/components/blocks/**`), plutôt que par un gabarit HTML Jinja dédié initialement envisagé pour les vitrines les plus simples. Ce code de rendu est donc redevenu **châssis** (`copier update` le propage normalement) — seule la *donnée* produite par le Studio (`landing-manifest.json`, skin/blocks/hero_image) reste `project-owned` et gelée par `_skip_if_exists`. La frontière entre les deux couches n'a pas disparu ; elle est descendue d'un cran, du fichier entier jusqu'à son seul contenu. Décision produit (Chap 25) : cohérence du stack et réutilisation du code sur l'ensemble de la flotte, au prix du rendu 100 % client-side (pas de prerendering) — un compromis SEO/vitesse assumé par rapport au HTML statique d'origine.

## Le Pipeline d'Agents

Le Studio est un **service agentic pré-configuré**, déclaré dans `agent_services.yaml` (Chap 15) au même titre que les services vendus aux projets. Son métier : concevoir des landings GitSky. Un brief de marque circule entre agents spécialisés, chacun produisant un artefact contractuel :

| Agent | Entrée | Sortie |
|---|---|---|
| **Directeur artistique** | signal harvest (thread source, audience, verticale) | brief de marque : palette, duo typographique, ton, registre visuel, choix de skin |
| **Rédacteur** | brief + verbatim de la source | copy par section, dans la langue exacte de l'audience |
| **Média** | brief + copy | prompts → hero, illustrations, éventuellement vidéo, déclinés du brief |
| **Assembleur** | brief + copy + médias + catalogue de blocs | arrangement de la landing → Creative Manifest |
| **QA / Guardrails** | l'ensemble | vérifie les standards GitSky (voir plus bas) |

Le directeur artistique tient le brief comme **contexte partagé** (l'orchestrator et le memory system du Chap 15). Le modèle sous-jacent est **multimodal** : l'agent *voit* ses propres sorties pour les juger et itérer.

Le principe verbatim du harvest (Chap 20) s'étend ici au **design verbatim** : matcher les codes esthétiques de l'audience-source. Une landing pour développeurs issus de Reddit, pour créateurs issus de TikTok, ou pour acheteurs B2B issus de LinkedIn n'obéissent pas aux mêmes codes visuels.

## Le Creative Manifest : Geler la Sortie de l'IA

Un principe non négociable structure toute l'intégration : **l'IA est non-déterministe, mais GitSky exige la reproductibilité.** Un `config.yaml` doit toujours regénérer le même projet — c'est ce qui permet de le recréer à l'identique en cas de restauration après incident, ou de reconstitution manuelle après un archivage (Chap 20).

La règle est donc :

> Le Studio tourne **une seule fois**, à la création. Sa sortie — le **Creative Manifest** — est **persistée et versionnée**, jamais re-générée à la volée. Le générateur reste 100 % déterministe : il consomme le manifest figé.

```yaml
# startup-factory-configs/manifests/pain-scraper.yaml — extrait
manifest_version: 3
brief:
  skin: editorial-serif
  palette: { primary: "#1A1A1A", accent: "#C8452D" }
  type_pairing: { display: "Fraunces", body: "Inter" }
  tone: "direct, technique, sans bullshit"
blocks:
  - hero: { headline: "...", media: assets/pain-scraper/hero-3.webp }
  - pain_points: { items: [...] }
  - email_capture: { cta: "Rejoindre la beta" }
media:
  - id: hero-3
    prompt: "..."
    license: generated-owned
```

Autrement dit : **l'agent enrichit le `config.yaml`, il ne remplace pas la génération.** Le manifest *est* la section `branding` + `landing` du config, en version augmentée. Les médias vivent dans le media store partagé de la flotte.

## Le Modèle de Publication

La question « GitSky déploie-t-il automatiquement, ou faut-il un humain avant publication ? » appelle une réponse de principe :

> On barre l'étape **irréversible** (rendre public, indexer, dépenser en acquisition), jamais l'étape de **génération**. Générer est gratuit et réversible ; publier un domaine dédié avec du SEO acquis et des utilisateurs payants ne l'est pas.

C'est le même principe de gradation du risque, appliqué à la publication : cheap à tester, délibéré à engager. Elle donne trois modes indexés sur le **blast radius**, pas un choix binaire — et le curseur, ici, n'est plus un tier de projet mais la nature du domaine visé (sous-domaine de flotte, éphémère et jetable, versus domaine dédié, engageant et coûteux à défaire) :

| Mode | Quand | Rôle de l'humain |
|---|---|---|
| **Auto-publish guardrailé** | sous-domaine de flotte (`*.mystudio.com`), si les guardrails passent | *on-the-loop* : surveille le dashboard, hors du chemin critique |
| **Preview-first** (défaut sain) | déploiement auto sur `x.preview.mystudio.com` (noindex), live sur un clic | *on-the-loop* |
| **HITL bloquant** | domaine dédié (custom domain), campagne payante | *in-the-loop* : approbation obligatoire |

Trois convictions sous-tendent ce modèle :

**Ne pas réintroduire le goulot que la fabrique a supprimé.** 100 landings × approbation manuelle, et l'opérateur *redevient* le bottleneck que GitSky existe pour éliminer. Sur un sous-domaine de flotte, l'humain doit être *on* the loop, pas *in* it.

**Remplacer « human-in-the-loop » par « guardrails-in-the-loop ».** Le gate par défaut est *machine*. L'humain n'intervient que sur échec de guardrail ou fort blast radius (domaine dédié). C'est « cadrer, pas brider » — la philosophie du module security (Chap 14) transposée au design.

**L'autonomie se gagne (ratchet de confiance).** Tant que le Studio n'a pas fait ses preuves, davantage de gates humains. Quand ses guardrails affichent un track record — conversion mesurée et zéro incident de marque, visibles au fleet dashboard — on desserre. Comme un déploiement canari, l'autonomie progresse par degrés de confiance.

## Itération : des Diffs sur le Manifest

Lorsque l'opérateur veut retoucher — « change cette couleur », « réécris cette section », « remplace ce hero » — ces modifications sont des **diffs sur le Creative Manifest**, pas des régénérations.

- Le manifest est la source de vérité, **versionné et réversible comme du code**.
- Édition humaine directe et instruction en langage naturel à l'IA atterrissent toutes deux comme une **nouvelle version de manifest**.
- Le fleet dashboard affiche l'historique de design d'un projet ; un rollback est un simple retour de version.
- La **régénération complète** reste possible, mais c'est l'option nucléaire : explicite, jamais implicite.

Règle de propriété des pixels, pour éviter que l'IA écrase le travail humain :

| Zone | Statut |
|---|---|
| Piloté par le manifest | regénérable — l'IA peut y repasser |
| Échappatoire full-custom (code à la main) | gelée — jamais regénérée |

Un projet qui a fait ses preuves et mérite du sur-mesure bascule sa vitrine dans la zone échappatoire, définitivement protégée de toute régénération.

## Les Guardrails : Cadrer, pas Brider

Le cadre est ce qui permet de lâcher l'IA sans qu'elle casse la qualité. L'agent ne peint pas des pixels libres — il **compose dans un système de design borné** (tokens + catalogue de blocs + skins curés). La contrainte garantit *à la fois* qualité et diversité ; la liberté totale produit de la bouillie moyenne.

L'agent QA valide avant tout déploiement :

| Guardrail | Vérifie |
|---|---|
| Accessibilité | contraste WCAG, tailles, alternatives textuelles des médias |
| Cohérence de marque | respect du brief (palette, typo, ton) |
| Claims légaux | absence d'allégations factuelles non étayées sur la landing |
| Licences médias | droits clairs sur chaque asset (généré-possédé ou licencié) |

### Le Paradoxe de l'Homogénéité IA

Un piège à concevoir *contre* : en résolvant « toutes pareilles à cause du template », on risque « toutes pareilles à cause de l'IA » — le même *AI look* sur 100 landings. L'antidote est double : composer dans des skins curés (variété structurelle garantie) et surveiller la diversité inter-projets comme une métrique de flotte à part entière.

## La Boucle de Feedback : la Vraie Douve

Le fleet dashboard mesure déjà la conversion de chaque landing (Chap 19). Le Studio referme la boucle : **quelles directions artistiques convertissent** est réinjecté dans le scoring du directeur artistique.

Le Studio s'améliore alors *parce qu'il est câblé à un portefeuille de données de conversion réelles* — un avantage qu'aucun outil de design générique isolé ne possède. La génération elle-même n'est pas la douve ; la boucle d'apprentissage sur données de flotte l'est.

## Anti-Patterns à Éviter

- **Régénérer à la volée à chaque déploiement.** Casse la reproductibilité : un `config.yaml` ne redonnerait plus jamais le même projet, y compris pour une reconstitution après archivage (Chap 20). Le manifest se fige.
- **Exiger une approbation humaine pour chaque publication sur sous-domaine de flotte.** Réintroduit le goulot d'étranglement opérateur.
- **Lâcher l'IA sans design system.** Produit une homogénéité IA, pire que l'homogénéité template car plus difficile à diagnostiquer.
- **Éditer les fichiers générés sans passer par le manifest.** La prochaine régénération écrase le travail — sauf dans la zone échappatoire déclarée.

---

*Le Studio donne à la flotte sa direction artistique à l'échelle. Il clôt la boucle industrielle : la même architecture agentic sert les produits et la fabrique qui les engendre. La partie suivante revient à la production et à la maintenance de cet ensemble en conditions réelles.*
