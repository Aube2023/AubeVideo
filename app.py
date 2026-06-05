"""AubeVideo - Plateforme de partage de vidéos de L'Aube Étoilée.

Flask sur port 5017, PostgreSQL aubevideo, auth PAM partagée.
Domaine public : video.aubeetoilee.com
"""
import os
import re
import io
import json
import time
import uuid
import zipfile
import mimetypes
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, send_from_directory, abort, Response, stream_with_context, flash
)
from werkzeug.middleware.proxy_fix import ProxyFix
from PIL import Image

from db import (
    db_cursor, init_db, ensure_user,
    fetch_video, VISIBILITIES, normalize_visibility,
)
from auth import (
    pam_authenticate, login_required, admin_required,
    is_admin, current_user,
    register_user, authenticate_local, authenticate_aubemail, normalize_username,
    get_user_by_email, mark_email_verified, set_password,
)
import mailer
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from security import (
    csrf_protect, security_headers, configure_session,
    rate_limit, throttle_login,
)
from media import generate_thumbnail, probe_metadata, srt_to_vtt
import notify
import analytics
import cache
import totp
import push
import transcoding
import payments
import recommendations

# ---------- Configuration ----------
BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = Path(os.environ.get("AUBEVIDEO_UPLOADS", BASE_DIR / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "avi", "m4v", "ogv"}
ALLOWED_IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_VIDEO_SIZE = 2 * 1024 * 1024 * 1024  # 2 Go
USER_QUOTA = int(os.environ.get("AUBEVIDEO_QUOTA", 10 * 1024 * 1024 * 1024))  # 10 Go

def _load_secret_key():
    """Clé secrète STABLE entre redémarrages et workers gunicorn.

    Priorité à AUBEVIDEO_SECRET. Sinon, on persiste une clé aléatoire dans un
    fichier (au lieu de la régénérer à chaque process, ce qui invaliderait
    toutes les sessions et casserait le multi-worker).
    """
    env = os.environ.get("AUBEVIDEO_SECRET")
    if env:
        return env
    key_file = Path(os.environ.get("AUBEVIDEO_SECRET_FILE", BASE_DIR / ".secret_key"))
    try:
        if key_file.exists():
            data = key_file.read_text().strip()
            if data:
                return data
        secret = uuid.uuid4().hex + uuid.uuid4().hex
        key_file.write_text(secret)
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return secret
    except OSError:
        # FS en lecture seule : dernier recours, clé éphémère (warn au boot).
        return "ephemeral-" + uuid.uuid4().hex


app = Flask(__name__)
app.secret_key = _load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_SIZE
app.jinja_env.autoescape = True

# Tokens signés et expirables (reset mot de passe, vérification e-mail)
_token_serializer = URLSafeTimedSerializer(app.secret_key, salt="aubevideo-tokens")


def make_token(purpose, data):
    return _token_serializer.dumps({"p": purpose, "d": data})


def verify_token(purpose, token, max_age=3600):
    try:
        payload = _token_serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired, Exception):
        return None
    if not isinstance(payload, dict) or payload.get("p") != purpose:
        return None
    return payload.get("d")


def _send_verification_email(uid, username, email):
    """Envoie le lien de vérification d'e-mail (non bloquant)."""
    if not email:
        return
    token = make_token("verify", uid)
    url = url_for("verify_email", token=token, _external=True)
    html = mailer.render_email(
        "Confirmez votre adresse e-mail",
        f"Bonjour {username}, bienvenue sur AubeVideo ! Cliquez ci-dessous pour "
        "confirmer votre adresse e-mail.",
        "Confirmer mon e-mail", url,
        "Si vous n'êtes pas à l'origine de cette inscription, ignorez cet e-mail.")
    mailer.send_email(email, "Confirmez votre e-mail — AubeVideo", html)

