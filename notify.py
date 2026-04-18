"""AubeVideo - création et lecture des notifications."""
from db import db_cursor


def create_notification(cur, user_id, ntype, title, body="", link=""):
    """À appeler dans un context db_cursor(commit=True)."""
    if not user_id:
        return
    cur.execute(
        """INSERT INTO notifications (user_id, type, title, body, link)
           VALUES (%s, %s, %s, %s, %s)""",
        (user_id, ntype, title, body, link),
    )


def notify_subscribers_of_new_video(cur, channel_id, channel_name, video_id, video_title):
    """Notifie tous les abonnés d'une nouvelle vidéo (qui ont notify=TRUE)."""
    cur.execute(
        """INSERT INTO notifications (user_id, type, title, body, link)
           SELECT s.subscriber_id, 'new_video', %s, %s, %s
           FROM subscriptions s
           WHERE s.channel_id = %s AND s.notify = TRUE""",
        (
            f"Nouvelle vidéo de {channel_name}",
            video_title[:250],
            f"/watch/{video_id}",
            channel_id,
        ),
    )


def notify_new_subscriber(cur, channel_id, subscriber_name, subscriber_username):
    cur.execute(
        """INSERT INTO notifications (user_id, type, title, body, link)
           VALUES (%s, 'new_sub', %s, %s, %s)""",
        (channel_id, "Nouvel abonné",
         f"{subscriber_name} s'est abonné à votre chaîne",
         f"/c/{subscriber_username}"),
    )


def notify_new_comment(cur, video_owner_id, commenter_name, video_id, video_title, content):
    if not video_owner_id:
        return
    cur.execute(
        """INSERT INTO notifications (user_id, type, title, body, link)
           VALUES (%s, 'new_comment', %s, %s, %s)""",
        (video_owner_id, f"{commenter_name} a commenté",
         f"{video_title}: {content[:100]}",
         f"/watch/{video_id}"),
    )


def unread_count(user_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = %s AND is_read = FALSE",
            (user_id,),
        )
        return cur.fetchone()["c"]


def list_recent(user_id, limit=20):
    with db_cursor() as cur:
        cur.execute(
            """SELECT * FROM notifications WHERE user_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (user_id, limit),
        )
        return cur.fetchall()


def mark_all_read(user_id):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE notifications SET is_read = TRUE WHERE user_id = %s",
            (user_id,),
        )
