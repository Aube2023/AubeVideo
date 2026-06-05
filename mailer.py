"""AubeVideo - envoi d'e-mails transactionnels via le Postfix local.

Envoie en clair sur localhost:25 (relais Postfix de l'écosystème). Silencieux
en cas d'échec (log seulement) pour ne jamais casser une requête utilisateur.
"""
import os
import smtplib
import logging
from email.message import EmailMessage
from email.utils import formataddr

log = logging.getLogger("aubevideo.mailer")

SMTP_HOST = os.environ.get("AUBEVIDEO_SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("AUBEVIDEO_SMTP_PORT", "25"))
MAIL_FROM = os.environ.get("AUBEVIDEO_MAIL_FROM", "noreply@aubeetoilee.com")
MAIL_FROM_NAME = os.environ.get("AUBEVIDEO_MAIL_FROM_NAME", "AubeVideo")


def send_email(to_addr: str, subject: str, html: str, text: str = "") -> bool:
    """Envoie un e-mail HTML (+ texte). Renvoie True si remis au MTA local."""
    if not to_addr:
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((MAIL_FROM_NAME, MAIL_FROM))
    msg["To"] = to_addr
    msg.set_content(text or _strip(html))
    msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as s:
            s.send_message(msg)
        return True
    except Exception as e:
        log.warning("Échec envoi e-mail à %s : %s", to_addr, e)
        return False


def _strip(html: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", html).strip()


def render_email(title: str, intro: str, button_label: str, button_url: str,
                 footer: str = "") -> str:
    """Gabarit HTML simple et sobre pour les e-mails AubeVideo."""
    return f"""\
<!doctype html><html><body style="margin:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;color:#111">
  <div style="max-width:520px;margin:0 auto;padding:32px 20px">
    <div style="text-align:center;margin-bottom:24px">
      <span style="font-size:22px;font-weight:700;color:#111">Aube<span style="color:#5e7da2">Video</span></span>
    </div>
    <div style="background:#fff;border-radius:12px;padding:28px;border:1px solid #e0e0e0">
      <h1 style="font-size:20px;margin:0 0 12px">{title}</h1>
      <p style="font-size:15px;line-height:1.6;color:#333;margin:0 0 22px">{intro}</p>
      <p style="text-align:center;margin:0 0 8px">
        <a href="{button_url}" style="display:inline-block;background:#5e7da2;color:#fff;
           text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:600">{button_label}</a>
      </p>
      <p style="font-size:12px;color:#888;margin:18px 0 0;word-break:break-all">
        Ou copiez ce lien : {button_url}</p>
    </div>
    <p style="font-size:12px;color:#999;text-align:center;margin-top:18px">{footer}</p>
  </div>
</body></html>"""