# Derrière un proxy (nginx) : respecter X-Forwarded-For / X-Forwarded-Proto
if os.environ.get("AUBEVIDEO_BEHIND_PROXY", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

configure_session(app)
csrf_protect(app)
security_headers(app)

# API REST v1 (clients mobiles, intégrations)
from api import api_bp
app.register_blueprint(api_bp)

# ---------- Logging ----------
log_dir = Path(os.environ.get("AUBEVIDEO_LOG_DIR", BASE_DIR / "logs"))
log_dir.mkdir(parents=True, exist_ok=True)
handler = logging.handlers.RotatingFileHandler(
    log_dir / "aubevideo.log", maxBytes=10 * 1024 * 1024, backupCount=5
)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


# ---------- Helpers ----------
def allowed_file(filename, exts):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts


def user_dir(user_id):
    """Chemin vers le dossier user. NE crée pas les sous-dossiers (utilisé en lecture)."""
    return UPLOAD_DIR / str(user_id)


def user_dir_writable(user_id):
    """Comme user_dir mais crée les sous-dossiers — pour les routes d'upload."""
    d = UPLOAD_DIR / str(user_id)
    for sub in ("videos", "thumbs", "avatars", "banners"):
        (d / sub).mkdir(parents=True, exist_ok=True)
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


CATEGORIES = [
    "Général", "Musique", "Gaming", "Actualités", "Sport",
    "Éducation", "Science", "Humour", "Film", "Voyage",
    "Cuisine", "Technologie", "Art", "Mode",
]


def _complete_login(uid, username):
    """Met en place la session après une auth réussie (PAM ou 2FA)."""
    session.permanent = True
    session.pop("is_admin", None)
    session.pop("viewed", None)
    session["user_id"] = uid
    session["username"] = username
    session["display_name"] = username
    try:
        with db_cursor() as cur:
            cur.execute("SELECT email_verified FROM users WHERE id = %s", (uid,))
            r = cur.fetchone()
        session["email_verified"] = bool(r and r["email_verified"])
    except Exception:
        session["email_verified"] = True  # ne pas bloquer si indisponible


def _safe_next(default_endpoint="home"):
    """Renvoie request.args['next'] si chemin local, sinon URL de fallback."""
    nxt = request.args.get("next") or url_for(default_endpoint)
    return nxt if nxt.startswith("/") else url_for(default_endpoint)


@app.context_processor
def inject_globals():
    uid = session.get("user_id")
    # Ne rien faire de coûteux si pas connecté / requête statique-like
    if not uid or request.endpoint in ("stream", "thumbnail", "avatar", "banner",
                                        "static", "health"):
        return {"current_user": current_user(), "is_admin": False,
                "unread_notifs": 0, "CATEGORIES": CATEGORIES,
                "email_verified": True}
    n_unread = 0
    try:
        n_unread = notify.unread_count(uid)
    except Exception:
        pass
    return {
        "current_user": current_user(),
        "is_admin": is_admin(uid),
        "unread_notifs": n_unread,
        "CATEGORIES": CATEGORIES,
        "email_verified": session.get("email_verified", True),
    }


# ---------- Pagination helper ----------
def _pagination(page, per_page=24):
    try:
        page = max(1, int(page or 1))
    except ValueError:
        page = 1
    return page, (page - 1) * per_page, per_page


# ---------- Auth routes ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        if not throttle_login(identifier):
            flash("Trop de tentatives. Réessayez dans quelques minutes.", "error")
            return render_template("login.html")

        # 1) Compte local (email/username + mot de passe hashé).
        # 2) SSO AubeMail (identifiants de l'écosystème, vérif bcrypt).
        user = authenticate_local(identifier, password) \
            or authenticate_aubemail(identifier, password)
        if user:
            uid, username = user["id"], user["username"]
            is_banned, totp_enabled = user["is_banned"], user["totp_enabled"]
        # 3) Fallback SSO PAM (comptes système de l'écosystème).
        elif pam_authenticate(identifier, password):
            uid = ensure_user(identifier, display_name=identifier)
            with db_cursor() as cur:
                cur.execute("SELECT username, is_banned, totp_enabled FROM users WHERE id = %s", (uid,))
                row = cur.fetchone()
            username = row["username"] if row else identifier
            is_banned = bool(row and row["is_banned"])
            totp_enabled = bool(row and row["totp_enabled"])
        else:
            app.logger.warning("Login échoué pour %s (%s)", identifier, request.remote_addr)
            flash("Identifiants invalides.", "error")
            return render_template("login.html")

        if is_banned:
            flash("Ce compte a été suspendu.", "error")
            return render_template("login.html")

        # 2FA activé : on stocke l'état pendant et on redirige
        if totp_enabled:
            session["_pending_uid"] = uid
            session["_pending_username"] = username
            session["_pending_next"] = _safe_next()
            return redirect(url_for("login_2fa"))

        _complete_login(uid, username)
        app.logger.info("Connexion de %s", username)
        flash("Connecté.", "success")
        return redirect(_safe_next())
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Inscription self-service : email + mot de passe (comme YouTube)."""
    if session.get("user_id"):
        return redirect(url_for("home"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        display_name = (request.form.get("display_name") or "").strip() or username
        if not throttle_login("register:" + (request.remote_addr or "anon"), max_attempts=8):
            flash("Trop de tentatives. Réessayez dans quelques minutes.", "error")
            return render_template("register.html", form=request.form)

        uid, err = register_user(username, email, password, display_name=display_name)
        if err:
            flash(err, "error")
            return render_template("register.html", form=request.form)

        _complete_login(uid, username)
        try:
            _send_verification_email(uid, username, email)
        except Exception:
            app.logger.exception("Envoi e-mail de vérification échoué")
        app.logger.info("Inscription de %s", username)
        flash("Bienvenue sur AubeVideo ! Vérifiez votre e-mail pour confirmer votre compte.", "success")
        return redirect(_safe_next())
    return render_template("register.html", form={})


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if not throttle_login("forgot:" + (request.remote_addr or "anon"), max_attempts=6):
            flash("Trop de tentatives. Réessayez plus tard.", "error")
            return render_template("forgot_password.html")
        user = get_user_by_email(email)
        if user:
            token = make_token("reset", user["id"])
            url = url_for("reset_password", token=token, _external=True)
            html = mailer.render_email(
                "Réinitialisation de votre mot de passe",
                f"Bonjour {user['username']}, vous avez demandé à réinitialiser votre "
                "mot de passe. Ce lien est valable 1 heure.",
                "Choisir un nouveau mot de passe", url,
                "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.")
            try:
                mailer.send_email(email, "Réinitialisation du mot de passe — AubeVideo", html)
            except Exception:
                app.logger.exception("Envoi e-mail reset échoué")
        # Réponse identique que l'e-mail existe ou non (anti-énumération)
        flash("Si un compte existe avec cet e-mail, un lien de réinitialisation a été envoyé.", "success")
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    uid = verify_token("reset", token, max_age=3600)
    if not uid:
        flash("Lien invalide ou expiré. Refaites une demande.", "error")
        return redirect(url_for("forgot_password"))
    if request.method == "POST":
        pw = request.form.get("password") or ""
        pw2 = request.form.get("password2") or ""
        if pw != pw2:
            flash("Les deux mots de passe ne correspondent pas.", "error")
            return render_template("reset_password.html", token=token)
        ok, err = set_password(uid, pw)
        if not ok:
            flash(err, "error")
            return render_template("reset_password.html", token=token)
        app.logger.info("Mot de passe réinitialisé pour uid=%s", uid)
        flash("Mot de passe mis à jour. Vous pouvez vous connecter.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", token=token)


@app.route("/verify-email/<token>")
def verify_email(token):
    uid = verify_token("verify", token, max_age=60 * 60 * 24 * 7)  # 7 jours
    if not uid:
        flash("Lien de vérification invalide ou expiré.", "error")
        return redirect(url_for("home"))
    mark_email_verified(uid)
    if session.get("user_id") == uid:
        session["email_verified"] = True
    flash("Votre adresse e-mail est confirmée. Merci !", "success")
    return redirect(url_for("home"))


@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute("SELECT username, email, email_verified FROM users WHERE id = %s", (uid,))
        row = cur.fetchone()
    if row and row["email"] and not row["email_verified"]:
        try:
            _send_verification_email(uid, row["username"], row["email"])
        except Exception:
            app.logger.exception("Renvoi vérification échoué")
    flash("E-mail de vérification renvoyé.", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    uid = session.get("_pending_uid")
    if not uid:
        return redirect(url_for("login"))
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        with db_cursor() as cur:
            cur.execute("SELECT totp_secret FROM users WHERE id = %s", (uid,))
            r = cur.fetchone()
        if not r or not totp.verify(r["totp_secret"], code):
            flash("Code 2FA invalide.", "error")
            return render_template("login_2fa.html")
        nxt = session.pop("_pending_next", url_for("home"))
        uname = session.pop("_pending_username", "")
        session.pop("_pending_uid", None)
        _complete_login(uid, uname)
        flash("Connecté.", "success")
        return redirect(nxt if nxt.startswith("/") else url_for("home"))
    return render_template("login_2fa.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Déconnecté.", "success")
    return redirect(url_for("home"))


# ---------- Home / feed ----------
@app.route("/")
def home():
    category = request.args.get("c")
    page, offset, per = _pagination(request.args.get("page"), per_page=36)
    sections = []
    uid = session.get("user_id")

    # En home par défaut (sans filtre, page 1, utilisateur connecté) on affiche
    # les sections multi-rangées « Reprendre », « Pour vous », « Tendances », etc.
    show_sections = (not category or category == "Toutes") and page == 1 and uid is not None
    if show_sections:
        try:
            sections = recommendations.discover_sections(uid)
        except Exception:
            sections = []

    with db_cursor() as cur:
        sql = """SELECT v.*, u.username, u.display_name, u.avatar_url
                 FROM videos v JOIN users u ON v.user_id = u.id
                 WHERE v.visibility = 'public' AND v.is_removed = FALSE"""
        params = []
        if category and category != "Toutes":
            sql += " AND v.category = %s"
            params.append(category)
        sql += " ORDER BY v.created_at DESC LIMIT %s OFFSET %s"
        params.extend([per, offset])
        cur.execute(sql, params)
        videos = cur.fetchall()
    return render_template("index.html",
                           videos=videos,
                           sections=sections,
                           active_category=category or "Toutes",
                           page=page,
                           has_more=len(videos) == per)


@app.route("/trending")
def trending():
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
               ORDER BY v.views DESC, v.created_at DESC LIMIT 60"""
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos,
                           active_category="Tendances", title="Tendances",
                           page=1, has_more=False)


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
                     AND v.is_removed = FALSE
               ORDER BY v.created_at DESC LIMIT 100""",
            (uid,),
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos,
                           active_category="Abonnements", title="Abonnements",
                           page=1, has_more=False)


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
               WHERE h.user_id = %s AND v.is_removed = FALSE
               ORDER BY h.watched_at DESC LIMIT 60""",
            (uid,),
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos,
                           active_category="Historique", title="Historique",
                           page=1, has_more=False)


