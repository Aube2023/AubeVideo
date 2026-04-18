# AubeVideo

Plateforme de partage de vidéos francophone de l'écosystème **L'Aube Étoilée** — alternative souveraine à YouTube.

![Port](https://img.shields.io/badge/port-5017-e8b84a) ![Stack](https://img.shields.io/badge/stack-Flask%20%2B%20PostgreSQL-3a5f9e) ![Auth](https://img.shields.io/badge/auth-PAM%20SSO-success)

## Fonctionnalités

- 🎬 **Upload vidéos** jusqu'à 2 Go (MP4, WebM, MOV, MKV, AVI, M4V, OGV)
- 📺 **Lecteur HTML5** avec streaming progressif (HTTP Range)
- 👤 **Profils / chaînes** avec avatar, bio, bannière, compteur d'abonnés
- 🔔 **Abonnements** et fil d'abonnements
- 👍 **Likes / dislikes / commentaires** (avec réponses)
- 🕒 **Historique** de visionnage
- 🔍 **Recherche** vidéos + chaînes (titre, description, tags, nom)
- 📈 **Tendances** (tri par vues)
- 🎨 **Catégories** (14 par défaut, 100 % francophones)
- 🛠️ **Studio créateur** (stats, édition, suppression, visibilité)
- 🔒 **Visibilité** : publique / non-répertoriée / privée
- 🌐 **Auth PAM partagée** avec AubeDocs, AubeDrive, AubeData, AubeMail, etc.

## Stack

| Composant | Choix |
|-----------|-------|
| Backend | Flask 3 + Gunicorn |
| DB | PostgreSQL 14+ |
| Auth | PAM (python-pam) — SSO système Linux |
| Stockage vidéos | Filesystem `/var/www/aubevideo/uploads/{user_id}/` |
| Streaming | HTTP Range (support seek, bandwidth adaptation) |
| Front | Templates Jinja2 + CSS/JS vanilla (pas de framework) |
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
