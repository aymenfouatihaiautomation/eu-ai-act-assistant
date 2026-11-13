# G1 — installation du serveur Ubuntu (commandes dans l'ordre)

Rien ici n'a été exécuté. Sources : documentation officielle (Docker, Caddy, Ubuntu), lue le 2026-11-13.
Légende : **vérifié** = copié de la doc officielle ; **non vérifié** = je n'ai pas pu le confirmer dans la doc.

## 0. Avant de commencer (toi)
- VPS acheté, clé SSH créée, DNS : enregistrement A `api.aymenahmedfouatih.com` → IP du VPS, Cloudflare en « DNS only » (nuage gris).
- Remplace `<IP>` et `<user>` ci-dessous.

## 1. Pare-feu (ports 22, 80, 443 seulement)
Sur le serveur :
```bash
sudo ufw allow 22          # vérifié (doc Ubuntu)
sudo ufw allow 80          # vérifié (même syntaxe que allow 22)
sudo ufw allow 443         # vérifié (même syntaxe)
sudo ufw default deny incoming   # non vérifié : absent de la doc Ubuntu lue (c'est le défaut d'ufw d'après mes connaissances)
sudo ufw enable            # vérifié
sudo ufw status verbose    # vérifié
```
Fais `allow 22` AVANT `enable`, sinon tu te coupes l'accès SSH.

**Attention (vérifié, doc Docker)** : les ports publiés par Docker contournent ufw. C'est pourquoi le conteneur est lancé avec `-p 127.0.0.1:8000:8000` (étape 5) : le port 8000 n'est jamais exposé à l'extérieur.

## 2. SSH par clé seulement
Éditer `/etc/ssh/sshd_config` : `PasswordAuthentication no` — **non vérifié** (je n'ai pas lu la doc OpenSSH/Ubuntu pour cette étape). Vérifier d'abord qu'une connexion par clé fonctionne dans un second terminal, puis recharger SSH (nom du service, `ssh` ou `sshd` : **non vérifié**).

## 3. Docker (vérifié, https://docs.docker.com/engine/install/ubuntu/)
```bash
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl status docker
sudo docker run hello-world
```

## 4. Envoyer l'image et le modèle (depuis ton PC)
`docker save` / `scp` / `docker load` : commandes standard Docker/OpenSSH, **non vérifiées** dans la doc ici.
```bash
# PC : l'image fait ≈ 553 Mio (mesure phase 2), gzip ne gagne presque rien
docker save g1-api -o g1-api.tar
scp g1-api.tar <user>@<IP>:/home/<user>/
# serveur :
sudo docker load -i /home/<user>/g1-api.tar
```
Modèle BGE-M3 : copier le dossier `E:\hf-cache\hub` vers le serveur (ex. `scp -r`), vers `/srv/g1/hf-cache/hub` (chemin choisi par moi, pas imposé).

Fichier `.env` sur le serveur seulement (jamais dans git) — variables listées dans `deploy/env.example` :
```bash
sudo mkdir -p /srv/g1
sudo nano /srv/g1/.env          # copier env.example, remplir ANTHROPIC_API_KEY, CORS_ORIGINS
sudo chmod 600 /srv/g1/.env
```

## 5. Lancer le conteneur (port 8000 sur 127.0.0.1 seulement)
Le montage et les variables (ex. variable pointant le cache HF) sont à reprendre de la commande `docker run` de la phase 1/2 : **non vérifié ici**, à confirmer dans PLAN.md avant de lancer.
```bash
sudo docker run -d --name g1 --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  --env-file /srv/g1/.env \
  -v /srv/g1/hf-cache/hub:/hf-cache/hub:ro \
  g1-api
```
(Les options `-d`, `--restart unless-stopped`, `-p 127.0.0.1:8000:8000`, `--env-file`, `-v …:ro` sont standard Docker : non revérifiées dans la doc ici.)
Attendre ≈ 50 s, puis : `curl -s http://127.0.0.1:8000/health`.

## 6. Caddy (vérifié, https://caddyserver.com/docs/install)
```bash
sudo apt install --yes debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo chmod o+r /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```
Le paquet démarre Caddy comme service systemd `caddy` (vérifié). Fichier de config : `/etc/caddy/Caddyfile` (vérifié, https://caddyserver.com/docs/running).

Copier `deploy/Caddyfile` (depuis le PC : `scp deploy/Caddyfile <user>@<IP>:/tmp/`), puis :
```bash
sudo cp /tmp/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy      # vérifié
systemctl status caddy           # vérifié
journalctl -u caddy --no-pager | less +G   # vérifié (logs)
```
HTTPS automatique : le certificat est obtenu au premier accès si le DNS pointe déjà sur le VPS et que 80/443 sont ouverts (comportement par défaut de Caddy ; **non revérifié** sur la page lue ici).

**X-Forwarded-For (vérifié, doc reverse_proxy)** : Caddy ignore par défaut les valeurs envoyées par le client. L'API prend la dernière entrée avec `BEHIND_PROXY=1`. Si un jour Cloudflare passe en mode proxy (nuage orange), la doc avertit que l'usurpation reste possible sans réglage supplémentaire : garder « DNS only ».

## 7. Tests depuis l'extérieur
```bash
curl -i https://api.aymenahmedfouatih.com/health
```
Puis /ask juste, refus hors sujet, limite par visiteur (10/jour), redémarrage du serveur (`sudo reboot`) et vérification que le conteneur remonte seul. Tag `v2.0-prod` ensuite.