@app.route("/watch-later")
@login_required
def watch_later_page():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM watch_later w
               JOIN videos v ON w.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE w.user_id = %s AND v.is_removed = FALSE
               ORDER BY w.added_at DESC""",
            (uid,),
        )
        videos = cur.fetchall()
    return render_template("index.html", videos=videos,
                           active_category="À regarder plus tard",
                           title="À regarder plus tard",
                           page=1, has_more=False)


# ---------- Search ----------
@app.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    sort = request.args.get("sort", "relevance")
    videos = []
    channels = []
    if q:
        like = f"%{q}%"
        order = {
            "date": "v.created_at DESC",
            "views": "v.views DESC",
            "relevance": "v.views DESC",
        }.get(sort, "v.views DESC")
        with db_cursor() as cur:
            cur.execute(
                f"""SELECT v.*, u.username, u.display_name, u.avatar_url
                   FROM videos v JOIN users u ON v.user_id = u.id
                   WHERE v.visibility = 'public' AND v.is_removed = FALSE
                     AND (v.title ILIKE %s OR v.description ILIKE %s
                          OR v.tags ILIKE %s OR u.username ILIKE %s
                          OR u.display_name ILIKE %s)
                   ORDER BY {order} LIMIT 60""",
                (like, like, like, like, like),
            )
            videos = cur.fetchall()
            cur.execute(
                """SELECT id, username, display_name, avatar_url, subscriber_count, bio
                   FROM users
                   WHERE (username ILIKE %s OR display_name ILIKE %s)
                     AND is_banned = FALSE
                   LIMIT 20""",
                (like, like),
            )
            channels = cur.fetchall()
    return render_template("search.html", q=q, sort=sort,
                           videos=videos, channels=channels)


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
        visibility = normalize_visibility(request.form.get("visibility"))
        video_file = request.files.get("video")
        thumb_file = request.files.get("thumbnail")

        if not title or len(title) > 255:
            flash("Titre manquant ou trop long.", "error")
            return redirect(url_for("upload"))
        if not video_file or not allowed_file(video_file.filename, ALLOWED_VIDEO_EXTS):
            flash("Fichier vidéo invalide.", "error")
            return redirect(url_for("upload"))

        ud = user_dir_writable(uid)
        ext = video_file.filename.rsplit(".", 1)[1].lower()
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
            timg = thumb_file.filename.rsplit(".", 1)[1].lower()
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

        # Shorts = vertical et <= 60s
        is_short = (meta.get("width", 0) < meta.get("height", 0)) and duration > 0 and duration <= 60

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

            if visibility == "public":
                cur.execute(
                    "SELECT display_name FROM users WHERE id = %s", (uid,)
                )
                chan = cur.fetchone()
                notify.notify_subscribers_of_new_video(
                    cur, uid, chan["display_name"], vid, title
                )

        # Transcoding 360/480/720p en arrière-plan
        try:
            transcoding.enqueue(vid, video_path, ud / "videos")
        except Exception:
            pass

        app.logger.info("Upload: user=%s video=%s size=%s duration=%s short=%s",
                        uid, vid, size, duration, is_short)
        flash("Vidéo publiée !", "success")
        return redirect(url_for("watch", video_id=vid))

    return render_template("upload.html")


# ---------- Watch ----------
@app.route("/watch/<int:video_id>")
def watch(video_id):
    with db_cursor(commit=True) as cur:
        video = fetch_video(cur, video_id, with_user=True)
        if not video:
            abort(404)
        if video["visibility"] == "private":
            if not session.get("user_id") or session["user_id"] != video["user_id"]:
                abort(403)

        # Dédup: 1 vue / vidéo / session toutes les 6h
        viewed = session.get("viewed", {})
        now = time.time()
        last = viewed.get(str(video_id), 0)
        if now - last > 6 * 3600:
            cur.execute(
                "UPDATE videos SET views = views + 1 WHERE id = %s", (video_id,)
            )
            cur.execute(
                "UPDATE users SET total_views = total_views + 1 WHERE id = %s",
                (video["user_id"],),
            )
            viewed[str(video_id)] = now
            # Garde seulement les 200 dernières vidéos vues
            if len(viewed) > 200:
                oldest = sorted(viewed.items(), key=lambda x: x[1])[:len(viewed) - 200]
                for k, _ in oldest:
                    viewed.pop(k, None)
            session["viewed"] = viewed
            session.modified = True
            try:
                analytics.log_view(video_id)
            except Exception:
                pass

        uid = session.get("user_id")
        if uid:
            cur.execute(
                """INSERT INTO watch_history (user_id, video_id)
                   VALUES (%s, %s)""",
                (uid, video_id),
            )

        user_reaction = None
        is_subscribed = False
        in_watch_later = False
        my_playlists = []
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
                "SELECT 1 FROM watch_later WHERE user_id = %s AND video_id = %s",
                (uid, video_id),
            )
            in_watch_later = cur.fetchone() is not None
            cur.execute(
                """SELECT p.id, p.title,
                          EXISTS(SELECT 1 FROM playlist_videos pv
                                 WHERE pv.playlist_id = p.id AND pv.video_id = %s) AS has_video
                   FROM playlists p WHERE p.user_id = %s
                   ORDER BY p.created_at DESC""",
                (video_id, uid),
            )
            my_playlists = cur.fetchall()

        cur.execute(
            """SELECT c.*, u.username, u.display_name, u.avatar_url,
                      (SELECT COUNT(*) FROM comments r WHERE r.parent_id = c.id) AS reply_count
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.video_id = %s AND c.parent_id IS NULL AND c.is_removed = FALSE
               ORDER BY c.is_pinned DESC, c.likes_count DESC, c.created_at DESC""",
            (video_id,),
        )
        comments = cur.fetchall()

        cur.execute(
            "SELECT id, lang, label, is_auto FROM captions WHERE video_id = %s ORDER BY created_at",
            (video_id,),
        )
        captions = cur.fetchall()

        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_removed = FALSE
                     AND v.id <> %s
                     AND (v.category = %s OR v.user_id = %s)
               ORDER BY v.views DESC LIMIT 20""",
            (video_id, video["category"], video["user_id"]),
        )
        suggestions = cur.fetchall()
        if len(suggestions) < 10:
            cur.execute(
                """SELECT v.*, u.username, u.display_name, u.avatar_url
                   FROM videos v JOIN users u ON v.user_id = u.id
                   WHERE v.visibility = 'public' AND v.is_removed = FALSE
                         AND v.id <> %s
                   ORDER BY v.views DESC LIMIT 20""",
                (video_id,),
            )
            suggestions = cur.fetchall()

    return render_template(
        "watch.html",
        video=video,
        comments=comments,
        captions=captions,
        suggestions=suggestions,
        user_reaction=user_reaction,
        is_subscribed=is_subscribed,
        in_watch_later=in_watch_later,
        my_playlists=my_playlists,
    )


