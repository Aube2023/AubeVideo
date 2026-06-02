"""AubeVideo - API REST JSON v1 pour clients mobiles (Android, iOS) et SPA.

Auth : Bearer token (Authorization: Bearer av_xxx). Obtenu via /api/v1/auth/login.
Tous les endpoints ci-dessous sont préfixés par /api/v1.

Conventions :
- Erreurs : {"error": "message"} + code HTTP approprié
- Pagination : ?page=1&per_page=24
- Timestamps : ISO 8601 UTC
- IDs : entiers
- URLs ressources : chemins relatifs au domaine (ex: /stream/123)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, g, url_for

from db import db_cursor, fetch_video, VISIBILITIES, normalize_visibility, ensure_user
from auth import pam_authenticate
from api_tokens import (
    create_token, revoke_token, revoke_all_for_user,
    api_auth_required, api_auth_optional, list_tokens,
)
import notify
import totp
import recommendations


api_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ============================================================
# Sérialisation
# ============================================================
def _iso(dt) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)


def video_dto(v: Dict[str, Any], detailed: bool = False) -> Dict[str, Any]:
    out = {
        "id": v["id"],
        "title": v["title"],
        "thumbnail": url_for("thumbnail", video_id=v["id"]),
        "stream": url_for("stream", video_id=v["id"]),
        "duration": v.get("duration") or 0,
        "views": v.get("views") or 0,
        "likes": v.get("likes_count") or 0,
        "dislikes": v.get("dislikes_count") or 0,
        "comments": v.get("comments_count") or 0,
        "category": v.get("category"),
        "tags": [t.strip() for t in (v.get("tags") or "").split(",") if t.strip()],
        "is_short": bool(v.get("is_short")),
        "is_live": bool(v.get("is_live")),
        "visibility": v.get("visibility"),
        "age_restricted": bool(v.get("age_restricted")),
        "created_at": _iso(v.get("created_at")),
        "qualities": [q for q in (v.get("qualities") or "").split(",") if q],
        "channel": {
            "id": v.get("user_id"),
            "username": v.get("username"),
            "display_name": v.get("display_name"),
            "avatar": url_for("avatar", username=v["username"]) if v.get("username") else None,
            "subscribers": v.get("subscriber_count") or 0,
        } if v.get("username") else None,
    }
    if detailed:
        out["description"] = v.get("description") or ""
        out["mime_type"] = v.get("mime_type")
        out["file_size"] = v.get("file_size") or 0
    return out


def channel_dto(u: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": u["id"],
        "username": u["username"],
        "display_name": u["display_name"],
        "bio": u.get("bio") or "",
        "avatar": url_for("avatar", username=u["username"]),
        "banner": url_for("banner", username=u["username"]) if u.get("banner_url") else None,
        "subscribers": u.get("subscriber_count") or 0,
        "total_views": u.get("total_views") or 0,
        "is_verified": bool(u.get("is_verified")),
        "is_admin": bool(u.get("is_admin")),
        "created_at": _iso(u.get("created_at")),
    }


def comment_dto(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": c["id"],
        "video_id": c.get("video_id"),
        "parent_id": c.get("parent_id"),
        "content": c["content"],
        "likes": c.get("likes_count") or 0,
        "is_pinned": bool(c.get("is_pinned")),
        "hearted": bool(c.get("hearted")),
        "reply_count": c.get("reply_count") or 0,
        "created_at": _iso(c.get("created_at")),
        "author": {
            "username": c.get("username"),
            "display_name": c.get("display_name"),
            "avatar": url_for("avatar", username=c["username"]) if c.get("username") else None,
        },
    }


def _page(per_default: int = 24, per_max: int = 60):
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        per = min(per_max, max(1, int(request.args.get("per_page", per_default))))
    except ValueError:
        per = per_default
    return page, per, (page - 1) * per


# ============================================================
# Meta / santé / configuration client
# ============================================================
@api_bp.route("/health")
def health():
    return jsonify({"ok": True, "service": "aubevideo", "version": "v1"})


@api_bp.route("/config")
def config():
    """Renvoie la config publique côté client (catégories, limites, branding)."""
    from app import CATEGORIES, MAX_VIDEO_SIZE
    return jsonify({
        "categories": CATEGORIES,
        "max_video_size": MAX_VIDEO_SIZE,
        "allowed_video": ["mp4", "webm", "mov", "mkv", "avi", "m4v", "ogv"],
        "allowed_image": ["jpg", "jpeg", "png", "gif", "webp"],
        "visibilities": list(VISIBILITIES),
        "brand": {
            "name": "AubeVideo",
            "primary": "#3a5f9e",
            "accent": "#e8b84a",
            "ecosystem": "L'Aube Étoilée",
        },
    })


# ============================================================
# Authentification
# ============================================================
@api_bp.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    device = (data.get("device") or "").strip()[:128]
    platform = (data.get("platform") or "").strip()[:32]
    if not username or not password:
        return jsonify({"error": "identifiants requis"}), 400
    if not pam_authenticate(username, password):
        return jsonify({"error": "identifiants invalides"}), 401
    uid = ensure_user(username, display_name=username)
    with db_cursor() as cur:
        cur.execute(
            "SELECT is_banned, totp_enabled, display_name, avatar_url FROM users WHERE id = %s",
            (uid,),
        )
        row = cur.fetchone()
    if not row:
        return jsonify({"error": "utilisateur introuvable"}), 404
    if row["is_banned"]:
        return jsonify({"error": "compte suspendu"}), 403
    if row["totp_enabled"]:
        otp = (data.get("otp") or "").strip()
        if not otp:
            return jsonify({"error": "code 2FA requis", "totp_required": True}), 401
        with db_cursor() as cur:
            cur.execute("SELECT totp_secret FROM users WHERE id = %s", (uid,))
            r = cur.fetchone()
        if not r or not totp.verify(r["totp_secret"], otp):
            return jsonify({"error": "code 2FA invalide", "totp_required": True}), 401
    token = create_token(uid, device=device, platform=platform)
    return jsonify({
        "token": token,
        "user": {
            "id": uid,
            "username": username,
            "display_name": row["display_name"],
            "avatar": url_for("avatar", username=username),
        },
    })


@api_bp.route("/auth/logout", methods=["POST"])
@api_auth_required
def auth_logout():
    tok = request.headers.get("Authorization", "")
    if tok.lower().startswith("bearer "):
        revoke_token(tok.split(" ", 1)[1].strip())
    return jsonify({"ok": True})


@api_bp.route("/auth/logout-all", methods=["POST"])
@api_auth_required
def auth_logout_all():
    n = revoke_all_for_user(g.user_id)
    return jsonify({"revoked": n})


@api_bp.route("/auth/me")
@api_auth_required
def auth_me():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (g.user_id,))
        u = cur.fetchone()
    if not u:
        return jsonify({"error": "utilisateur introuvable"}), 404
    return jsonify(channel_dto(u))


@api_bp.route("/auth/tokens")
@api_auth_required
def auth_tokens():
    rows = list_tokens(g.user_id)
    return jsonify([{
        "id": r["id"],
        "device": r["device"],
        "platform": r["platform"],
        "created_at": _iso(r["created_at"]),
        "last_used_at": _iso(r["last_used_at"]),
        "expires_at": _iso(r["expires_at"]),
    } for r in rows])


# ============================================================
# Feed / découverte
# ============================================================
@api_bp.route("/feed")
@api_auth_optional
def feed():
    """Feed accueil — catégorie optionnelle + paginé."""
    category = request.args.get("category")
    page, per, offset = _page()
    params: List[Any] = []
    sql = """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
             FROM videos v JOIN users u ON v.user_id = u.id
             WHERE v.visibility = 'public' AND v.is_removed = FALSE
                   AND v.is_short = FALSE"""
    if category and category != "Toutes":
        sql += " AND v.category = %s"
        params.append(category)
    sql += " ORDER BY v.created_at DESC LIMIT %s OFFSET %s"
    params.extend([per, offset])
    with db_cursor() as cur:
        cur.execute(sql, params)
        videos = cur.fetchall()
    return jsonify({
        "page": page,
        "per_page": per,
        "items": [video_dto(v) for v in videos],
        "has_more": len(videos) == per,
    })


@api_bp.route("/trending")
def trending():
    """Top vues sur 7 jours (fallback all-time si pas assez)."""
    page, per, offset = _page(per_default=24)
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
                     AND v.is_short = FALSE
               ORDER BY v.views DESC, v.created_at DESC
               LIMIT %s OFFSET %s""",
            (per, offset),
        )
        videos = cur.fetchall()
    return jsonify({"page": page, "per_page": per, "items": [video_dto(v) for v in videos]})


