# Procédure — Lancer un nouveau projet GitSky

Checklist opérateur rapide. Le détail technique/infra (variables d'env,
pièges de déploiement du wizard lui-même) reste dans
[`docs/Template-book/chap_27.md`](docs/Template-book/chap_27.md) — ce
fichier-ci ne le duplique pas, il donne juste la marche à suivre.

## 1. Créer le projet (fleet-dashboard)

Dans `https://0-hitl.com` (fleet-dashboard) : bouton **« + Nouveau projet »**
sur la grille → `/admin/fleet/new`. Un seul écran :

- **Nom** — slug DNS-safe (minuscules, chiffres, tirets) : devient nom de
  répertoire, identifiant PostgreSQL et sous-domaine.
- **Modules** — cases à cocher (catalogue plat, `docs/Template-book/chap_02.md`).
  `auth`/SEO sont core, jamais un choix.
- **Domaine** — optionnel ; vide = sous-domaine `<nom>` + suffixe configuré
  (`FLEET_SUBDOMAIN_SUFFIX`, ex. `.0-hitl.com`).
- **GitHub** — radio aucun / créer un dépôt / lier un dépôt existant
  (`owner/repo` si lien).

Soumettre. La requête est synchrone (génération + enregistrement flotte +
dépôt + premier push + bootstrap déploiement, dans cet ordre) — quelques
secondes, pas de barre de progression.

## 2. Lire le résultat, pas juste le "succès"

Le résumé affiché donne : `generated` / `github_repo` / `webhook_installed`
/ `pushed` / `deploy_triggered`, plus une liste `warnings` éventuelle.
**Un warning n'est jamais une raison de tout relancer** — à partir de
l'étape "enregistrement", plus rien n'est fatal ; les endpoints
`create-repo`/`link-repo` de la fiche projet reprennent la main après coup
sur un projet déjà généré.

## 3. Sur le serveur — étapes réelles, pas automatisées par le wizard

Le wizard écrit directement dans `PROJECTS_DIR` **sur le serveur** (c'est
déjà "la prod" — pas un brouillon local à redéployer ensuite) et déclenche
le premier `docker compose up -d --build` via le même pipeline que
`deploy-on-push.sh`. Ce qui reste malgré tout à faire à la main, une fois
la stack levée :

- **DNS** — jamais vérifié ni câblé automatiquement ; à faire à part si domaine dédié.
- **Provisionnement DB réel** — simulé sauf si `POSTGRES_CONTAINER` est
  configuré côté générateur ; le wizard ne le fait pas à la place de l'opérateur.
- **Modules structurels** (`fleet`, `worker`, `leads`) — `toggle_module.sh`
  les refuse explicitement (changement de `docker-compose.yml` trop
  profond pour un simple flag `.env`). Il faut relancer `copier update`
  avec la réponse `modules: {<module>: true}` dans `.copier-answers.yml`.
  Tout le reste du catalogue passe par `toggle_module.sh <module> on`.
- **Secrets qui n'existent dans AUCUN champ du formulaire du wizard** —
  clés API tierces propres au produit (LLM, Kraken, MaxMind, SMTP réel,
  etc.). Elles vont **exclusivement** dans `.env.local` sur le serveur
  (`/opt/gitsky/projects/<nom>/.env.local`), jamais dans `.env` (régénéré
  par `copier update`), jamais committées, jamais vues par le wizard ni par
  le générateur. `docker compose up -d --build` (ou un simple `restart` du
  service concerné) après ajout pour qu'elles soient prises en compte.
- **Compte admin** — si `MODULE_ADMIN` est actif, personne n'a de compte
  tant qu'on n'a pas lancé, sur le serveur :
  ```bash
  docker exec -it <projet>_backend ./scripts/create_admin.sh <email> [password]
  ```
  Sans mot de passe fourni, le script en génère un — **le noter tout de
  suite** (déjà vu un cas où le script plante juste après l'avoir affiché
  et où il devient irrécupérable). C'est ce compte qui permet ensuite à
  l'opérateur de se connecter au frontend.