# ---------- Streaming vidéo avec support Range ----------
@app.route("/embed/<int:video_id>")
def embed(video_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.id = %s AND v.is_removed = FALSE""",
            (video_id,),
        )
        v = cur.fetchone()
    if not v or v["visibility"] == "private":
        abort(404)
    return render_template("embed.html", video=v)


@app.route("/stream/<int:video_id>")
def stream(video_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT user_id, filename, mime_type, visibility, is_removed, qualities
               FROM videos WHERE id = %s""",
            (video_id,),
        )
        v = cur.fetchone()
    if not v or v["is_removed"]:
        abort(404)
    if v["visibility"] == "private":
        if not session.get("user_id") or session["user_id"] != v["user_id"]:
            abort(403)

    # Sélection de qualité (?q=720p). En "auto"/absence de q, on préfère une
    # version transcodée MP4 (lecture navigateur garantie) plutôt que l'original
    # qui peut être un conteneur non lisible (.mov/quicktime, .mkv, .avi…).
    q = (request.args.get("q") or "").strip()
    available = [x for x in (v["qualities"] or "").split(",") if x]
    base = Path(v["filename"]).stem
    filename = v["filename"]
    if q and q in available:
        candidate = user_dir(v["user_id"]) / "videos" / f"{base}_{q}.mp4"
        if candidate.exists():
            filename = candidate.name
    elif not q:
        for cand_q in ("720p", "480p", "360p"):
            if cand_q in available:
                candidate = user_dir(v["user_id"]) / "videos" / f"{base}_{cand_q}.mp4"
                if candidate.exists():
                    filename = candidate.name
                    break

    path = user_dir(v["user_id"]) / "videos" / filename
    if not path.exists():
        abort(404)

    size = path.stat().st_size
    range_header = request.headers.get("Range")
    # Type MIME d'après l'extension RÉELLEMENT servie (un .mp4 transcodé doit être
    # renvoyé en video/mp4, pas avec le video/quicktime de l'original).
    ext = path.suffix.lower().lstrip(".")
    mime = {"mp4": "video/mp4", "m4v": "video/mp4", "webm": "video/webm",
            "ogv": "video/ogg", "mov": "video/quicktime",
            "mkv": "video/x-matroska", "avi": "video/x-msvideo"}.get(
        ext, v["mime_type"] or "video/mp4")

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


# ---------- Thumbnails / avatars / banners ----------
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


@app.route("/banner/<username>")
def banner(username):
    with db_cursor() as cur:
        cur.execute("SELECT id, banner_url FROM users WHERE username = %s", (username,))
        u = cur.fetchone()
    if not u or not u["banner_url"]:
        abort(404)
    path = user_dir(u["id"]) / "banners" / u["banner_url"]
    if not path.exists():
        abort(404)
    return send_from_directory(path.parent, path.name)


# ---------- Profile / channel ----------
@app.route("/c/<username>")
def channel(username):
    tab = request.args.get("tab", "videos")
    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if not user:
            abort(404)
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.user_id = %s AND v.visibility = 'public'
                     AND v.is_removed = FALSE
               ORDER BY v.created_at DESC""",
            (user["id"],),
        )
        videos = cur.fetchall()

        cur.execute(
            """SELECT p.*, COUNT(pv.id) AS video_count
               FROM playlists p
               LEFT JOIN playlist_videos pv ON pv.playlist_id = p.id
               WHERE p.user_id = %s AND p.visibility = 'public'
               GROUP BY p.id
               ORDER BY p.created_at DESC""",
            (user["id"],),
        )
        playlists = cur.fetchall()

        is_subscribed = False
        me = session.get("user_id")
        if me and me != user["id"]:
            cur.execute(
                "SELECT 1 FROM subscriptions WHERE subscriber_id = %s AND channel_id = %s",
                (me, user["id"]),
            )
            is_subscribed = cur.fetchone() is not None
    return render_template(
        "profile.html", user=user, videos=videos,
        playlists=playlists, tab=tab,
        is_subscribed=is_subscribed,
    )


@app.route("/studio")
@login_required
def studio():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT * FROM videos WHERE user_id = %s AND is_removed = FALSE
               ORDER BY created_at DESC""",
            (uid,),
        )
        videos = cur.fetchall()
        cur.execute(
            """SELECT COALESCE(SUM(views),0) AS total_views,
                      COUNT(*) AS total_videos,
                      COALESCE(SUM(likes_count),0) AS total_likes
               FROM videos WHERE user_id = %s AND is_removed = FALSE""",
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
        avatar_file = request.files.get("avatar")
        banner_file = request.files.get("banner")
        avatar_name = None
        banner_name = None
        if avatar_file and allowed_file(avatar_file.filename, ALLOWED_IMAGE_EXTS):
            ext = avatar_file.filename.rsplit(".", 1)[1].lower()
            avatar_name = f"avatar.{ext}"
            path = user_dir_writable(uid) / "avatars" / avatar_name
            avatar_file.save(str(path))
            try:
                img = Image.open(path)
                img.thumbnail((400, 400))
                img.save(path)
            except Exception:
                pass
        if banner_file and allowed_file(banner_file.filename, ALLOWED_IMAGE_EXTS):
            ext = banner_file.filename.rsplit(".", 1)[1].lower()
            banner_name = f"banner.{ext}"
            path = user_dir_writable(uid) / "banners" / banner_name
            banner_file.save(str(path))
            try:
                img = Image.open(path)
                img.thumbnail((2560, 720))
                img.save(path)
            except Exception:
                pass
        with db_cursor(commit=True) as cur:
            updates = ["display_name = %s", "bio = %s"]
            params = [display_name or session["username"], bio]
            if avatar_name:
                updates.append("avatar_url = %s")
                params.append(avatar_name)
            if banner_name:
                updates.append("banner_url = %s")
                params.append(banner_name)
            params.append(uid)
            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = %s", params
            )
        session["display_name"] = display_name or session["username"]
        flash("Profil mis à jour.", "success")
        return redirect(url_for("settings"))

    with db_cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (uid,))
        user = cur.fetchone()
    return render_template("settings.html", user=user)


# ---------- Notifications ----------
@app.route("/notifications")
@login_required
def notifications_page():
    uid = session["user_id"]
    items = notify.list_recent(uid, limit=100)
    notify.mark_all_read(uid)
    return render_template("notifications.html", items=items)


@app.route("/api/notifications")
@login_required
def api_notifications():
    uid = session["user_id"]
    items = notify.list_recent(uid, limit=20)
    return jsonify([{
        "id": n["id"],
        "type": n["type"],
        "title": n["title"],
        "body": n["body"],
        "link": n["link"],
        "is_read": n["is_read"],
        "created_at": n["created_at"].isoformat(),
    } for n in items])


@app.route("/api/notifications/read", methods=["POST"])
@login_required
def api_notifications_read():
    notify.mark_all_read(session["user_id"])
    return jsonify({"ok": True})


