"""AubeVideo - moteur de recommandations multi-signaux.

Hybride simple :
- "Pour vous" : top catégories de l'historique récent (30j) × top videos
- "À reprendre" : historique avec progress < 90% et watched récent
- "Tendances" : vues × récence (gravity 1.5, 24h)
- "Créateurs émergents" : nouvelles chaînes < 30j avec engagement élevé
- "Communauté" : abonnements + chaînes similaires
"""
from datetime import datetime
from typing import Any, Dict, List

from db import db_cursor


def _rows_to_dicts(rows: List[Any]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


def trending(limit: int = 24, hours: int = 168) -> List[Dict[str, Any]]:
    """Score = views / age_hours^1.5. Sur la dernière semaine par défaut."""
    with db_cursor() as cur:
        cur.execute(
            f"""SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count,
                       (v.views::float / GREATEST(
                           EXTRACT(EPOCH FROM (NOW() - v.created_at))/3600.0 + 2, 1)
                       ^ 1.5) AS score
                FROM videos v JOIN users u ON v.user_id = u.id
                WHERE v.visibility = 'public' AND v.is_removed = FALSE
                  AND v.is_short = FALSE
                  AND v.created_at > NOW() - INTERVAL '%s hours'
                ORDER BY score DESC NULLS LAST, v.views DESC
                LIMIT %s""",
            (hours, limit),
        )
        return _rows_to_dicts(cur.fetchall())


def for_you(user_id: int, limit: int = 24) -> List[Dict[str, Any]]:
    """Top catégories préférées × top videos non vues récemment."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.category, COUNT(*) AS c
               FROM watch_history h JOIN videos v ON h.video_id = v.id
               WHERE h.user_id = %s AND h.watched_at > NOW() - INTERVAL '30 days'
                 AND v.category IS NOT NULL
               GROUP BY v.category ORDER BY c DESC LIMIT 4""",
            (user_id,),
        )
        cats = [r["category"] for r in cur.fetchall() if r["category"]]
        if not cats:
            return trending(limit=limit)
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
                 AND v.is_short = FALSE
                 AND v.category = ANY(%s)
                 AND v.id NOT IN (
                    SELECT video_id FROM watch_history
                    WHERE user_id = %s AND watched_at > NOW() - INTERVAL '14 days'
                 )
               ORDER BY v.views DESC, v.created_at DESC
               LIMIT %s""",
            (cats, user_id, limit),
        )
        return _rows_to_dicts(cur.fetchall())


def continue_watching(user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    """Vidéos en cours (progress > 30s et < 90% de la durée)."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (v.id) v.*, u.username, u.display_name,
                       u.avatar_url, u.subscriber_count,
                       h.progress_seconds, h.watched_at
               FROM watch_history h JOIN videos v ON h.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE h.user_id = %s
                 AND h.progress_seconds > 30
                 AND v.duration > 60
                 AND h.progress_seconds < v.duration * 0.9
                 AND v.is_removed = FALSE
               ORDER BY v.id, h.watched_at DESC""",
            (user_id,),
        )
        rows = _rows_to_dicts(cur.fetchall())
        rows.sort(key=lambda r: r.get("watched_at") or datetime.min, reverse=True)
        return rows[:limit]


def emerging_creators(limit: int = 10) -> List[Dict[str, Any]]:
    """Chaînes < 60j avec ratio engagement élevé (likes+comments)/views."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT u.id, u.username, u.display_name, u.avatar_url,
                      u.subscriber_count, u.total_views, u.created_at,
                      COALESCE(SUM(v.likes_count + v.comments_count), 0) AS engagement,
                      COALESCE(SUM(v.views), 0) AS total_v
               FROM users u
               LEFT JOIN videos v ON v.user_id = u.id AND v.is_removed = FALSE
               WHERE u.created_at > NOW() - INTERVAL '60 days'
                 AND u.is_banned = FALSE
               GROUP BY u.id
               HAVING COALESCE(SUM(v.views), 0) > 50
               ORDER BY (CASE WHEN SUM(v.views) > 0
                             THEN SUM(v.likes_count + v.comments_count)::float
                                  / SUM(v.views) ELSE 0 END) DESC,
                        u.created_at DESC
               LIMIT %s""",
            (limit,),
        )
        return _rows_to_dicts(cur.fetchall())


def from_subscriptions(user_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    """Dernières vidéos des chaînes auxquelles l'utilisateur est abonné."""
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, u.subscriber_count
               FROM videos v
               JOIN users u ON v.user_id = u.id
               JOIN subscriptions s ON s.channel_id = u.id
               WHERE s.subscriber_id = %s AND v.visibility = 'public'
                     AND v.is_removed = FALSE
                     AND v.created_at > NOW() - INTERVAL '14 days'
               ORDER BY v.created_at DESC LIMIT %s""",
            (user_id, limit),
        )
        return _rows_to_dicts(cur.fetchall())


def discover_sections(user_id: int | None) -> List[Dict[str, Any]]:
    """Construit toutes les sections de découverte de la home (best-effort).

    Renvoie une liste de {key, title, videos: [...]}.
    Si user_id est None, fallback en mode anonyme.
    """
    sections: List[Dict[str, Any]] = []
    # Continue à regarder
    if user_id:
        try:
            cw = continue_watching(user_id, limit=8)
            if cw:
                sections.append({"key": "continue", "title": "Reprendre", "videos": cw})
        except Exception:
            pass
        try:
            fs = from_subscriptions(user_id, limit=8)
            if fs:
                sections.append({"key": "subscriptions", "title": "De vos abonnements", "videos": fs})
        except Exception:
            pass
    # Pour vous / tendances
    try:
        if user_id:
            fy = for_you(user_id, limit=12)
            if fy:
                sections.append({"key": "foryou", "title": "Pour vous", "videos": fy})
    except Exception:
        pass
    try:
        tr = trending(limit=12)
        if tr:
            sections.append({"key": "trending", "title": "Tendances", "videos": tr})
    except Exception:
        pass
    return sections
