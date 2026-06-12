# AubeVideo — API REST v1

Base URL : `https://video.aubeetoilee.com/api/v1`

Format : JSON. Authentification : `Authorization: Bearer av_xxx`. CSRF non
nécessaire pour les requêtes avec Bearer (les tokens API ne sont pas envoyés
automatiquement par le navigateur).

## Authentification

### `POST /auth/login`
Auth PAM partagée écosystème L'Aube Étoilée. Si 2FA actif sur le compte,
fournir aussi le code.

```json
// Request
{ "username": "alice", "password": "•••", "platform": "android",
  "device": "Pixel 8 Pro", "otp": "123456" }

// Response 200
{ "token": "av_xxx...", "user": { "id": 12, "username": "alice",
  "display_name": "Alice", "avatar": "/avatar/alice" } }
```

Erreurs :
- `400 identifiants requis`
- `401 identifiants invalides`
- `401 code 2FA requis` (avec `"totp_required": true`)
- `403 compte suspendu`

### `POST /auth/logout`
Révoque le token courant.

### `POST /auth/logout-all`
Révoque tous les tokens du compte.

### `GET /auth/me`
Renvoie le profil de l'utilisateur authentifié.

### `GET /auth/tokens`
Liste les sessions actives (autres appareils).

## Méta

### `GET /health`
`{ "ok": true, "service": "aubevideo", "version": "v1" }`

### `GET /config`
Renvoie config publique : catégories, limites d'upload, branding.

## Feeds

### `GET /feed?category=Musique&page=1&per_page=24`
Feed d'accueil (hors Shorts).

### `GET /trending`
Top vues récentes, hors Shorts.

### `GET /shorts`
Flux vertical de Shorts.

### `GET /subscriptions` *(auth)*
Vidéos des chaînes auxquelles l'utilisateur est abonné.

### `GET /recommended` *(auth optionnel)*
Recommandations personnalisées (catégories préférées × top non vues).

### `GET /discover` *(auth optionnel)*
Multi-sections de découverte :

```json
[
  { "key": "continue", "title": "Reprendre", "videos": [...] },
  { "key": "subscriptions", "title": "De vos abonnements", "videos": [...] },
  { "key": "foryou", "title": "Pour vous", "videos": [...] },
  { "key": "trending", "title": "Tendances", "videos": [...] }
]
```

### `GET /emerging-creators`
Créateurs émergents (moins de 60 jours, engagement élevé).

## Recherche

### `GET /search?q=python&sort=relevance|date|views&page=1`
Renvoie `{ "videos": [...], "channels": [...] }`.

### `GET /suggest?q=pyth`
Suggestions d'auto-complétion (titres uniques, max 8).

## Vidéo

### `GET /videos/{id}`
Détail complet : description, chapitres, sous-titres, qualités disponibles,
état utilisateur (réaction, abonnement, watch later).

### `GET /videos/{id}/suggestions`
Suggestions latérales (même catégorie + même chaîne).

### `POST /videos/{id}/view`
Enregistre une vue (idempotent côté serveur).

### `POST /videos/{id}/progress`
```json
{ "seconds": 142 }
```
Met à jour la position de lecture (sync mobile / web).

### `POST /videos/{id}/react`
```json
{ "reaction": "like" }   // ou "dislike", ou null pour retirer
```
Réponse : `{ "likes": 42, "dislikes": 3, "reaction": "like" }`

### `GET /videos/{id}/comments?sort=top|recent&page=1`
Liste paginée de commentaires racines.

### `POST /videos/{id}/comments` *(auth)*
```json
{ "content": "Super vidéo !", "parent_id": null }
```

### `GET /comments/{id}/replies`
Réponses à un commentaire.

### `POST /comments/{id}/like` *(auth)*
Toggle like.

## Chaînes

### `GET /channels/{username}`
Profil + dernières vidéos publiques.

### `POST /channels/{id}/subscribe` *(auth)*
Toggle abonnement. Réponse : `{ "subscribed": true, "count": 4523 }`.