# ---------- API: reactions / comments / subscribe ----------
@app.route("/api/video/<int:video_id>/react", methods=["POST"])
@login_required
@rate_limit(limit=30, window=60)
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
@rate_limit(limit=20, window=60)
def add_comment(video_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    parent_id = data.get("parent_id")
    if not content or len(content) > 5000:
        return jsonify({"error": "contenu vide ou trop long"}), 400
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
        "username": u["username"],
        "display_name": u["display_name"],
        "avatar_url": u["avatar_url"],
        "created_at": c["created_at"].isoformat(),
        "parent_id": parent_id,
    })


@app.route("/api/comment/<int:comment_id>/replies")
def comment_replies(comment_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT c.*, u.username, u.display_name, u.avatar_url
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.parent_id = %s AND c.is_removed = FALSE
               ORDER BY c.created_at ASC""",
            (comment_id,),
        )
        rows = cur.fetchall()
    return jsonify([{
        "id": r["id"],
        "content": r["content"],
        "username": r["username"],
        "display_name": r["display_name"],
        "avatar_url": r["avatar_url"],
        "likes_count": r["likes_count"],
        "created_at": r["created_at"].isoformat(),
    } for r in rows])


@app.route("/api/comment/<int:comment_id>/like", methods=["POST"])
@login_required
def like_comment(comment_id):
    uid = session["user_id"]
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
        if row["user_id"] != uid and row["owner"] != uid and not is_admin(uid):
            return jsonify({"error": "interdit"}), 403
        # Compte les réponses imbriquées (qui cascadent aussi)
        cur.execute(
            """WITH RECURSIVE tree AS (
                 SELECT id FROM comments WHERE id = %s
                 UNION ALL
                 SELECT c.id FROM comments c JOIN tree t ON c.parent_id = t.id
               )
               SELECT COUNT(*) AS c FROM tree""",
            (comment_id,),
        )
        total = cur.fetchone()["c"]
        cur.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
        cur.execute(
            "UPDATE videos SET comments_count = GREATEST(comments_count - %s, 0) WHERE id = %s",
            (total, video_id),
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
            cur.execute(
                "SELECT display_name, username FROM users WHERE id = %s", (uid,)
            )
            me = cur.fetchone()
            notify.notify_new_subscriber(
                cur, channel_id, me["display_name"], me["username"]
            )
            subscribed = True
        cur.execute(
            "SELECT subscriber_count FROM users WHERE id = %s", (channel_id,)
        )
        count = cur.fetchone()["subscriber_count"]
    return jsonify({"subscribed": subscribed, "count": count})


# ---------- Liste de mes abonnements ----------
@app.route("/my-subscriptions")
@login_required
def my_subscriptions():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT u.id, u.username, u.display_name, u.avatar_url,
                      u.subscriber_count,
                      (SELECT MAX(created_at) FROM videos WHERE user_id = u.id) AS last_upload
               FROM subscriptions s
               JOIN users u ON s.channel_id = u.id
               WHERE s.subscriber_id = %s
               ORDER BY u.display_name""",
            (uid,),
        )
        subs = cur.fetchall()
    return render_template("my_subscriptions.html", subs=subs)


