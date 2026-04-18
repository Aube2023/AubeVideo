"""AubeVideo - Plateforme de partage de vidéos de L'Aube Étoilée.

Flask sur port 5017, PostgreSQL aubevideo, auth PAM partagée.
Domaine public : video.aubeetoilee.com
"""
import os
import re
import uuid
import mimetypes
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, send_from_directory, abort, Response, stream_with_context, flash
)
from werkzeug.utils import secure_filename
from PIL import Image

from db import db_cursor, init_db, ensure_user
from auth import pam_authenticate, login_required, current_user

# ---------- Configuration ----------
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = Path(os.environ.get("AUBEVIDEO_UPLOADS", BASE_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "avi", "m4v", "ogv"}
ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_VIDEO_SIZE = 2 * 1024 * 1024 * 1024  # 2 Go
USER_QUOTA = int(os.environ.get("AUBEVIDEO_QUOTA", 10 * 1024 * 1024 * 1024))  # 10 Go

app = Flask(__name__)
app.secret_key = os.environ.get("AUBEVIDEO_SECRET", "change-me-in-prod-" + uuid.uuid4().hex)
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_SIZE


# ---------- Helpers ----------
def allowed_file(filename, exts):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def user_dir(user_id):
    d = UPLOAD_DIR / str(user_id)
    (d / "videos").mkdir(parents=True, exist_ok=True)
    (d / "thumbs").mkdir(parents=True, exist_ok=True)
    (d / "avatars").mkdir(parents=True, exist_ok=True)
    return d


def format_count(n):
    if n is None:
        return "0"
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n/1000:.1f} k".replace(".0", "")
    if n < 1_000_000_000:
        return f"{n/1_000_000:.1f} M".replace(".0", "")
    return f"{n/1_000_000_000:.1f} Md".replace(".0", "")


def time_ago(dt):
    if not dt:
        return ""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    delta = datetime.now() - dt
    s = int(delta.total_seconds())
    if s < 60:
        return "à l'instant"
    if s < 3600:
        m = s // 60
        return f"il y a {m} minute{'s' if m > 1 else ''}"
    if s < 86400:
        h = s // 3600
        return f"il y a {h} heure{'s' if h > 1 else ''}"
    if s < 2592000:
        d = s // 86400
        return f"il y a {d} jour{'s' if d > 1 else ''}"
    if s < 31536000:
        mo = s // 2592000
        return f"il y a {mo} mois"
    y = s // 31536000
    return f"il y a {y} an{'s' if y > 1 else ''}"


def format_duration(sec):
    if not sec:
        return "0:00"
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


app.jinja_env.filters["count"] = format_count
app.jinja_env.filters["timeago"] = time_ago
app.jinja_env.filters["duration"] = format_duration


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "CATEGORIES": [
            "Général", "Musique", "Gaming", "Actualités", "Sport",
            "Éducation", "Science", "Humour", "Film", "Voyage",
            "Cuisine", "Technologie", "Art", "Mode"
        ],
    }


# ---------- Auth routes ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not pam_authenticate(username, password):
            flash("Identifiants invalides.", "error")
            return render_template("login.html")
        uid = ensure_user(username, display_name=username)
        session["user_id"] = uid
        session["username"] = username
        session["display_name"] = username
        flash("Connecté.", "success")
        nxt = request.args.get("next") or url_for("home")
        return redirect(nxt)
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Déconnecté.", "success")
    return redirect(url_for("home"))


# ---------- Home / feed ----------
@app.route("/")
def home():
    category = request.args.get("c")
    with db_cursor() as cur:
        sql = """SELECT v.*, u.username, u.display_name, u.avatar_url
                 FROM videos v JOIN users u ON v.user_id = u.id
                 WHERE v.visibility = 'public'"""
        params = []
        if category and category != "Toutes":
            sql += " AND v.category = %s"
            params.append(category)
        sql += " ORDER BY v.created_at DESC LIMIT 60"
        cur.execute(sql, params)
        videos = cur.fetchall()
    return render_template("index.html", videos=videos, active_category=category or "Toutes")


