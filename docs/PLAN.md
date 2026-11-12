# G1 — Étape 2 : mise en production

Objectif : l'assistant EU AI Act tourne sur mon serveur, en HTTPS, sur api.aymenahmedfouatih.com, et le dépôt GitHub est public et propre.
Date limite : bien avant le 4/12/2026 (fin de mon abonnement Hugging Face PRO, non renouvelé).

## Point de départ (11/11/2026)
- Étape 1 finie : tag v1.4 (c49c6e5). Held-out v2 = 94,4 % (34/36), hors sujet refusé 12/12, 0 citation inventée.
- api.py + tests/test_api.py committés (e2151b5, 34 tests verts). API testée en local avec le vrai moteur : /health 200 après 97 s, /risk, /deadlines, /ask OK, refus OK.
- requirements-api.txt écrit (versions lues avec pip freeze), pas encore committé.
- Docker Desktop fonctionne (7,53 Go de RAM, 4 CPU).
- Plan Docker déjà vérifié sur le disque : C:\Users\hp\.claude\plans\plan-docker-pour-l-api-humming-seal.md

## Règles de travail (toutes les phases)
- Je dis « Fais la phase N ». Tu présentes un plan court, j'accepte, puis tu fais toute la phase sans t'arrêter.
- Tu t'arrêtes seulement : à une erreur, à un test qui échoue, ou à une décision qui sort de ce plan.
- Une tâche = un commit (message écrit dans un fichier, puis git commit -F). Une tâche qui ne change aucun fichier ne fait pas de commit.
- Après chaque commit, tu lances `python -m pytest tests/` et tu t'arrêtes au premier échec.
- Moi seul valide : une installation hors plan, un push, une suppression, une dépense, et toute commande sur le serveur.
- Tag avant-phaseN avant les phases risquées (3 et 4).
- Ne rien inventer : un chiffre, un fichier ou une version vient d'une commande lancée, sinon tu écris « non vérifié ».
- Fin de phase : résumé simple (ce qui est fait, les chiffres mesurés, ce qui reste, les commits créés).

## Phase 1 — API dans Docker, en local
1. requirements-api.txt : vérifier (chaque ligne paquet==version, pas de gradio, pytest ni httpx), puis le committer seul.
2. Test hors ligne en local, sans Docker : lancer l'API depuis .venv avec HF_HOME=E:\hf-cache, HF_HUB_OFFLINE=1 et TRANSFORMERS_OFFLINE=1, pour cette session seulement. Attendre /health = 200, faire un appel /ask, puis arrêter. Noter le fichier de poids chargé (.bin ou safetensors) et le temps. Pas de commit. Si ça échoue, arrêt.
3. Dockerfile + .dockerignore, d'après le plan vérifié du 11/11 :
   - python:3.12-slim, torch CPU, versions de requirements-api.txt.
   - Copiés dans l'image : api.py, src/, data/index/ et data/processed/chunks.json (lu par /deadlines).
   - Modèle BGE-M3 non copié : seul E:\hf-cache\hub est monté, en lecture seule. Jamais E:\hf-cache entier, qui contient mon jeton HF.
   - HF_HUB_OFFLINE=1. La clé est passée au lancement par --env-file, jamais dans l'image.
   - Utilisateur non-root, 1 worker uvicorn, healthcheck sur /health avec start-period de 240 s.
   - REWRITE_CACHE=0 et LLM_PROVIDER=anthropic imposés dans l'ENTRYPOINT.
   - .dockerignore exclut .env, .env.*, .venv, data/raw, data/eval, .git, tests, notes et les caches Python.
   - Vérifier avec `docker build --check .`, puis commit.
4. Avant le build, vérifier l'espace libre sur C: et s'arrêter s'il reste moins de 8 Go. Ensuite :
   - `docker build -t g1-api .`
   - `docker run --rm -p 8000:8000 --env-file .env -v E:\hf-cache\hub:/hf-cache/hub:ro g1-api`
   - Tester /health, /risk, /deadlines, /ask avec une vraie question (réponse avec citations), puis /ask avec une question hors sujet (refus attendu).
   - Vérifier que .env est absent de l'image : `docker run --rm --entrypoint ls g1-api -a /app`
   - Si un correctif est nécessaire : un commit par correctif, et les tests relancés.
