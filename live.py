"""Live : helpers partagés entre les routes web (app.py) et l'API v1 (api.py).

Le chat du direct fonctionne par polling court (3 s) : chaque poll renvoie les
messages publiés depuis `after` (id du dernier message vu) et sert aussi de
battement de présence pour compter les spectateurs (fenêtre glissante Redis).
"""
import cache

CHAT_MAX_LEN = 300
# Fenêtre (s) pendant laquelle un poll compte comme « spectateur présent ».
VIEWER_WINDOW = 30
# Les suppressions (modération) sont signalées aux clients sur cette plage d'ids.
DELETED_LOOKBACK = 500


def viewer_key(username):
    return f"live:viewers:{username.lower()}"


def touch_viewer(username, who):
    """Marque `who` comme spectateur du direct et renvoie le compte actuel."""
    return cache.presence_touch(viewer_key(username), who, window=VIEWER_WINDOW)


def viewer_count(username):
    return cache.presence_count(viewer_key(username), window=VIEWER_WINDOW)


def get_active_stream(cur, username):
    """Le direct en cours d'une chaîne (None si hors-ligne)."""
    cur.execute(
        """SELECT ls.id, ls.user_id, ls.title, ls.started_at
           FROM live_streams ls JOIN users u ON ls.user_id = u.id
           WHERE LOWER(u.username) = LOWER(%s) AND ls.status = 'live'
             AND u.is_banned = FALSE
           ORDER BY ls.started_at DESC LIMIT 1""",
        (username,),
    )
    return cur.fetchone()


def fetch_chat(cur, stream_id, after=0):
    """Messages publiés depuis `after` + ids supprimés depuis (modération)."""
    cur.execute(
        """SELECT m.id, m.user_id, m.body, u.username, u.display_name
           FROM live_chat_messages m JOIN users u ON m.user_id = u.id
           WHERE m.stream_id = %s AND m.id > %s AND m.is_deleted = FALSE
           ORDER BY m.id LIMIT 100""",
        (stream_id, after),
    )
    messages = [
        {"id": m["id"], "user_id": m["user_id"],
         "author": m["display_name"] or m["username"], "body": m["body"]}
        for m in cur.fetchall()
    ]
    deleted = []
    if after:
        cur.execute(
            """SELECT id FROM live_chat_messages
               WHERE stream_id = %s AND is_deleted = TRUE
                 AND id <= %s AND id > %s""",
            (stream_id, after, after - DELETED_LOOKBACK),
        )
        deleted = [r["id"] for r in cur.fetchall()]
    return messages, deleted


def post_chat(cur, stream_id, user_id, body):
    """Insère un message et le renvoie sérialisé (le corps doit être validé avant)."""
    cur.execute(
        """INSERT INTO live_chat_messages (stream_id, user_id, body)
           VALUES (%s, %s, %s) RETURNING id""",
        (stream_id, user_id, body),
    )
    mid = cur.fetchone()["id"]
    cur.execute(
        "SELECT username, display_name FROM users WHERE id = %s", (user_id,)
    )
    u = cur.fetchone()
    return {"id": mid, "user_id": user_id,
            "author": u["display_name"] or u["username"], "body": body}
