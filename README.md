# AubeVideo

Plateforme de partage de vidéos francophone de l'écosystème **L'Aube Étoilée** — alternative souveraine à YouTube.

![Port](https://img.shields.io/badge/port-5017-e8b84a) ![Stack](https://img.shields.io/badge/stack-Flask%20%2B%20PostgreSQL-3a5f9e) ![Auth](https://img.shields.io/badge/auth-email%2Fmdp%20%2B%20PAM%20SSO-success) ![Deploy](https://img.shields.io/badge/deploy-Docker%20%7C%20Render-2563eb)

## 🚀 Mettre en ligne (obtenir le lien prod)

AubeVideo est livré clé en main pour le cloud. **Inscription self-service** (e-mail +
mot de passe, comme YouTube) — n'importe qui peut créer un compte, plus besoin de
comptes système.

### Option A — Render, déploiement en 1 clic (gratuit, ~5 min)

1. Pousser ce repo sur GitHub (déjà fait : `Aube2023/AubeVideo`).
2. Cliquer : **https://render.com/deploy?repo=https://github.com/Aube2023/AubeVideo**
3. Render lit [`render.yaml`](./render.yaml), provisionne PostgreSQL + le web service,
   applique le schéma, et publie l'app. Lien final : `https://aubevideo.onrender.com`.

> Le plan gratuit suffit pour une démo (stockage éphémère). Pour de la vraie prod :
> décommenter le bloc `disk` dans `render.yaml` + passer le plan à `starter`, ou
> brancher un stockage objet (S3 / Cloudflare R2).

### Option B — Docker, auto-hébergé sur ton VPS (une commande)

```bash
git clone https://github.com/Aube2023/AubeVideo.git && cd AubeVideo
export DB_PASSWORD="un-mot-de-passe-fort" AUBEVIDEO_SECRET="$(openssl rand -hex 32)"
docker compose up -d --build
# App sur http://localhost:8080 — mettre Caddy/nginx + TLS devant pour le domaine public
```

Met le tout derrière `video.aubeetoilee.com` (A → ton IP) avec Caddy ou le
[`nginx.conf.example`](./nginx.conf.example) + certbot.

## Fonctionnalités

### Plateforme web
- 🎬 **Upload vidéos** jusqu'à 2 Go (MP4, WebM, MOV, MKV, AVI, M4V, OGV)
- 📺 **Lecteur HTML5** avec streaming progressif (HTTP Range)
- 👤 **Profils / chaînes** avec avatar, bio, bannière, compteur d'abonnés
- 🔔 **Abonnements**, **notifications** in-app + push web (VAPID)
- 👍 **Likes / dislikes / commentaires** (avec réponses, épinglage, ❤ par l'auteur)
- 🕒 **Historique** de visionnage + reprise automatique (cross-device)
- 🔍 **Recherche** vidéos + chaînes (titre, description, tags, nom) + suggestions
- 📈 **Tendances** (vues / récence, gravity 1.5)
- 🎯 **Sections « Pour vous »** : continuer, abonnements, recommandé, tendances
- 🎨 **Catégories** (14 par défaut, 100 % francophones)
- 🛠️ **Studio créateur** (stats, édition, suppression, visibilité, sous-titres)
- 🔒 **Visibilité** : publique / non-répertoriée / privée
- 🌐 **Auth PAM partagée** + **2FA TOTP**
- 💸 **Tip jar** Stripe pour soutenir les créateurs
- 📡 **Live streams** (RTMP + HLS)
- ⚡ **Shorts** (vertical ≤ 60s)
- 🎚️ **Transcoding** multi-qualités (360p / 480p / 720p) en arrière-plan
- 🌓 **Thème clair / sombre / système** (nouveau v3)
- 🎭 **Mode théâtre, mini-player, picture-in-picture, raccourcis clavier** (v3)
- 🧭 **Chapitres** auto-détectés depuis la description (v3)
- ✨ **Hover preview** sur les vignettes (v3)
- 🔐 **CSRF, rate limiting, headers sécurité, ban admin, modération**

### API REST v1 (mobile + intégrations)
- 🔑 **Auth Bearer tokens** (création via `/api/v1/auth/login`)
- 📦 **48 endpoints** couvrant : feeds, vidéos, commentaires, abonnements,
  playlists, watch later, historique, notifications, push, préférences, upload, live
- 🌍 **CORS** configurable (`AUBEVIDEO_CORS_ORIGINS`)
- 📖 Documentation complète : [`API.md`](./API.md)

### App Android native ([`android/`](./android/))
- ⚙️ **Kotlin 2.0 + Jetpack Compose Material 3**
- 🎬 **Media3 / ExoPlayer** : adaptive streaming, sous-titres, chapitres
- 📲 **Background playback + Picture-in-Picture**
- 🔔 **Push FCM**, deep linking `/watch/{id}` et `/c/{username}`
- 🎨 **Thème** sombre / clair / système avec couleurs Aube
- 📜 Voir [`android/README.md`](./android/README.md)

## Stack

| Composant | Choix |
|-----------|-------|
| Backend | Flask 3 + Gunicorn |
| DB | PostgreSQL 14+ (auto-détecte `DATABASE_URL`) |
| Auth | **Inscription e-mail/mot de passe** (hash Werkzeug) + PAM SSO en option |
| API mobile | REST v1 JSON + Bearer tokens (`/api/v1/...`) |
| Stockage vidéos | Filesystem `/var/www/aubevideo/uploads/{user_id}/` |
| Streaming | HTTP Range (support seek, bandwidth adaptation) |
| Transcoding | FFmpeg en arrière-plan (queue thread) |
| Front web | Templates Jinja2 + CSS/JS vanilla, thèmes clair/sombre |
| App Android | Kotlin 2.0 + Compose Material 3 + Media3 |
| Port | **5017** (5014 pris par AubeNews) |
| Domaine | `video.aubeetoilee.com` (A → 155.138.136.149) |

## Installation locale (dev)

```bash
git clone https://github.com/Aube2023/AubeVideo.git
cd AubeVideo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PostgreSQL
sudo -u postgres psql -c "CREATE USER aubevideo_user WITH PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE aubevideo OWNER aubevideo_user;"

cp .env.example .env
# édite .env avec les vrais identifiants

python app.py
```

Ouvre http://localhost:5017

## Déploiement production (VPS 155.138.136.149)

```bash
# 1. Code
sudo mkdir -p /var/www/aubevideo
sudo chown www-data:www-data /var/www/aubevideo
cd /var/www/aubevideo
sudo -u www-data git clone https://github.com/Aube2023/AubeVideo.git .

# 2. Dépendances
sudo -u www-data python3 -m venv .venv
sudo -u www-data .venv/bin/pip install -r requirements.txt

# 3. DB
sudo -u postgres createuser -P aubevideo_user
sudo -u postgres createdb aubevideo -O aubevideo_user
sudo -u postgres psql aubevideo < schema.sql

# 4. Config
sudo -u www-data cp .env.example .env
sudo -u www-data nano .env   # remplir les variables

sudo mkdir -p /var/log/aubevideo
sudo chown www-data:www-data /var/log/aubevideo

# 5. Service systemd
sudo cp aubevideo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aubevideo
sudo systemctl status aubevideo

# 6. Nginx + DNS + SSL
sudo cp nginx.conf.example /etc/nginx/sites-available/aubevideo
sudo ln -s /etc/nginx/sites-available/aubevideo /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Ajouter A record video.aubeetoilee.com -> 155.138.136.149 dans Squarespace

sudo certbot --nginx -d video.aubeetoilee.com
```

## Écosystème L'Aube Étoilée

Auth PAM partagée, jamais reset les mots de passe Linux.

| Service | Port | Domaine |
|---------|------|---------|
| AubeCRM | 5007 | crm.aubeetoilee.com |
| AubeDocs | 5008 | docs.aubeetoilee.com |
| AubeDrive | 5011 | drive.aubeetoilee.com |
| AubeData | 5012 | data.aubeetoilee.com |
| AubeDriver | 5013 | driver.aubeetoilee.com |
| AubeNews | 5014 | news.aubeetoilee.com |
| AubeForms | 5015 | forms.aubeetoilee.com |
| AubeMusic | 5016 | music.aubeetoilee.com |
| **AubeVideo** | **5017** | **video.aubeetoilee.com** |

## Licence

© L'Aube Étoilée — Tous droits réservés.