@api_bp.route("/shorts")
def shorts_list():
    """Flux de Shorts."""
    page, per, offset = _page(per_default=20, per_max=40)
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
                     AND v.is_short = TRUE
               ORDER BY v.created_at DESC LIMIT %s OFFSET %s""",
            (per, offset),
        )
        videos = cur.fetchall()
    return jsonify({"page": page, "per_page": per, "items": [video_dto(v) for v in videos]})


@api_bp.route("/subscriptions")
@api_auth_required
def subscriptions_feed():
    page, per, offset = _page()
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v
               JOIN users u ON v.user_id = u.id
               JOIN subscriptions s ON s.channel_id = u.id
               WHERE s.subscriber_id = %s AND v.visibility = 'public'
                     AND v.is_removed = FALSE
               ORDER BY v.created_at DESC LIMIT %s OFFSET %s""",
            (g.user_id, per, offset),
        )
        videos = cur.fetchall()
    return jsonify({"page": page, "per_page": per, "items": [video_dto(v) for v in videos]})


@api_bp.route("/discover")
@api_auth_optional
def discover():
    """Découverte multi-sections (sections : reprendre, abonnements, pour vous, tendances)."""
    sections = recommendations.discover_sections(g.user_id)
    return jsonify([
        {
            "key": s["key"],
            "title": s["title"],
            "videos": [video_dto(v) for v in s["videos"]],
        } for s in sections
    ])


@api_bp.route("/emerging-creators")
def emerging_creators():
    """Liste de créateurs émergents (engagement / récence)."""
    rows = recommendations.emerging_creators(limit=12)
    return jsonify([channel_dto(r) for r in rows])


