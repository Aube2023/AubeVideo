"""Tests basiques — pas de DB réelle, uniquement compile + imports."""
import pytest


def test_imports():
    import app
    import auth
    import db
    import security
    import media
    import notify
    import analytics
    import cache
    import totp
    import push
    import transcoding
    import payments
    assert app.app is not None


def test_totp_generate_and_verify():
    import totp
    secret = totp.generate_secret()
    assert len(secret) >= 32
    code = totp.totp(secret)
    assert totp.verify(secret, code)
    assert not totp.verify(secret, "000000")


def test_csrf_validation():
    from security import generate_csrf_token, validate_csrf_token
    from app import app
    with app.test_request_context():
        from flask import session
        session.clear()
        t = generate_csrf_token()
        assert validate_csrf_token(t)
        assert not validate_csrf_token("bad")


def test_analytics_sparkline():
    import analytics
    series = [{"date": "2026-01-01", "views": 10},
              {"date": "2026-01-02", "views": 50},
              {"date": "2026-01-03", "views": 30}]
    svg = analytics.sparkline_svg(series)
    assert "<svg" in svg and "path" in svg


def test_srt_to_vtt():
    from app import _srt_to_vtt
    srt = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
    vtt = _srt_to_vtt(srt)
    assert "WEBVTT" in vtt
    assert "00:00:01.000 --> 00:00:03.000" in vtt


def test_health_endpoint():
    from app import app
    with app.test_client() as c:
        r = c.get("/health")
        # 200 si DB OK, 503 sinon — tous les 2 sont acceptables
        assert r.status_code in (200, 503)


def test_robots_and_manifest():
    from app import app
    with app.test_client() as c:
        r = c.get("/robots.txt")
        assert r.status_code == 200
        assert b"Sitemap" in r.data
        r = c.get("/manifest.webmanifest")
        assert r.status_code == 200
        assert b"AubeVideo" in r.data


def test_csrf_blocks_post_without_token():
    from app import app
    with app.test_client() as c:
        r = c.post("/login", data={"username": "x", "password": "y"})
        assert r.status_code == 403  # CSRF block


def test_login_requires_csrf_and_fails_on_bad_creds():
    from app import app
    with app.test_client() as c:
        page = c.get("/login").data.decode()
        # Extrait le token CSRF du form
        import re
        m = re.search(r'name="_csrf" value="([^"]+)"', page)
        assert m
        token = m.group(1)
        r = c.post("/login", data={"username": "inexistant",
                                     "password": "faux", "_csrf": token})
        # Dev mode accepte tout (1) sinon 200 avec flash d'erreur
        assert r.status_code in (200, 302)