### `GET /me/subscriptions` *(auth)*
Liste de mes chaînes suivies.

## Bibliothèque

### `GET /me/watch-later` *(auth)*
### `POST /me/watch-later/{id}` *(auth)*
### `DELETE /me/watch-later/{id}` *(auth)*

### `GET /me/history?page=1` *(auth)*
Historique de lecture avec `watched_at` + `progress_seconds`.

### `DELETE /me/history` *(auth)*
Efface tout l'historique.

### `GET /me/playlists` *(auth)*
### `POST /me/playlists` *(auth)*
```json
{ "title": "Ma playlist", "visibility": "public", "description": "" }
```
### `GET /playlists/{id}`
Détail public (ou privé si propriétaire).

### `POST /me/playlists/{pid}/videos/{vid}` *(auth)*
### `DELETE /me/playlists/{pid}/videos/{vid}` *(auth)*

## Notifications & Push

### `GET /me/notifications` *(auth)*
### `POST /me/notifications/read` *(auth)*
### `GET /me/notifications/unread-count` *(auth)*

### `POST /me/push/register` *(auth)*
Enregistre un device FCM (Android) / APNs (iOS) / Web Push.
```json
{ "token": "fcm_xxx", "platform": "android", "device": "Pixel 8" }
```
### `POST /me/push/unregister` *(auth)*
```json
{ "token": "fcm_xxx" }
```

## Préférences

### `GET /me/preferences` *(auth)*
### `PUT /me/preferences` *(auth)*
```json
{
  "theme": "dark|light|auto",
  "autoplay": true,
  "default_quality": "auto|360p|480p|720p|1080p",
  "language": "fr",
  "safe_mode": false,
  "background_play": true
}
```

## Studio

### `GET /me/videos` *(auth)*
Mes vidéos + stats agrégées.

### `PATCH /videos/{id}` *(auth, propriétaire)*
Champs modifiables : `title`, `description`, `visibility`, `category`, `tags`.

### `DELETE /videos/{id}` *(auth, propriétaire)*

### `POST /upload` *(auth, multipart/form-data)*
Champs : `video` (fichier), `title`, `description`, `category`, `tags`,
`visibility`, `thumbnail` (optionnel).

## Live

### `GET /live`
Streams actifs (avec `viewers`, compte de spectateurs en temps réel).

### `GET /live/{username}/chat?after={id}&t={token}`
Chat du direct : messages publiés après l'id `after` + nombre de spectateurs.
Auth facultative ; `t` = jeton anonyme côté client (sert au comptage des
spectateurs). Le poll (toutes les ~3 s) vaut présence.

```json
{ "live": true, "viewers": 12,
  "messages": [{ "id": 41, "user_id": 7, "author": "Nico", "body": "Salut !" }],
  "deleted": [38] }
```

`live: false` si la chaîne n'est pas (ou plus) en direct. `deleted` liste les
ids retirés par la modération depuis `after` (à enlever de l'affichage).

### `POST /live/{username}/chat` 🔒
Publier un message. Corps : `{ "body": "texte" }` (300 caractères max).
Réponse `201` : le message sérialisé (comme ci-dessus). `404` si le direct
est terminé.

## Pagination

Les endpoints paginés acceptent `?page=N&per_page=K` (K plafonné à 60).
Réponse : `{ "page", "per_page", "items", "has_more" }`.

## Limites

| Ressource             | Limite                       |
|-----------------------|------------------------------|
| Vidéo upload          | 2 Go                         |
| Quota utilisateur     | 10 Go par défaut             |
| Rate limit progress   | 120/min                      |
| Rate limit réactions  | 30/min                       |
| Rate limit commentaires | 20/min                     |

## CORS

L'API renvoie `Access-Control-Allow-Origin` selon `AUBEVIDEO_CORS_ORIGINS`
(par défaut `*`). Headers autorisés : `Authorization, Content-Type, X-CSRF-Token`.
Méthodes : `GET, POST, PUT, PATCH, DELETE, OPTIONS`.