@api_bp.route("/recommended")
@api_auth_optional
def recommended():
    """Recommandations personnalisées si connecté, mix populaire sinon."""
    page, per, offset = _page()
    uid = g.user_id
    with db_cursor() as cur:
        if uid:
            # Catégories préférées (historique récent)
            cur.execute(
                """SELECT v.category, COUNT(*) AS c
                   FROM watch_history h JOIN videos v ON h.video_id = v.id
                   WHERE h.user_id = %s AND h.watched_at > NOW() - INTERVAL '30 days'
                   GROUP BY v.category ORDER BY c DESC LIMIT 3""",
                (uid,),
            )
            top_cats = [r["category"] for r in cur.fetchall() if r["category"]]
            if top_cats:
                cur.execute(
                    """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
                       FROM videos v JOIN users u ON v.user_id = u.id
                       WHERE v.visibility = 'public' AND v.is_removed = FALSE
                             AND v.is_short = FALSE
                             AND v.category = ANY(%s)
                             AND v.id NOT IN (
                                SELECT video_id FROM watch_history WHERE user_id = %s
                             )
                       ORDER BY v.views DESC, v.created_at DESC
                       LIMIT %s OFFSET %s""",
                    (top_cats, uid, per, offset),
                )
                videos = cur.fetchall()
                if videos:
                    return jsonify({
                        "page": page, "per_page": per,
                        "items": [video_dto(v) for v in videos],
                    })
        # Fallback : populaires
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
                     AND v.is_short = FALSE
               ORDER BY v.views DESC LIMIT %s OFFSET %s""",
            (per, offset),
        )
        videos = cur.fetchall()
    return jsonify({"page": page, "per_page": per, "items": [video_dto(v) for v in videos]})


# ============================================================
# Recherche
# ============================================================
@api_bp.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "relevance")
    page, per, offset = _page(per_default=20)
    if not q:
        return jsonify({"videos": [], "channels": []})
    like = f"%{q}%"
    order = {"date": "v.created_at DESC", "views": "v.views DESC"}.get(sort, "v.views DESC")
    with db_cursor() as cur:
        cur.execute(
            f"""SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
                FROM videos v JOIN users u ON v.user_id = u.id
                WHERE v.visibility = 'public' AND v.is_removed = FALSE
                  AND (v.title ILIKE %s OR v.description ILIKE %s
                       OR v.tags ILIKE %s OR u.username ILIKE %s
                       OR u.display_name ILIKE %s)
                ORDER BY {order} LIMIT %s OFFSET %s""",
            (like, like, like, like, like, per, offset),
        )
        videos = cur.fetchall()
        cur.execute(
            """SELECT id, username, display_name, avatar_url, banner_url,
                      subscriber_count, total_views, bio, is_verified, is_admin
               FROM users WHERE (username ILIKE %s OR display_name ILIKE %s)
                 AND is_banned = FALSE LIMIT 20""",
            (like, like),
        )
        channels = cur.fetchall()
    return jsonify({
        "page": page, "per_page": per,
        "videos": [video_dto(v) for v in videos],
        "channels": [channel_dto(c) for c in channels],
    })


@api_bp.route("/suggest")
def suggest():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    with db_cursor() as cur:
        cur.execute(
            """SELECT DISTINCT title FROM videos
               WHERE visibility = 'public' AND is_removed = FALSE
                 AND title ILIKE %s
               ORDER BY title LIMIT 8""",
            (like,),
        )
        rows = cur.fetchall()
    return jsonify([r["title"] for r in rows])


# ============================================================
# Détail vidéo
# ============================================================
@api_bp.route("/videos/<int:video_id>")
@api_auth_optional
def video_detail(video_id):
    with db_cursor() as cur:
        v = fetch_video(cur, video_id, with_user=True)
        if not v:
            return jsonify({"error": "introuvable"}), 404
        if v["visibility"] == "private" and v["user_id"] != g.user_id:
            return jsonify({"error": "interdit"}), 403

        uid = g.user_id
        user_reaction = None
        is_subscribed = False
        in_watch_later = False
        if uid:
            cur.execute(
                "SELECT reaction FROM video_reactions WHERE user_id = %s AND video_id = %s",
                (uid, video_id),
            )
            r = cur.fetchone()
            user_reaction = r["reaction"] if r else None
            cur.execute(
                "SELECT 1 FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
                (uid, v["user_id"]),
            )
            is_subscribed = cur.fetchone() is not None
            cur.execute(
                "SELECT 1 FROM watch_later WHERE user_id = %s AND video_id = %s",
                (uid, video_id),
            )
            in_watch_later = cur.fetchone() is not None

        cur.execute(
            """SELECT id, lang, label, is_auto FROM captions
               WHERE video_id = %s ORDER BY created_at""",
            (video_id,),
        )
        captions = cur.fetchall()

        cur.execute(
            """SELECT start_seconds, title, position FROM chapters
               WHERE video_id = %s ORDER BY position, start_seconds""",
            (video_id,),
        )
        chapters = cur.fetchall()

    dto = video_dto(v, detailed=True)
    dto["user_reaction"] = user_reaction
    dto["is_subscribed"] = is_subscribed
    dto["in_watch_later"] = in_watch_later
    dto["captions"] = [{
        "id": c["id"], "lang": c["lang"], "label": c["label"],
        "url": url_for("caption", caption_id=c["id"]),
        "auto": bool(c["is_auto"]),
    } for c in captions]
    dto["chapters"] = [{
        "start": c["start_seconds"],
        "title": c["title"],
    } for c in chapters]
    return jsonify(dto)


@api_bp.route("/videos/<int:video_id>/suggestions")
def video_suggestions(video_id):
    """Suggestions latérales : même catégorie + même chaîne + populaires."""
    with db_cursor() as cur:
        cur.execute("SELECT category, user_id FROM videos WHERE id = %s", (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify([])
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
                 AND v.id <> %s AND (v.category = %s OR v.user_id = %s)
               ORDER BY v.views DESC LIMIT 20""",
            (video_id, v["category"], v["user_id"]),
        )
        rows = cur.fetchall()
    return jsonify([video_dto(r) for r in rows])