@app.route("/trending")
def trending():
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public'
               ORDER BY v.views DESC, v.created_at DESC LIMIT 60"""
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos, active_category="Tendances", title="Tendances")


@app.route("/subscriptions")
@login_required
def subscriptions_feed():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v
               JOIN users u ON v.user_id = u.id
               JOIN subscriptions s ON s.channel_id = u.id
               WHERE s.subscriber_id = %s AND v.visibility = 'public'
               ORDER BY v.created_at DESC LIMIT 100""",
            (uid,),
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos, active_category="Abonnements", title="Abonnements")


@app.route("/history")
@login_required
def history():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url, h.watched_at
               FROM watch_history h
               JOIN videos v ON h.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE h.user_id = %s
               ORDER BY h.watched_at DESC LIMIT 60""",
            (uid,),
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos, active_category="Historique", title="Historique")


# ---------- Search ----------
@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    videos = []
    channels = []
    if q:
        like = f"%{q}%"
        with db_cursor() as cur:
            cur.execute(
                """SELECT v.*, u.username, u.display_name, u.avatar_url
                   FROM videos v JOIN users u ON v.user_id = u.id
                   WHERE v.visibility = 'public'
                     AND (v.title ILIKE %s OR v.description ILIKE %s
                          OR v.tags ILIKE %s OR u.username ILIKE %s
                          OR u.display_name ILIKE %s)
                   ORDER BY v.views DESC LIMIT 60""",
                (like, like, like, like, like),
            )
            videos = cur.fetchall()
            cur.execute(
                """SELECT id, username, display_name, avatar_url, subscriber_count, bio
                   FROM users
                   WHERE username ILIKE %s OR display_name ILIKE %s
                   LIMIT 20""",
                (like, like),
            )
            channels = cur.fetchall()
    return render_template("search.html", q=q, videos=videos, channels=channels)


# ---------- Upload ----------
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        uid = session["user_id"]
        title = (request.form.get("title") or "").strip()
        description = request.form.get("description") or ""
        category = request.form.get("category") or "Général"
        tags = request.form.get("tags") or ""
        visibility = request.form.get("visibility") or "public"
        video_file = request.files.get("video")
        thumb_file = request.files.get("thumbnail")

        if not title:
            flash("Le titre est obligatoire.", "error")
            return redirect(url_for("upload"))
        if not video_file or not allowed_file(video_file.filename, ALLOWED_VIDEO_EXTS):
            flash("Fichier vidéo invalide.", "error")
            return redirect(url_for("upload"))

        ud = user_dir(uid)
        ext = video_file.filename.rsplit(".", 1)[1].lower()
        video_id_str = uuid.uuid4().hex
        video_filename = f"{video_id_str}.{ext}"
        video_path = ud / "videos" / video_filename
        video_file.save(str(video_path))
        size = video_path.stat().st_size
        mime = mimetypes.guess_type(video_filename)[0] or "video/mp4"

        thumb_name = ""
        if thumb_file and allowed_file(thumb_file.filename, ALLOWED_IMAGE_EXTS):
            text = thumb_file.filename.rsplit(".", 1)[1].lower()
            thumb_name = f"{video_id_str}.{text}"
            thumb_path = ud / "thumbs" / thumb_name
            thumb_file.save(str(thumb_path))
            try:
                img = Image.open(thumb_path)
                img.thumbnail((1280, 720))
                img.save(thumb_path)
            except Exception:
                pass

        with db_cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO videos (user_id, title, description, filename,
                   thumbnail, file_size, mime_type, category, visibility, tags)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (uid, title, description, video_filename, thumb_name,
                 size, mime, category, visibility, tags),
            )
            vid = cur.fetchone()["id"]
        flash("Vidéo publiée !", "success")
        return redirect(url_for("watch", video_id=vid))

    return render_template("upload.html")


# ---------- Watch ----------
@app.route("/watch/<int:video_id>")
def watch(video_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url,
                      u.subscriber_count, u.bio
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.id = %s""",
            (video_id,),
        )
        video = cur.fetchone()
        if not video:
            abort(404)
        if video["visibility"] == "private":
            if not session.get("user_id") or session["user_id"] != video["user_id"]:
                abort(403)

        cur.execute(
            "UPDATE videos SET views = views + 1 WHERE id = %s", (video_id,)
        )
        cur.execute(
            "UPDATE users SET total_views = total_views + 1 WHERE id = %s",
            (video["user_id"],),
        )

        uid = session.get("user_id")
        if uid:
            cur.execute(
                """INSERT INTO watch_history (user_id, video_id)
                   VALUES (%s, %s)""",
                (uid, video_id),
            )

        user_reaction = None
        is_subscribed = False
        if uid:
            cur.execute(
                "SELECT reaction FROM video_reactions WHERE user_id = %s AND video_id = %s",
                (uid, video_id),
            )
            r = cur.fetchone()
            user_reaction = r["reaction"] if r else None
            cur.execute(
                "SELECT 1 FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
                (uid, video["user_id"]),
            )
            is_subscribed = cur.fetchone() is not None

        cur.execute(
            """SELECT c.*, u.username, u.display_name, u.avatar_url
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.video_id = %s AND c.parent_id IS NULL
               ORDER BY c.created_at DESC""",
            (video_id,),
        )
        comments = cur.fetchall()

        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.id <> %s
               ORDER BY v.views DESC LIMIT 20""",
            (video_id,),
        )
        suggestions = cur.fetchall()

    return render_template(
        "watch.html",
        video=video,
        comments=comments,
        suggestions=suggestions,
        user_reaction=user_reaction,
        is_subscribed=is_subscribed,
    )


# ---------- Streaming vidéo avec support Range ----------
@app.route("/stream/<int:video_id>")
def stream(video_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT user_id, filename, mime_type, visibility FROM videos WHERE id = %s",
            (video_id,),
        )
        v = cur.fetchone()
    if not v:
        abort(404)
    if v["visibility"] == "private":
        if not session.get("user_id") or session["user_id"] != v["user_id"]:
            abort(403)

    path = user_dir(v["user_id"]) / "videos" / v["filename"]
    if not path.exists():
        abort(404)

    size = path.stat().st_size
    range_header = request.headers.get("Range")
    mime = v["mime_type"] or "video/mp4"

    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
            end = min(end, size - 1)
            length = end - start + 1

            def gen():
                with open(path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(8192, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            resp = Response(stream_with_context(gen()), status=206, mimetype=mime)
            resp.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Content-Length"] = str(length)
            return resp

    return send_from_directory(path.parent, path.name, mimetype=mime, conditional=True)


# ---------- Thumbnails / avatars ----------
@app.route("/thumb/<int:video_id>")
def thumbnail(video_id):
    with db_cursor() as cur:
        cur.execute("SELECT user_id, thumbnail FROM videos WHERE id = %s", (video_id,))
        v = cur.fetchone()
    if not v or not v["thumbnail"]:
        return send_from_directory(BASE_DIR / "static" / "img", "placeholder.svg")
    path = user_dir(v["user_id"]) / "thumbs" / v["thumbnail"]
    if not path.exists():
        return send_from_directory(BASE_DIR / "static" / "img", "placeholder.svg")
    return send_from_directory(path.parent, path.name)


@app.route("/avatar/<username>")
def avatar(username):
    with db_cursor() as cur:
        cur.execute("SELECT id, avatar_url FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
    if not u or not u["avatar_url"]:
        return send_from_directory(BASE_DIR / "static" / "img", "avatar-default.svg")
    path = user_dir(u["id"]) / "avatars" / u["avatar_url"]
    if not path.exists():
        return send_from_directory(BASE_DIR / "static" / "img", "avatar-default.svg")
    return send_from_directory(path.parent, path.name)


# ---------- Profile / channel ----------
@app.route("/c/<username>")
def channel(username):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if not user:
            abort(404)
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.user_id = %s AND v.visibility = 'public'
               ORDER BY v.created_at DESC""",
            (user["id"],),
        )
        videos = cur.fetchall()

        is_subscribed = False
        me = session.get("user_id")
        if me and me != user["id"]:
            cur.execute(
                "SELECT 1 FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
                (me, user["id"]),
            )
            is_subscribed = cur.fetchone() is not None
    return render_template(
        "profile.html", user=user, videos=videos, is_subscribed=is_subscribed
    )