# ---------- Progress save (sync mobile/web) ----------
@app.route("/api/video/<int:video_id>/progress", methods=["POST"])
@login_required
@rate_limit(limit=120, window=60)
def save_progress_web(video_id):
    data = request.get_json(silent=True) or {}
    try:
        seconds = max(0, int(data.get("seconds") or 0))
    except (TypeError, ValueError):
        return jsonify({"error": "seconds invalide"}), 400
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute(
            """UPDATE watch_history SET progress_seconds = %s, watched_at = CURRENT_TIMESTAMP
               WHERE id = (SELECT id FROM watch_history
                           WHERE user_id = %s AND video_id = %s
                           ORDER BY watched_at DESC LIMIT 1)""",
            (seconds, uid, video_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO watch_history (user_id, video_id, progress_seconds)
                   VALUES (%s, %s, %s)""",
                (uid, video_id, seconds),
            )
    return jsonify({"ok": True})


# ---------- Watch later ----------
@app.route("/api/watch-later/<int:video_id>", methods=["POST"])
@login_required
def toggle_watch_later(video_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT 1 FROM watch_later WHERE user_id = %s AND video_id = %s",
            (uid, video_id),
        )
        exists = cur.fetchone() is not None
        if exists:
            cur.execute(
                "DELETE FROM watch_later WHERE user_id = %s AND video_id = %s",
                (uid, video_id),
            )
        else:
            cur.execute(
                "INSERT INTO watch_later (user_id, video_id) VALUES (%s, %s)",
                (uid, video_id),
            )
    return jsonify({"saved": not exists})


# ---------- Playlists ----------
@app.route("/playlists")
@login_required
def playlists_page():
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT p.*, COUNT(pv.id) AS video_count
               FROM playlists p
               LEFT JOIN playlist_videos pv ON pv.playlist_id = p.id
               WHERE p.user_id = %s
               GROUP BY p.id
               ORDER BY p.created_at DESC""",
            (uid,),
        )
        items = cur.fetchall()
    return render_template("playlists.html", playlists=items)


@app.route("/playlist/<int:playlist_id>")
def playlist_view(playlist_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT p.*, u.username, u.display_name
               FROM playlists p JOIN users u ON p.user_id = u.id
               WHERE p.id = %s""",
            (playlist_id,),
        )
        pl = cur.fetchone()
        if not pl:
            abort(404)
        if pl["visibility"] == "private":
            if not session.get("user_id") or session["user_id"] != pl["user_id"]:
                abort(403)
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM playlist_videos pv
               JOIN videos v ON pv.video_id = v.id
               JOIN users u ON v.user_id = u.id
               WHERE pv.playlist_id = %s AND v.is_removed = FALSE
               ORDER BY pv.position, pv.added_at""",
            (playlist_id,),
        )
        videos = cur.fetchall()
    return render_template("playlist.html", playlist=pl, videos=videos)


@app.route("/api/playlist", methods=["POST"])
@login_required
def create_playlist():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    visibility = data.get("visibility", "public")
    if not title or visibility not in VISIBILITIES:
        return jsonify({"error": "paramètres invalides"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO playlists (user_id, title, visibility)
               VALUES (%s, %s, %s) RETURNING id""",
            (uid, title, visibility),
        )
        pid = cur.fetchone()["id"]
    return jsonify({"id": pid, "title": title})


@app.route("/api/playlist/<int:playlist_id>/video/<int:video_id>", methods=["POST"])
@login_required
def toggle_playlist_video(playlist_id, video_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM playlists WHERE id = %s", (playlist_id,))
        p = cur.fetchone()
        if not p or p["user_id"] != uid:
            return jsonify({"error": "interdit"}), 403
        cur.execute(
            "SELECT 1 FROM playlist_videos WHERE playlist_id = %s AND video_id = %s",
            (playlist_id, video_id),
        )
        exists = cur.fetchone() is not None
        if exists:
            cur.execute(
                "DELETE FROM playlist_videos WHERE playlist_id = %s AND video_id = %s",
                (playlist_id, video_id),
            )
        else:
            cur.execute(
                "INSERT INTO playlist_videos (playlist_id, video_id) VALUES (%s, %s)",
                (playlist_id, video_id),
            )
    return jsonify({"in_playlist": not exists})


@app.route("/api/playlist/<int:playlist_id>", methods=["DELETE"])
@login_required
def delete_playlist(playlist_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM playlists WHERE id = %s", (playlist_id,))
        p = cur.fetchone()
        if not p or p["user_id"] != uid:
            return jsonify({"error": "interdit"}), 403
        cur.execute("DELETE FROM playlists WHERE id = %s", (playlist_id,))
    return jsonify({"ok": True})


# ---------- Video CRUD ----------
@app.route("/api/video/<int:video_id>", methods=["DELETE"])
@login_required
def delete_video(video_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id, filename, thumbnail FROM videos WHERE id = %s",
                    (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify({"error": "introuvable"}), 404
        if v["user_id"] != uid and not is_admin(uid):
            return jsonify({"error": "interdit"}), 403
        try:
            ud = user_dir(v["user_id"])
            source = ud / "videos" / v["filename"]
            source.unlink(missing_ok=True)
            # Nettoie les versions transcodées _360p/_480p/_720p
            stem = Path(v["filename"]).stem
            for quality_file in (ud / "videos").glob(f"{stem}_*p.mp4"):
                quality_file.unlink(missing_ok=True)
            if v["thumbnail"]:
                (ud / "thumbs" / v["thumbnail"]).unlink(missing_ok=True)
            # Captions associés
            cur.execute(
                "SELECT filename FROM captions WHERE video_id = %s", (video_id,)
            )
            for cap in cur.fetchall():
                (ud / "captions" / cap["filename"]).unlink(missing_ok=True)
        except Exception:
            pass
        cur.execute("DELETE FROM videos WHERE id = %s", (video_id,))
    return jsonify({"ok": True})


VIDEO_PATCH_FIELDS = ("title", "description", "category", "visibility", "tags")


@app.route("/api/video/<int:video_id>", methods=["PATCH"])
@login_required
def update_video(video_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    fields = {k: data[k] for k in VIDEO_PATCH_FIELDS if k in data}
    if "visibility" in fields and fields["visibility"] not in VISIBILITIES:
        return jsonify({"error": "visibilité invalide"}), 400
    if not fields:
        return jsonify({"ok": True})
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id FROM videos WHERE id = %s", (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify({"error": "introuvable"}), 404
        if v["user_id"] != uid:
            return jsonify({"error": "interdit"}), 403
        sets = ", ".join(f"{k} = %s" for k in fields)
        params = list(fields.values()) + [video_id]
        cur.execute(f"UPDATE videos SET {sets}, updated_at = NOW() WHERE id = %s", params)
    return jsonify({"ok": True})


# ---------- Signalement / modération ----------
REPORT_REASONS = [
    "Contenu inapproprié", "Discours haineux", "Violence",
    "Spam / arnaque", "Fausses informations", "Harcèlement",
    "Atteinte aux droits d'auteur", "Autre",
]


@app.route("/api/report", methods=["POST"])
@login_required
@rate_limit(limit=5, window=300)
def create_report():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    reason = data.get("reason")
    details = (data.get("details") or "")[:2000]
    if target_type not in ("video", "comment", "user"):
        return jsonify({"error": "type invalide"}), 400
    if reason not in REPORT_REASONS:
        return jsonify({"error": "motif invalide"}), 400
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        return jsonify({"error": "id invalide"}), 400
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO reports (reporter_id, target_type, target_id, reason, details)
               VALUES (%s, %s, %s, %s, %s)""",
            (uid, target_type, target_id, reason, details),
        )
    app.logger.info("Signalement %s#%s par user %s", target_type, target_id, uid)
    return jsonify({"ok": True})


# ---------- Admin panel ----------
@app.route("/admin")
@admin_required
def admin_home():
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS c FROM users")
        users_count = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM videos WHERE is_removed = FALSE")
        videos_count = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM reports WHERE status = 'pending'")
        pending_reports = cur.fetchone()["c"]
        cur.execute(
            """SELECT r.*, u.username AS reporter
               FROM reports r JOIN users u ON r.reporter_id = u.id
               WHERE r.status = 'pending'
               ORDER BY r.created_at DESC LIMIT 50"""
        )
        reports = cur.fetchall()
    return render_template("admin.html",
                           users_count=users_count,
                           videos_count=videos_count,
                           pending_reports=pending_reports,
                           reports=reports)


@app.route("/api/admin/report/<int:report_id>", methods=["POST"])
@admin_required
def handle_report(report_id):
    data = request.get_json(silent=True) or {}
    action = data.get("action") or request.form.get("action")
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT * FROM reports WHERE id = %s", (report_id,))
        r = cur.fetchone()
        if not r:
            return jsonify({"error": "introuvable"}), 404
        if action == "dismiss":
            cur.execute(
                "UPDATE reports SET status='dismissed', reviewed_by=%s, reviewed_at=NOW() WHERE id=%s",
                (uid, report_id),
            )
        elif action == "remove":
            if r["target_type"] == "video":
                cur.execute("UPDATE videos SET is_removed = TRUE WHERE id = %s",
                            (r["target_id"],))
            elif r["target_type"] == "comment":
                cur.execute("UPDATE comments SET is_removed = TRUE WHERE id = %s",
                            (r["target_id"],))
            elif r["target_type"] == "user":
                cur.execute("UPDATE users SET is_banned = TRUE WHERE id = %s",
                            (r["target_id"],))
            cur.execute(
                "UPDATE reports SET status='actioned', reviewed_by=%s, reviewed_at=NOW() WHERE id=%s",
                (uid, report_id),
            )
        else:
            return jsonify({"error": "action invalide"}), 400
    return jsonify({"ok": True})


# ---------- Shorts ----------
@app.route("/shorts")
def shorts():
    with db_cursor() as cur:
        cur.execute(
            """SELECT v.*, u.username, u.display_name, u.avatar_url
               FROM videos v JOIN users u ON v.user_id = u.id
               WHERE v.visibility = 'public' AND v.is_short = TRUE
                     AND v.is_removed = FALSE
               ORDER BY v.created_at DESC LIMIT 30"""
        )
        videos = cur.fetchall()
    return render_template("shorts.html", videos=videos)


# ---------- Analytics (studio) ----------
@app.route("/studio/analytics")
@login_required
def studio_analytics():
    uid = session["user_id"]
    days = int(request.args.get("days", 30))
    days = max(7, min(days, 365))
    series = analytics.channel_series(uid, days=days)
    svg = analytics.sparkline_svg(series, width=800, height=180)
    total = sum(p["views"] for p in series)
    with db_cursor() as cur:
        cur.execute(
            """SELECT id, title, views, likes_count, comments_count
               FROM videos WHERE user_id = %s AND is_removed = FALSE
               ORDER BY views DESC LIMIT 10""",
            (uid,),
        )
        top = cur.fetchall()
    return render_template("analytics.html",
                           series=series, svg=svg, total=total,
                           days=days, top=top)


@app.route("/api/video/<int:video_id>/series")
@login_required
def video_series_api(video_id):
    uid = session["user_id"]
    with db_cursor() as cur:
        cur.execute("SELECT user_id FROM videos WHERE id = %s", (video_id,))
        v = cur.fetchone()
        if not v:
            return jsonify({"error": "introuvable"}), 404
        if v["user_id"] != uid and not is_admin(uid):
            return jsonify({"error": "interdit"}), 403
    days = int(request.args.get("days", 30))
    days = max(7, min(days, 365))
    return jsonify(analytics.video_series(video_id, days=days))


# ---------- Search autocomplete ----------
@app.route("/api/suggest")
def suggest():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"{q}%"
    wlike = f"%{q}%"
    key = f"suggest:{q.lower()}"
    hit = cache.get(key)
    if hit is not None:
        return jsonify(hit)
    with db_cursor() as cur:
        cur.execute(
            """(SELECT title AS text, 'video' AS kind, id::text AS id, ''::text AS username
                FROM videos
                WHERE visibility = 'public' AND is_removed = FALSE AND title ILIKE %s
                ORDER BY views DESC LIMIT 6)
               UNION ALL
               (SELECT display_name AS text, 'channel' AS kind, id::text AS id, username
                FROM users
                WHERE (display_name ILIKE %s OR username ILIKE %s) AND is_banned = FALSE
                LIMIT 4)""",
            (like, wlike, wlike),
        )
        rows = cur.fetchall()
    out = [{"text": r["text"], "kind": r["kind"], "id": r["id"],
            "username": r["username"]} for r in rows]
    cache.set(key, out, ttl=60)
    return jsonify(out)


# ---------- Pinned comments + creator heart ----------
@app.route("/api/comment/<int:comment_id>/pin", methods=["POST"])
@login_required
def pin_comment(comment_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute(
            """SELECT c.video_id, v.user_id AS owner
               FROM comments c JOIN videos v ON c.video_id = v.id
               WHERE c.id = %s""",
            (comment_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "introuvable"}), 404
        if row["owner"] != uid:
            return jsonify({"error": "seul le créateur peut épingler"}), 403
        # Désépingle les anciens du même vidéo
        cur.execute(
            "UPDATE comments SET is_pinned = FALSE WHERE video_id = %s AND is_pinned = TRUE",
            (row["video_id"],),
        )
        cur.execute(
            "UPDATE comments SET is_pinned = TRUE WHERE id = %s", (comment_id,)
        )
        cur.execute(
            "UPDATE videos SET pinned_comment_id = %s WHERE id = %s",
            (comment_id, row["video_id"]),
        )
    return jsonify({"ok": True})


@app.route("/api/comment/<int:comment_id>/heart", methods=["POST"])
@login_required
def heart_comment(comment_id):
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute(
            """SELECT v.user_id AS owner, c.hearted
               FROM comments c JOIN videos v ON c.video_id = v.id
               WHERE c.id = %s""",
            (comment_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "introuvable"}), 404
        if row["owner"] != uid:
            return jsonify({"error": "seul le créateur"}), 403
        new_val = not row["hearted"]
        cur.execute("UPDATE comments SET hearted = %s WHERE id = %s",
                    (new_val, comment_id))
    return jsonify({"hearted": new_val})


# ---------- Captions (.vtt) ----------
@app.route("/api/video/<int:video_id>/captions", methods=["GET", "POST"])
def captions_api(video_id):
    if request.method == "GET":
        with db_cursor() as cur:
            cur.execute(
                """SELECT id, lang, label, is_auto FROM captions WHERE video_id = %s
                   ORDER BY created_at DESC""",
                (video_id,),
            )
            rows = cur.fetchall()
        return jsonify([dict(r) for r in rows])

    if not session.get("user_id"):
        return jsonify({"error": "auth"}), 401
    with db_cursor() as cur:
        v = fetch_video(cur, video_id)
    if not v:
        return jsonify({"error": "introuvable"}), 404
    if v["user_id"] != session["user_id"]:
        return jsonify({"error": "interdit"}), 403

    file = request.files.get("file")
    lang = request.form.get("lang", "fr")[:10]
    label = request.form.get("label", "Français")[:64]
    if not file or not file.filename.endswith((".vtt", ".srt")):
        return jsonify({"error": "fichier .vtt ou .srt requis"}), 400
    ud = user_dir(v["user_id"])
    (ud / "captions").mkdir(parents=True, exist_ok=True)
    fname = f"{video_id}_{lang}_{uuid.uuid4().hex[:8]}.vtt"
    path = ud / "captions" / fname
    content = file.read().decode("utf-8", errors="ignore")
    if file.filename.endswith(".srt"):
        content = srt_to_vtt(content)
    path.write_text(content, encoding="utf-8")
    with db_cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO captions (video_id, lang, label, filename)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (video_id, lang, label, fname),
        )
        cap_id = cur.fetchone()["id"]
    return jsonify({"id": cap_id, "lang": lang, "label": label})


@app.route("/caption/<int:caption_id>")
def caption_file(caption_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT c.filename, v.user_id
               FROM captions c JOIN videos v ON c.video_id = v.id
               WHERE c.id = %s""",
            (caption_id,),
        )
        c = cur.fetchone()
    if not c:
        abort(404)
    path = user_dir(c["user_id"]) / "captions" / c["filename"]
    if not path.exists():
        abort(404)
    return send_from_directory(path.parent, path.name, mimetype="text/vtt")


# ---------- 2FA TOTP ----------
@app.route("/settings/2fa", methods=["GET", "POST"])
@login_required
def twofa_setup():
    uid = session["user_id"]
    if request.method == "POST":
        action = request.form.get("action")
        with db_cursor(commit=True) as cur:
            if action == "enable":
                secret = session.get("_pending_totp")
                code = request.form.get("code", "").strip()
                if not secret or not totp.verify(secret, code):
                    flash("Code invalide.", "error")
                    return redirect(url_for("twofa_setup"))
                cur.execute(
                    "UPDATE users SET totp_secret = %s, totp_enabled = TRUE WHERE id = %s",
                    (secret, uid),
                )
                session.pop("_pending_totp", None)
                flash("2FA activé.", "success")
            elif action == "disable":
                cur.execute(
                    "UPDATE users SET totp_secret = NULL, totp_enabled = FALSE WHERE id = %s",
                    (uid,),
                )
                flash("2FA désactivé.", "success")
        return redirect(url_for("twofa_setup"))

    with db_cursor() as cur:
        cur.execute("SELECT totp_enabled, username FROM users WHERE id = %s", (uid,))
        u = cur.fetchone()
    secret = None
    uri = None
    if not u["totp_enabled"]:
        secret = session.get("_pending_totp")
        if not secret:
            secret = totp.generate_secret()
            session["_pending_totp"] = secret
        uri = totp.provisioning_uri(secret, u["username"])
    return render_template("twofa.html", enabled=u["totp_enabled"],
                           secret=secret, uri=uri)


# ---------- Web push ----------
@app.route("/api/push/key")
def push_key():
    return jsonify({"key": push.public_key_b64()})


@app.route("/api/push/subscribe", methods=["POST"])
@login_required
def push_subscribe():
    sub = request.get_json(silent=True) or {}
    push.save_subscription(session["user_id"], sub)
    return jsonify({"ok": True})


@app.route("/api/push/unsubscribe", methods=["POST"])
@login_required
def push_unsubscribe():
    data = request.get_json(silent=True) or {}
    push.remove_subscription(session["user_id"], data.get("endpoint", ""))
    return jsonify({"ok": True})


# ---------- Tip jar (Stripe) ----------
@app.route("/tip/<username>", methods=["GET", "POST"])
def tip_page(username):
    with db_cursor() as cur:
        cur.execute("SELECT id, display_name, username FROM users WHERE username = %s",
                    (username,))
        u = cur.fetchone()
    if not u:
        abort(404)
    if request.method == "POST":
        try:
            amount_cents = int(request.form.get("amount", "0")) * 100
        except ValueError:
            amount_cents = 0
        message = (request.form.get("message") or "")[:500]
        if amount_cents < 100:
            flash("Montant minimum 1 €.", "error")
            return redirect(url_for("tip_page", username=username))
        # Garde-fou : Stripe refuse au-delà mais on coupe avant pour un message clair
        if amount_cents > 1_000_000:
            flash("Montant maximum 10 000 €.", "error")
            return redirect(url_for("tip_page", username=username))
        url = payments.create_checkout(
            session.get("user_id"), u["id"], u["display_name"],
            amount_cents, message,
        )
        if not url:
            flash("Les paiements ne sont pas configurés.", "error")
            return redirect(url_for("tip_page", username=username))
        return redirect(url)
    return render_template("tip.html", creator=u)


@app.route("/tip/success")
def tip_success():
    flash("Merci pour votre don !", "success")
    return redirect(url_for("home"))


@app.route("/tip/cancel")
def tip_cancel():
    flash("Don annulé.", "error")
    return redirect(url_for("home"))


@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    sig = request.headers.get("Stripe-Signature", "")
    if payments.handle_webhook(request.get_data(), sig):
        return "", 200
    return "", 400


# ---------- Live streaming (skeleton) ----------
@app.route("/studio/live")
@login_required
def live_dashboard():
    uid = session["user_id"]
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT stream_key FROM users WHERE id = %s", (uid,))
        u = cur.fetchone()
        if not u["stream_key"]:
            key = uuid.uuid4().hex
            cur.execute("UPDATE users SET stream_key = %s WHERE id = %s", (key, uid))
            u = {"stream_key": key}
    rtmp_base = os.environ.get("AUBEVIDEO_RTMP_URL", "rtmp://video.aubeetoilee.com/live")
    return render_template("live.html",
                           stream_key=u["stream_key"],
                           rtmp_base=rtmp_base)


@app.route("/api/live/callback", methods=["POST"])
def live_callback():
    """Endpoint appelé par nginx-rtmp on_publish / on_publish_done."""
    key = request.form.get("name", "")
    action = request.form.get("call", "")  # publish / publish_done
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM users WHERE stream_key = %s", (key,))
        u = cur.fetchone()
        if not u:
            return "", 403
        if action == "publish":
            cur.execute(
                """INSERT INTO live_streams (user_id, title, status, started_at)
                   VALUES (%s, %s, 'live', NOW())""",
                (u["id"], "Direct AubeVideo"),
            )
        else:
            cur.execute(
                """UPDATE live_streams SET status = 'ended', ended_at = NOW()
                   WHERE user_id = %s AND status = 'live'""",
                (u["id"],),
            )
    return "", 200


# ---------- GDPR export ----------
GDPR_EXPORT_QUERIES = (
    ("user.json",          "SELECT * FROM users WHERE id = %s"),
    ("videos.json",        "SELECT * FROM videos WHERE user_id = %s"),
    ("comments.json",      "SELECT * FROM comments WHERE user_id = %s"),
    ("subscriptions.json", "SELECT * FROM subscriptions WHERE subscriber_id = %s"),
    ("history.json",       "SELECT * FROM watch_history WHERE user_id = %s"),
)


@app.route("/settings/export")
@login_required
def gdpr_export():
    uid = session["user_id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, db_cursor() as cur:
        for fname, sql in GDPR_EXPORT_QUERIES:
            cur.execute(sql, (uid,))
            rows = cur.fetchall()
            payload = dict(rows[0]) if (fname == "user.json" and rows) else [dict(r) for r in rows]
            z.writestr(fname, json.dumps(payload, default=str, ensure_ascii=False, indent=2))
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename=aubevideo-export-{uid}.zip"},
    )


# ---------- SEO: sitemap + robots + manifest ----------
@app.route("/robots.txt")
def robots():
    public = os.environ.get("AUBEVIDEO_PUBLIC_URL", "http://localhost:5017")
    return Response(
        f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nSitemap: {public}/sitemap.xml\n",
        mimetype="text/plain",
    )


@app.route("/sitemap.xml")
def sitemap():
    public = os.environ.get("AUBEVIDEO_PUBLIC_URL", "http://localhost:5017")
    urls = [f"{public}/", f"{public}/trending", f"{public}/shorts"]
    with db_cursor() as cur:
        cur.execute(
            """SELECT id, created_at FROM videos
               WHERE visibility = 'public' AND is_removed = FALSE
               ORDER BY created_at DESC LIMIT 5000"""
        )
        vids = cur.fetchall()
        cur.execute(
            "SELECT username FROM users WHERE is_banned = FALSE LIMIT 5000"
        )
        users = cur.fetchall()
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml.append(f"<url><loc>{u}</loc></url>")
    for v in vids:
        xml.append(
            f"<url><loc>{public}/watch/{v['id']}</loc>"
            f"<lastmod>{v['created_at'].date().isoformat()}</lastmod></url>"
        )
    for u in users:
        xml.append(f"<url><loc>{public}/c/{u['username']}</loc></url>")
    xml.append("</urlset>")
    return Response("\n".join(xml), mimetype="application/xml")


@app.route("/manifest.webmanifest")
def manifest():
    return jsonify({
        "name": "AubeVideo",
        "short_name": "AubeVideo",
        "description": "Plateforme vidéo de L'Aube Étoilée",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f0f0f",
        "theme_color": "#e8b84a",
        "lang": "fr",
        "icons": [
            {"src": "/static/img/logo.svg", "sizes": "any",
             "type": "image/svg+xml", "purpose": "any maskable"},
        ],
    })


@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(BASE_DIR / "static", "service-worker.js",
                                mimetype="application/javascript")


# ---------- Health / monitoring ----------
@app.route("/health")
def health():
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return jsonify({"status": "ok", "db": "ok", "time": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"status": "degraded", "db": str(e)}), 503


@app.errorhandler(413)
def too_large(e):
    flash("Fichier trop volumineux (max 2 Go).", "error")
    return redirect(url_for("upload"))


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           message="Accès refusé."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="Page introuvable."), 404


if __name__ == "__main__":
    try:
        init_db()
        print("[AubeVideo] Schéma initialisé.")
    except Exception as e:
        print(f"[AubeVideo] init_db skip: {e}")
    app.run(host="0.0.0.0",
            port=int(os.environ.get("PORT", 5017)),
            debug=os.environ.get("FLASK_DEBUG", "1") == "1")