@api_bp.route("/videos/<int:video_id>/view", methods=["POST"])
@api_auth_optional
def register_view(video_id):
    """Enregistre une vue (1 par user/IP par 6h via DB)."""
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM videos WHERE id = %s AND is_removed = FALSE",
                    (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify({"error": "introuvable"}), 404
        cur.execute("UPDATE videos SET views = views + 1 WHERE id = %s", (video_id,))
        cur.execute("UPDATE users SET total_views = total_views + 1 WHERE id = %s",
                    (v["user_id"],))
        if g.user_id:
            cur.execute(
                """INSERT INTO watch_history (user_id, video_id) VALUES (%s, %s)""",
                (g.user_id, video_id),
            )
    return jsonify({"ok": True})


@api_bp.route("/videos/<int:video_id>/progress", methods=["POST"])
@api_auth_required
def save_progress(video_id):
    """Met à jour la position de lecture pour reprise."""
    data = request.get_json(silent=True) or {}
    try:
        seconds = max(0, int(data.get("seconds") or 0))
    except (TypeError, ValueError):
        return jsonify({"error": "seconds invalide"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE watch_history SET progress_seconds = %s, watched_at = CURRENT_TIMESTAMP
               WHERE id = (SELECT id FROM watch_history
                           WHERE user_id = %s AND video_id = %s
                           ORDER BY watched_at DESC LIMIT 1)""",
            (seconds, g.user_id, video_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO watch_history (user_id, video_id, progress_seconds)
                   VALUES (%s, %s, %s)""",
                (g.user_id, video_id, seconds),
            )
    return jsonify({"ok": True})


# ============================================================
# Reactions / commentaires / abos
# ============================================================
@api_bp.route("/videos/<int:video_id>/react", methods=["POST"])
@api_auth_required
def react(video_id):
    data = request.get_json(silent=True) or {}
    reaction = data.get("reaction")
    if reaction not in ("like", "dislike", None):
        return jsonify({"error": "reaction invalide"}), 400
    uid = g.user_id
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT reaction FROM video_reactions WHERE user_id = %s AND video_id = %s",
            (uid, video_id),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                "DELETE FROM video_reactions WHERE user_id = %s AND video_id = %s",
                (uid, video_id),
            )
            col = "likes_count" if existing["reaction"] == "like" else "dislikes_count"
            cur.execute(
                f"UPDATE videos SET {col} = GREATEST({col}-1,0) WHERE id = %s",
                (video_id,),
            )
        if reaction and (not existing or existing["reaction"] != reaction):
            cur.execute(
                "INSERT INTO video_reactions (user_id, video_id, reaction) VALUES (%s,%s,%s)",
                (uid, video_id, reaction),
            )
            col = "likes_count" if reaction == "like" else "dislikes_count"
            cur.execute(
                f"UPDATE videos SET {col} = {col} + 1 WHERE id = %s",
                (video_id,),
            )
        cur.execute(
            "SELECT likes_count, dislikes_count FROM videos WHERE id = %s",
            (video_id,),
        )
        counts = cur.fetchone()
    new_reaction = reaction if (reaction and (not existing or existing["reaction"] != reaction)) else None
    return jsonify({
        "likes": counts["likes_count"],
        "dislikes": counts["dislikes_count"],
        "reaction": new_reaction,
    })


@api_bp.route("/videos/<int:video_id>/comments")
def list_comments(video_id):
    page, per, offset = _page(per_default=30, per_max=100)
    sort = request.args.get("sort", "top")
    order = "c.likes_count DESC, c.created_at DESC" if sort == "top" else "c.created_at DESC"
    with db_cursor() as cur:
        cur.execute(
            f"""SELECT c.*, u.username, u.display_name, u.avatar_url,
                       (SELECT COUNT(*) FROM comments r WHERE r.parent_id = c.id) AS reply_count
                FROM comments c JOIN users u ON c.user_id = u.id
                WHERE c.video_id = %s AND c.parent_id IS NULL AND c.is_removed = FALSE
                ORDER BY c.is_pinned DESC, {order}
                LIMIT %s OFFSET %s""",
            (video_id, per, offset),
        )
        rows = cur.fetchall()
    return jsonify({
        "page": page, "per_page": per,
        "items": [comment_dto(r) for r in rows],
    })


@api_bp.route("/videos/<int:video_id>/comments", methods=["POST"])
@api_auth_required
def add_comment(video_id):
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id")
    if not content or len(content) > 5000:
        return jsonify({"error": "contenu invalide"}), 400
    uid = g.user_id
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO comments (video_id, user_id, parent_id, content)
               VALUES (%s, %s, %s, %s) RETURNING id, created_at""",
            (video_id, uid, parent_id, content),
        )
        c = cur.fetchone()
        cur.execute(
            "UPDATE videos SET comments_count = comments_count + 1 WHERE id = %s",
            (video_id,),
        )
        cur.execute(
            "SELECT username, display_name, avatar_url FROM users WHERE id = %s",
            (uid,),
        )
        u = cur.fetchone()
        cur.execute(
            "SELECT user_id, title FROM videos WHERE id = %s", (video_id,)
        )
        vid_row = cur.fetchone()
        if vid_row and vid_row["user_id"] != uid:
            notify.notify_new_comment(
                cur, vid_row["user_id"], u["display_name"],
                video_id, vid_row["title"], content,
            )
    return jsonify({
        "id": c["id"],
        "content": content,
        "created_at": _iso(c["created_at"]),
        "author": {
            "username": u["username"],
            "display_name": u["display_name"],
            "avatar": url_for("avatar", username=u["username"]),
        },
    })


@api_bp.route("/comments/<int:comment_id>/replies")
def list_replies(comment_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT c.*, u.username, u.display_name, u.avatar_url
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.parent_id = %s AND c.is_removed = FALSE
               ORDER BY c.created_at ASC""",
            (comment_id,),
        )
        rows = cur.fetchall()
    return jsonify([comment_dto(r) for r in rows])