@app.route("/studio")
@login_required
def studio():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT * FROM videos WHERE user_id = %s ORDER BY created_at DESC""",
            (uid,),
        )
        videos = cur.fetchall()
        cur.execute(
            """SELECT COALESCE(SUM(views),0) AS total_views,
                      COUNT(*) AS total_videos,
                      COALESCE(SUM(likes_count),0) AS total_likes
               FROM videos WHERE user_id = %s""",
            (uid,),
        )
        stats = cur.fetchone()
        cur.execute(
            "SELECT subscriber_count FROM users WHERE id = %s", (uid,)
        )
        u = cur.fetchone()
        stats["subscribers"] = u["subscriber_count"]
    return render_template("studio.html", videos=videos, stats=stats)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    uid = session["user_id"]
    if request.method == "POST":
        display_name = (request.form.get("display_name") or "").strip()
        bio = request.form.get("bio") or ""
        avatar = request.files.get("avatar")
        avatar_name = None
        if avatar and allowed_file(avatar.filename, ALLOWED_IMAGE_EXTS):
            ext = avatar.filename.rsplit(".", 1)[1].lower()
            avatar_name = f"avatar.{ext}"
            path = user_dir(uid) / "avatars" / avatar_name
            avatar.save(str(path))
            try:
                img = Image.open(path)
                img.thumbnail((400, 400))
                img.save(path)
            except Exception:
                pass
        with db_cursor(commit=True) as cur:
            if avatar_name:
                cur.execute(
                    """UPDATE users SET display_name = %s, bio = %s, avatar_url = %s
                       WHERE id = %s""",
                    (display_name or session["username"], bio, avatar_name, uid),
                )
            else:
                cur.execute(
                    """UPDATE users SET display_name = %s, bio = %s WHERE id = %s""",
                    (display_name or session["username"], bio, uid),
                )
        session["display_name"] = display_name or session["username"]
        flash("Profil mis à jour.", "success")
        return redirect(url_for("settings"))

    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
        user = cur.fetchone()
    return render_template("settings.html", user=user)


# ---------- API: reactions / comments / subscribe ----------
@app.route("/api/video/<int:video_id>/react", methods=["POST"])
@login_required
def react(video_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    reaction = data.get("reaction")
    if reaction not in ("like", "dislike", None):
        return jsonify({"error": "reaction invalide"}), 400

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
            if existing["reaction"] == "like":
                cur.execute(
                    "UPDATE videos SET likes_count = GREATEST(likes_count-1,0) WHERE id = %s",
                    (video_id,),
                )
            else:
                cur.execute(
                    "UPDATE videos SET dislikes_count = GREATEST(dislikes_count-1,0) WHERE id = %s",
                    (video_id,),
                )

        if reaction and (not existing or existing["reaction"] != reaction):
            cur.execute(
                "INSERT INTO video_reactions (user_id, video_id, reaction) VALUES (%s,%s,%s)",
                (uid, video_id, reaction),
            )
            if reaction == "like":
                cur.execute(
                    "UPDATE videos SET likes_count = likes_count + 1 WHERE id = %s",
                    (video_id,),
                )
            else:
                cur.execute(
                    "UPDATE videos SET dislikes_count = dislikes_count + 1 WHERE id = %s",
                    (video_id,),
                )

        cur.execute(
            "SELECT likes_count, dislikes_count FROM videos WHERE id = %s",
            (video_id,),
        )
        counts = cur.fetchone()

    new_reaction = None
    if reaction and (not existing or existing["reaction"] != reaction):
        new_reaction = reaction

    return jsonify({
        "likes": counts["likes_count"],
        "dislikes": counts["dislikes_count"],
        "reaction": new_reaction,
    })


@app.route("/api/video/<int:video_id>/comment", methods=["POST"])
@login_required
def add_comment(video_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id")
    if not content:
        return jsonify({"error": "vide"}), 400
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
    return jsonify({
        "id": c["id"],
        "content": content,
        "username": u["username"],
        "display_name": u["display_name"],
        "avatar_url": u["avatar_url"],
        "created_at": c["created_at"].isoformat(),
        "parent_id": parent_id,
    })


@app.route("/api/video/<int:video_id>/comment/<int:comment_id>", methods=["DELETE"])
@login_required
def delete_comment(video_id, comment_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute(
            """SELECT c.user_id, v.user_id AS owner
               FROM comments c JOIN videos v ON c.video_id = v.id
               WHERE c.id = %s AND c.video_id = %s""",
            (comment_id, video_id),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "introuvable"}), 404
        if row["user_id"] != uid and row["owner"] != uid:
            return jsonify({"error": "interdit"}), 403
        cur.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
        cur.execute(
            "UPDATE videos SET comments_count = GREATEST(comments_count-1,0) WHERE id = %s",
            (video_id,),
        )
    return jsonify({"ok": True})


@app.route("/api/subscribe/<int:channel_id>", methods=["POST"])
@login_required
def subscribe(channel_id):
    uid = session["user_id"]
    if uid == channel_id:
        return jsonify({"error": "on ne peut pas s'abonner à soi-même"}), 400
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
            subscribed = True
        cur.execute(
            "SELECT subscriber_count FROM users WHERE id = %s", (channel_id,)
        )
        count = cur.fetchone()["subscriber_count"]
    return jsonify({"subscribed": subscribed, "count": count})


@app.route("/api/video/<int:video_id>", methods=["DELETE"])
@login_required
def delete_video(video_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id, filename, thumbnail FROM videos WHERE id = %s", (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify({"error": "introuvable"}), 404
        if v["user_id"] != uid:
            return jsonify({"error": "interdit"}), 403
        try:
            (user_dir(uid) / "videos" / v["filename"]).unlink(missing_ok=True)
            if v["thumbnail"]:
                (user_dir(uid) / "thumbs" / v["thumbnail"]).unlink(missing_ok=True)
        except Exception:
            pass
        cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
    return jsonify({"ok": True})


@app.route("/api/video/<int:video_id>", methods=["PATCH"])
@login_required
def update_video(video_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM videos WHERE id = %s", (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify({"error": "introuvable"}), 404
        if v["user_id"] != uid:
            return jsonify({"error": "interdit"}), 403
        fields = {}
        for k in ("title", "description", "category", "visibility", "tags"):
            if k in data:
                fields[k] = data[k]
        if not fields:
            return jsonify({"ok": True})
        sets = ", ".join(f"{k} = %s" for k in fields)
        params = list(fields.values()) + [video_id]
        cur.execute(f"UPDATE videos SET {sets}, updated_at = NOW() WHERE id = %s", params)
    return jsonify({"ok": True})


@app.errorhandler(413)
def too_large(e):
    flash("Fichier trop volumineux (max 2 Go).", "error")
    return redirect(url_for("upload"))


if __name__ == "__main__":
    try:
        init_db()
        print("[AubeVideo] Schéma initialisé.")
    except Exception as e:
        print(f"[AubeVideo] init_db skip: {e}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5017)), debug=True)