5. Mesures, à noter dans la section « Résultats » ci-dessous :
   - taille de l'image (`docker images g1-api`) ;
   - RAM la plus haute (`docker stats --no-stream`, relevé au démarrage et pendant 3 appels /ask) ;
   - temps jusqu'à /health = 200 dans le conteneur.
   Puis commit et tag v2.0-api-local, sans push.

Fini quand : /ask répond juste dans le conteneur, la question hors sujet est refusée, .env est absent de l'image, et les trois chiffres sont notés. Commit fait et tag v2.0-api-local posé.

## Phase 2 — Préparer la prod, en local
1. Lecture de l'IP du visiteur derrière Caddy. api.py doit prendre la dernière adresse de X-Forwarded-For (celle ajoutée par Caddy), pas la première, qu'un visiteur peut falsifier. Ajouter des tests : sans en-tête, avec en-tête, avec en-tête falsifié. Les limites LIMIT_PER_VISITOR (défaut 10) et LIMIT_PER_DAY (défaut 300) doivent toujours fonctionner. Commit.
2. Créer deploy/env.example : liste des variables du serveur (ANTHROPIC_API_KEY vide, CORS_ORIGINS, LIMIT_PER_VISITOR, LIMIT_PER_DAY, MAX_QUESTION_CHARS, MAX_CONCURRENT), sans aucune valeur secrète. Commit.
3. Rebuild de l'image, puis les mêmes tests que la tâche 4 de la phase 1.

Fini quand : les tests passent, y compris les nouveaux tests d'IP, et l'image reconstruite répond juste.

## Phase 3 — Serveur, HTTPS, DNS (tag avant-phase3)
0. Moi : choisir le VPS OVHcloud d'après la RAM mesurée en phase 1. Vérifier l'offre réelle dans le panier, acheter moi-même, et créer une clé SSH.
1. Sécuriser le serveur : connexion SSH par clé seulement, pare-feu avec les ports 22, 80 et 443 ouverts et rien d'autre. Installer Docker d'après la documentation officielle.
2. Envoyer l'image avec `docker save`, `scp` puis `docker load`, parce que data/index n'est pas dans git et qu'on ne peut donc pas builder depuis le dépôt. Mettre BGE-M3 sur le serveur une fois, en le téléchargeant ou en le copiant depuis E:\hf-cache\hub. Créer le fichier .env sur le serveur seulement, avec les droits 600.
3. Lancer le conteneur avec --restart unless-stopped, le port 8000 ouvert seulement sur 127.0.0.1.
4. Caddy en reverse proxy vers 127.0.0.1:8000, avec HTTPS automatique. DNS api.aymenahmedfouatih.com en enregistrement A sur Cloudflare, en « DNS only » (nuage gris). Le Caddyfile et la commande de lancement sont rangés dans deploy/ et committés, jamais le .env.
5. Tests depuis l'extérieur : /health, /ask juste, refus hors sujet, limite par visiteur atteinte. Redémarrer le serveur et vérifier que le conteneur remonte seul. Tag v2.0-prod.

Fini quand : https://api.aymenahmedfouatih.com/health répond 200, /ask répond juste depuis l'extérieur, les limites fonctionnent, et le conteneur remonte seul après un redémarrage.

## Phase 4 — GitHub public (tag avant-phase4)
1. Chercher des secrets dans tout l'historique git : clés (sk-ant-, gsk_, hf_), un .env committé un jour, le contenu de .env.example. Si quelque chose est trouvé, arrêt et décision ensemble.
2. Lister ce qui est suivi par git et que le public verrait (notes/, data/raw, data/eval, data/processed). Je décide de ce qui reste.
3. README : à quoi sert G1 ; les chiffres de référence (held-out v2 94,4 %, hors sujet refusé 12/12, 0 citation inventée) ; le lancement local, y compris comment reconstruire data/index, qui n'est pas dans git ; l'architecture ; les limites connues (v1.5 : règle des 2 fiches, h04/v02) ; le lien de l'API en ligne. Commit.
4. Moi : créer le dépôt public. Push seulement après mon accord. Tag v2.0.

Fini quand : le dépôt public est propre, le README est clair et donne le lien de l'API en ligne. Tag v2.0 posé.

## Résultats
(à remplir pendant les phases)
- Phase 1 — taille de l'image : … ; RAM max : … ; /health 200 après : … s ; poids chargés : …