@api_bp.route("/comments/<int:comment_id>/like", methods=["POST"])
@api_auth_required
def like_comment(comment_id):
    uid = g.user_id
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT 1 FROM comment_likes WHERE user_id = %s AND comment_id = %s",
            (uid, comment_id),
        )
        exists = cur.fetchone() is not None
        if exists:
            cur.execute(
                "DELETE FROM comment_likes WHERE user_id = %s AND comment_id = %s",
                (uid, comment_id),
            )
            cur.execute(
                "UPDATE comments SET likes_count = GREATEST(likes_count-1,0) WHERE id = %s",
                (comment_id,),
            )
        else:
            cur.execute(
                "INSERT INTO comment_likes (user_id, comment_id) VALUES (%s, %s)",
                (uid, comment_id),
            )
            cur.execute(
                "UPDATE comments SET likes_count = likes_count + 1 WHERE id = %s",
                (comment_id,),
            )
        cur.execute("SELECT likes_count FROM comments WHERE id = %s", (comment_id,))
        count = cur.fetchone()["likes_count"]
    return jsonify({"liked": not exists, "count": count})


@api_bp.route("/channels/<int:channel_id>/subscribe", methods=["POST"])
@api_auth_required
def subscribe(channel_id):
    uid = g.user_id
    if uid == channel_id:
        return jsonify({"error": "auto-abonnement impossible"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT 1 FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
            (uid, channel_id),
        )
        exists = cur.fetchone() is not None
        if exists:
            cur.execute(
                "DELETE FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
                (uid, channel_id),
            )
            cur.execute(
                "UPDATE users SET subscriber_count = GREATEST(subscriber_count-1,0) WHERE id = %s",
                (channel_id,),
            )
            subscribed = False
        else:
            cur.execute(
                "INSERT INTO subscriptions (subscriber_id, channel_id) VALUES (%s, %s)",
                (uid, channel_id),
            )
            cur.execute(
                "UPDATE users SET subscriber_count = subscriber_count + 1 WHERE id = %s",
                (channel_id,),
            )
            cur.execute("SELECT display_name, username FROM users WHERE id = %s", (uid,))
            me = cur.fetchone()
            notify.notify_new_subscriber(cur, channel_id, me["display_name"], me["username"])
            subscribed = True
        cur.execute("SELECT subscriber_count FROM users WHERE id = %s", (channel_id,))
        count = cur.fetchone()["subscriber_count"]
    return jsonify({"subscribed": subscribed, "count": count})


# ============================================================
# Chaînes / profils
# ============================================================
@api_bp.route("/channels/<username>")
@api_auth_optional
def channel(username):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
        if not u:
            return jsonify({"error": "introuvable"}), 404
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.user_id = %s AND v.visibility = 'public' AND v.is_removed = FALSE
               ORDER BY v.created_at DESC LIMIT 60""",
            (u["id"],),
        )
        videos = cur.fetchall()
        is_subscribed = False
        if g.user_id and g.user_id != u["id"]:
            cur.execute(
                "SELECT 1 FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
                (g.user_id, u["id"]),
            )
            is_subscribed = cur.fetchone() is not None
    out = channel_dto(u)
    out["videos"] = [video_dto(v) for v in videos]
    out["is_subscribed"] = is_subscribed
    return out and jsonify(out)


@api_bp.route("/me/subscriptions")
@api_auth_required
def my_subscriptions():
    with db_cursor() as cur:
        cur.execute(
            """SELECT u.id, u.username, u.display_name, u.avatar_url, u.banner_url,
                      u.subscriber_count, u.total_views, u.is_verified, u.bio,
                      (SELECT MAX(created_at) FROM videos WHERE user_id = u.id) AS last_upload
               FROM subscriptions s JOIN users u ON s.channel_id = u.id
               WHERE s.subscriber_id = %s ORDER BY u.display_name""",
            (g.user_id,),
        )
        rows = cur.fetchall()
    return jsonify([channel_dto(r) for r in rows])


# ============================================================
# Watch later / history / playlists
# ============================================================
@api_bp.route("/me/watch-later")
@api_auth_required
def watch_later_list():
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM watch_later w JOIN videos v ON w.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE w.user_id = %s AND v.is_removed = FALSE
               ORDER BY w.added_at DESC""",
            (g.user_id,),
        )
        rows = cur.fetchall()
    return jsonify([video_dto(v) for v in rows])