- **Vérifier que `.env`/`.copier-answers.yml` reflètent vraiment les
  modules voulus** — le formulaire du wizard peut diverger de l'intention
  réelle (déjà vu : `monetization_shop` resté actif alors que le projet ne
  devait pas l'avoir). `GET /health` du nouveau projet donne l'état réel en
  un coup d'œil.

## 4. Cloner en local et ouvrir une session de développement

```bash
git clone <repo-du-nouveau-projet>
cd <nom-du-projet>
```

**Le `.env` local n'est PAS celui du serveur** — le clone git n'inclut
jamais `.env`/`.env.local` (gitignorés, jamais synchronisés par git dans un
sens ou dans l'autre ; serveur et poste local ont chacun leur propre couple
de fichiers, indépendants). Sans ça, `docker-compose.dev.yml` ne démarre pas :

```bash
cp .env.example .env                      # valeurs de dev suffisent
cp .env.local.example .env.local          # si présent — vide sauf besoin réel en local
docker compose -f docker-compose.dev.yml up --build
```

Pas besoin des vrais secrets de prod pour développer en local, sauf si la
fonctionnalité en cours dépend directement d'un vrai appel externe — dans
ce cas, une clé de test/sandbox dédiée, jamais celle de prod.

Ensuite, lancer `claude` dans ce dossier. **Aucun prompt de contexte à
rédiger à la main** : `CLAUDE.md` (généré) pointe vers `AGENTS.md` (généré)
— lu automatiquement en tout début de session — qui couvre déjà ce qui
appartient au projet, ce qui est châssis, ce qu'il ne faut jamais toucher,
et les vérifications avant commit/push. `MODULES.md` (généré) détaille les
points d'extension des modules actifs sur ce projet précis.

## 5. Prompt de démarrage pour l'agent développeur du projet

Ce qu'`AGENTS.md` sait déjà n'a pas besoin d'être répété. Ce qui reste à
lancer explicitement, une fois la session ouverte (§4) :

```
Ce projet vient d'être généré par GitSky. Avant tout code métier, j'ai besoin
de trois choses, dans cet ordre :

1. ÉCRIRE LE LIVRE DE SPÉCIFICATION du produit : {{BRIEF_PRODUIT — une
   description du produit, son public, ce qu'il doit faire}}. Choisis une
   structure adaptée à la complexité réelle du produit (pas besoin du
   formalisme complet chapitres/normes/annexes si le produit est simple).
   Le livre devient la source de vérité : le code le suit, un désaccord entre
   les deux se résout par un amendement documenté, jamais par une correction
   silencieuse du livre pour coller au code. Crée un fichier racine dédié
   (ex. PRODUCT.md ou équivalent) qui pose la préséance entre ce livre et les
   contrats structurels du châssis (AGENTS.md/MODULES.md — jamais l'inverse),
   et ajoute une ligne additive dans CLAUDE.md qui y renvoie (survit à
   `copier update`, ne pas l'oublier après une mise à jour du châssis).

2. DÉFINIR LA CHARTE GRAPHIQUE ET LA LANDING PAGE. Le wizard a généré un
   branding et une landing par défaut (`branding.local.css`, `Landing.tsx`,
   `landing-manifest.json`) — pas du contenu réel. Propose une identité
   visuelle cohérente avec le produit décrit au point 1, implémente-la dans
   `branding.local.css`/`Navbar.tsx`/`Footer.tsx`/`Landing.tsx` (fichiers
   "à vous", voir AGENTS.md), documente-la si elle est assez riche pour le
   justifier (ex. CHARTE-GRAPHIQUE.md).

3. Une fois 1 et 2 avancés, DÉMARRE LE DÉVELOPPEMENT DE LA PARTIE MÉTIER dans
   `app/domain/` (le seul emplacement prévu pour le code produit — jamais
   dans `app/modules/` ni les composants châssis du frontend). Propose un
   séquencement par dépendance plutôt que de tout attaquer en même temps.

Ne commence pas le point 3 sans mon accord explicite sur 1 et 2.
```

**Le compte admin (§3) n'est pas dans ce prompt** — c'est une action
serveur (accès `docker exec` en prod), pas un travail du dépôt local ; à
faire soi-même, ou à demander à l'agent qui a l'accès serveur (celui qui
développe le châssis dans cette session-ci, par exemple), séparément. Une
fois le compte créé, l'opérateur peut se connecter au frontend, lire le
livre (si publié via un catalogue de contenu, cf. `seed_tutorials.py` côté
cryptokilla) et en discuter directement avec l'agent développeur avant que
celui-ci n'attaque le point 3.

## 6. Si quelque chose ne colle pas

- Génération en `503` → `GITSKY_GENERATOR_PATH` absent/invalide côté fleet-dashboard.
- Projet généré mais `_commit` jamais résolu dans `.copier-answers.yml`
  (incapable de recevoir un futur `copier update`) → `GITSKY_MONOREPO_GITDIR`
  mal monté, ou souci `git safe.directory` — voir chap_27 §Configuration.
- Pour tout le reste (pièges connus, incidents déjà rencontrés) : voir la
  mémoire de session `gitsky-next-steps` avant de re-déboguer from scratch.