@api_bp.route("/me/watch-later/<int:video_id>", methods=["POST", "DELETE"])
@api_auth_required
def watch_later_toggle(video_id):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT 1 FROM watch_later WHERE user_id = %s AND video_id = %s",
            (g.user_id, video_id),
        )
        exists = cur.fetchone() is not None
        if request.method == "DELETE" or exists:
            cur.execute(
                "DELETE FROM watch_later WHERE user_id = %s AND video_id = %s",
                (g.user_id, video_id),
            )
            return jsonify({"saved": False})
        cur.execute(
            "INSERT INTO watch_later (user_id, video_id) VALUES (%s, %s)",
            (g.user_id, video_id),
        )
    return jsonify({"saved": True})


@api_bp.route("/me/history")
@api_auth_required
def history_list():
    page, per, offset = _page(per_default=30)
    with db_cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (v.id) v.*, u.username, u.display_name, u.avatar_url,
                       u.subscriber_count, h.watched_at, h.progress_seconds
               FROM watch_history h JOIN videos v ON h.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE h.user_id = %s AND v.is_removed = FALSE
               ORDER BY v.id, h.watched_at DESC""",
            (g.user_id,),
        )
        rows = cur.fetchall()
    rows.sort(key=lambda r: r.get("watched_at") or datetime.min, reverse=True)
    rows = rows[offset:offset + per]
    out = []
    for v in rows:
        d = video_dto(v)
        d["watched_at"] = _iso(v.get("watched_at"))
        d["progress_seconds"] = v.get("progress_seconds") or 0
        out.append(d)
    return jsonify({"page": page, "per_page": per, "items": out})


@api_bp.route("/me/history", methods=["DELETE"])
@api_auth_required
def history_clear():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM watch_history WHERE user_id = %s", (g.user_id,))
    return jsonify({"ok": True})


@api_bp.route("/me/playlists")
@api_auth_required
def my_playlists():
    with db_cursor() as cur:
        cur.execute(
            """SELECT p.*, COUNT(pv.id) AS video_count
               FROM playlists p LEFT JOIN playlist_videos pv ON pv.playlist_id = p.id
               WHERE p.user_id = %s GROUP BY p.id ORDER BY p.created_at DESC""",
            (g.user_id,),
        )
        rows = cur.fetchall()
    return jsonify([{
        "id": p["id"], "title": p["title"],
        "description": p.get("description") or "",
        "visibility": p["visibility"],
        "video_count": p["video_count"],
        "created_at": _iso(p["created_at"]),
    } for p in rows])


@api_bp.route("/playlists/<int:playlist_id>")
@api_auth_optional
def playlist_detail(playlist_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT p.*, u.username, u.display_name FROM playlists p
               JOIN users u ON p.user_id = u.id WHERE p.id = %s""",
            (playlist_id,),
        )
        p = cur.fetchone()
        if not p:
            return jsonify({"error": "introuvable"}), 404
        if p["visibility"] == "private" and p["user_id"] != g.user_id:
            return jsonify({"error": "interdit"}), 403
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM playlist_videos pv JOIN videos v ON pv.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE pv.playlist_id = %s AND v.is_removed = FALSE
               ORDER BY pv.position, pv.added_at""",
            (playlist_id,),
        )
        videos = cur.fetchall()
    return jsonify({
        "id": p["id"], "title": p["title"],
        "description": p.get("description") or "",
        "visibility": p["visibility"],
        "owner": {"username": p["username"], "display_name": p["display_name"]},
        "videos": [video_dto(v) for v in videos],
    })


@api_bp.route("/me/playlists", methods=["POST"])
@api_auth_required
def create_playlist():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    visibility = normalize_visibility(data.get("visibility", "public"))
    description = (data.get("description") or "").strip()
    if not title:
        return jsonify({"error": "titre requis"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO playlists (user_id, title, description, visibility)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (g.user_id, title, description, visibility),
        )
        pid = cur.fetchone()["id"]
    return jsonify({"id": pid, "title": title})


@api_bp.route("/me/playlists/<int:playlist_id>/videos/<int:video_id>",
              methods=["POST", "DELETE"])
@api_auth_required
def playlist_toggle_video(playlist_id, video_id):
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM playlists WHERE id = %s", (playlist_id,))
        p = cur.fetchone()
        if not p or p["user_id"] != g.user_id:
            return jsonify({"error": "interdit"}), 403
        cur.execute(
            "SELECT 1 FROM playlist_videos WHERE playlist_id = %s AND video_id = %s",
            (playlist_id, video_id),
        )
        exists = cur.fetchone() is not None
        if request.method == "DELETE" or exists:
            cur.execute(
                "DELETE FROM playlist_videos WHERE playlist_id = %s AND video_id = %s",
                (playlist_id, video_id),
            )
            return jsonify({"in_playlist": False})
        cur.execute(
            "INSERT INTO playlist_videos (playlist_id, video_id) VALUES (%s, %s)",
            (playlist_id, video_id),
        )
    return jsonify({"in_playlist": True})


# ============================================================
# Notifications + push
# ============================================================
@api_bp.route("/me/notifications")
@api_auth_required
def notifications_list():
    items = notify.list_recent(g.user_id, limit=50)
    return jsonify([{
        "id": n["id"], "type": n["type"], "title": n["title"],
        "body": n["body"], "link": n["link"], "is_read": n["is_read"],
        "created_at": _iso(n["created_at"]),
    } for n in items])


@api_bp.route("/me/notifications/read", methods=["POST"])
@api_auth_required
def notifications_read():
    notify.mark_all_read(g.user_id)
    return jsonify({"ok": True})


@api_bp.route("/me/notifications/unread-count")
@api_auth_required
def notifications_unread():
    try:
        n = notify.unread_count(g.user_id)
    except Exception:
        n = 0
    return jsonify({"unread": n})


@api_bp.route("/me/push/register", methods=["POST"])
@api_auth_required
def push_register():
    """Enregistre un device push (FCM Android / APNs iOS)."""
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    platform = (data.get("platform") or "").strip()[:16]
    device = (data.get("device") or "").strip()[:128]
    if not token or platform not in ("android", "ios", "web"):
        return jsonify({"error": "paramètres invalides"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO push_devices (user_id, token, platform, device)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (token) DO UPDATE SET
                 user_id = EXCLUDED.user_id,
                 platform = EXCLUDED.platform,
                 device = EXCLUDED.device,
                 last_seen_at = CURRENT_TIMESTAMP""",
            (g.user_id, token, platform, device),
        )
    return jsonify({"ok": True})


@api_bp.route("/me/push/unregister", methods=["POST"])
@api_auth_required
def push_unregister():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token requis"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM push_devices WHERE token = %s AND user_id = %s",
                    (token, g.user_id))
    return jsonify({"ok": True})


# ============================================================
# Préférences utilisateur
# ============================================================
@api_bp.route("/me/preferences")
@api_auth_required
def get_prefs():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM user_preferences WHERE user_id = %s", (g.user_id,))
        p = cur.fetchone()
    if not p:
        return jsonify({
            "theme": "dark", "autoplay": True, "default_quality": "auto",
            "language": "fr", "safe_mode": False, "background_play": True,
        })
    return jsonify({
        "theme": p["theme"], "autoplay": p["autoplay"],
        "default_quality": p["default_quality"], "language": p["language"],
        "safe_mode": p["safe_mode"], "background_play": p["background_play"],
    })


@api_bp.route("/me/preferences", methods=["PUT"])
@api_auth_required
def set_prefs():
    data = request.get_json(silent=True) or {}
    theme = data.get("theme") or "dark"
    if theme not in ("dark", "light", "auto"):
        theme = "dark"
    language = (data.get("language") or "fr")[:8]
    default_quality = (data.get("default_quality") or "auto")[:16]
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO user_preferences
                  (user_id, theme, autoplay, default_quality, language, safe_mode, background_play)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id) DO UPDATE SET
                 theme = EXCLUDED.theme,
                 autoplay = EXCLUDED.autoplay,
                 default_quality = EXCLUDED.default_quality,
                 language = EXCLUDED.language,
                 safe_mode = EXCLUDED.safe_mode,
                 background_play = EXCLUDED.background_play,
                 updated_at = CURRENT_TIMESTAMP""",
            (g.user_id, theme,
             bool(data.get("autoplay", True)),
             default_quality, language,
             bool(data.get("safe_mode", False)),
             bool(data.get("background_play", True))),
        )
    return jsonify({"ok": True})


# ============================================================
# Studio / mes vidéos
# ============================================================
@api_bp.route("/me/videos")
@api_auth_required
def my_videos():
    with db_cursor() as cur:
        cur.execute(
            """SELECT * FROM videos WHERE user_id = %s AND is_removed = FALSE
               ORDER BY created_at DESC""",
            (g.user_id,),
        )
        rows = cur.fetchall()
        cur.execute(
            """SELECT COALESCE(SUM(views),0) AS total_views,
                      COUNT(*) AS total_videos,
                      COALESCE(SUM(likes_count),0) AS total_likes,
                      COALESCE(SUM(comments_count),0) AS total_comments
               FROM videos WHERE user_id = %s AND is_removed = FALSE""",
            (g.user_id,),
        )
        stats = cur.fetchone()
        cur.execute(
            "SELECT subscriber_count FROM users WHERE id = %s", (g.user_id,)
        )
        sub = cur.fetchone()
    return jsonify({
        "stats": {
            "subscribers": sub["subscriber_count"] if sub else 0,
            "total_views": stats["total_views"],
            "total_videos": stats["total_videos"],
            "total_likes": stats["total_likes"],
            "total_comments": stats["total_comments"],
        },
        "videos": [video_dto(v) for v in rows],
    })


@api_bp.route("/videos/<int:video_id>", methods=["PATCH"])
@api_auth_required
def update_video(video_id):
    data = request.get_json(silent=True) or {}
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM videos WHERE id = %s", (video_id,))
        row = cur.fetchone()
        if not row or row["user_id"] != g.user_id:
            return jsonify({"error": "interdit"}), 403
        updates, params = [], []
        if "title" in data:
            updates.append("title = %s"); params.append(data["title"][:255])
        if "description" in data:
            updates.append("description = %s"); params.append(data["description"][:10000])
        if "visibility" in data:
            updates.append("visibility = %s"); params.append(normalize_visibility(data["visibility"]))
        if "category" in data:
            updates.append("category = %s"); params.append(data["category"][:64])
        if "tags" in data:
            updates.append("tags = %s"); params.append(data["tags"][:500])
        if not updates:
            return jsonify({"error": "aucun champ"}), 400
        params.append(video_id)
        cur.execute(
            f"UPDATE videos SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            params,
        )
    return jsonify({"ok": True})


@api_bp.route("/videos/<int:video_id>", methods=["DELETE"])
@api_auth_required
def delete_video(video_id):
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM videos WHERE id = %s", (video_id,))
        row = cur.fetchone()
        if not row or row["user_id"] != g.user_id:
            return jsonify({"error": "interdit"}), 403
        cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
    return jsonify({"ok": True})


# ============================================================
# Upload (multipart simplifié pour mobile)
# ============================================================
@api_bp.route("/upload", methods=["POST"])
@api_auth_required
def upload_video():
    """Upload mobile (multipart/form-data). Réutilise la logique d'app.upload()."""
    from app import (
        allowed_file, ALLOWED_VIDEO_EXTS, ALLOWED_IMAGE_EXTS,
        user_dir_writable,
    )
    from media import probe_metadata, generate_thumbnail
    from PIL import Image
    import uuid, mimetypes
    import transcoding

    uid = g.user_id
    title = (request.form.get("title") or "").strip()
    description = request.form.get("description") or ""
    category = request.form.get("category") or "Général"
    tags = request.form.get("tags") or ""
    visibility = normalize_visibility(request.form.get("visibility"))
    video_file = request.files.get("video")
    thumb_file = request.files.get("thumbnail")
    if not title or len(title) > 255:
        return jsonify({"error": "titre invalide"}), 400
    if not video_file or not allowed_file(video_file.filename, ALLOWED_VIDEO_EXTS):
        return jsonify({"error": "vidéo invalide"}), 400

    ud = user_dir_writable(uid)
    ext = (video_file.filename or "").rsplit(".", 1)[1].lower()
    video_id_str = uuid.uuid4().hex
    video_filename = f"{video_id_str}.{ext}"
    video_path = ud / "videos" / video_filename
    video_file.save(str(video_path))
    size = video_path.stat().st_size
    mime = mimetypes.guess_type(video_filename)[0] or "video/mp4"
    meta = probe_metadata(video_path)
    duration = meta.get("duration", 0)

    thumb_name = ""
    if thumb_file and allowed_file(thumb_file.filename, ALLOWED_IMAGE_EXTS):
        timg = (thumb_file.filename or "").rsplit(".", 1)[1].lower()
        thumb_name = f"{video_id_str}.{timg}"
        thumb_path = ud / "thumbs" / thumb_name
        thumb_file.save(str(thumb_path))
        try:
            img = Image.open(thumb_path)
            img.thumbnail((1280, 720))
            img.save(thumb_path)
        except Exception:
            pass
    else:
        thumb_name = f"{video_id_str}.jpg"
        thumb_path = ud / "thumbs" / thumb_name
        ts = max(1, min(duration // 2, 10))
        if not generate_thumbnail(video_path, thumb_path, ts):
            thumb_name = ""

    is_short = (meta.get("width", 0) < meta.get("height", 0)) and 0 < duration <= 60

    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO videos (user_id, title, description, filename,
               thumbnail, duration, file_size, mime_type, category, visibility, tags,
               is_short, transcoding_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (uid, title, description, video_filename, thumb_name,
             duration, size, mime, category, visibility, tags,
             is_short, "pending"),
        )
        vid = cur.fetchone()["id"]
    try:
        transcoding.enqueue(vid, video_path, ud / "videos")
    except Exception:
        pass
    return jsonify({"id": vid, "title": title, "is_short": is_short}), 201


# ============================================================
# Live
# ============================================================
@api_bp.route("/live")
def live_list():
    with db_cursor() as cur:
        cur.execute(
            """SELECT ls.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM live_streams ls JOIN users u ON ls.user_id = u.id
               WHERE ls.status = 'live' ORDER BY ls.viewers DESC, ls.started_at DESC
               LIMIT 60"""
        )
        rows = cur.fetchall()
    return jsonify([{
        "id": r["id"], "title": r["title"], "status": r["status"],
        "viewers": r["viewers"],
        "started_at": _iso(r["started_at"]),
        "channel": {
            "id": r["user_id"], "username": r["username"],
            "display_name": r["display_name"],
            "avatar": url_for("avatar", username=r["username"]),
            "subscribers": r["subscriber_count"],
        },
    } for r in rows])


# ============================================================
# Erreurs
# ============================================================
@api_bp.app_errorhandler(404)
def _not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "introuvable"}), 404
    raise e


@api_bp.app_errorhandler(429)
def _too_many(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "trop de requêtes"}), 429
    raise e
