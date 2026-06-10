"""Analytics — séries temporelles de vues par vidéo."""
from datetime import date, timedelta
from db import db_cursor


_LOG_VIEW_SQL = """INSERT INTO daily_views (video_id, date, views)
   VALUES (%s, CURRENT_DATE, 1)
   ON CONFLICT (video_id, date) DO UPDATE
   SET views = daily_views.views + 1"""


def log_view(video_id, cur=None):
    """Incrémente la vue du jour. Réutilise `cur` si fourni (évite une connexion)."""
    if cur is not None:
        cur.execute(_LOG_VIEW_SQL, (video_id,))
        return
    with db_cursor(commit=True) as c:
        c.execute(_LOG_VIEW_SQL, (video_id,))


def video_series(video_id, days=30):
    with db_cursor() as cur:
        cur.execute(
            """SELECT date, views FROM daily_views
               WHERE video_id = %s AND date >= CURRENT_DATE - INTERVAL '%s days'
               ORDER BY date""",
            (video_id, days),
        )
        rows = cur.fetchall()
    by = {r["date"]: r["views"] for r in rows}
    today = date.today()
    series = []
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        series.append({"date": d.isoformat(), "views": by.get(d, 0)})
    return series


def channel_series(user_id, days=30):
    with db_cursor() as cur:
        cur.execute(
            """SELECT dv.date, SUM(dv.views) AS views
               FROM daily_views dv
               JOIN videos v ON dv.video_id = v.id
               WHERE v.user_id = %s AND dv.date >= CURRENT_DATE - INTERVAL '%s days'
               GROUP BY dv.date ORDER BY dv.date""",
            (user_id, days),
        )
        rows = cur.fetchall()
    by = {r["date"]: int(r["views"]) for r in rows}
    today = date.today()
    series = []
    for i in range(days, -1, -1):
        d = today - timedelta(days=i)
        series.append({"date": d.isoformat(), "views": by.get(d, 0)})
    return series


def sparkline_svg(series, width=600, height=120, color="#e8b84a"):
    """Retourne un SVG inline de la courbe. Pas de lib externe."""
    if not series:
        return ""
    maxv = max((p["views"] for p in series), default=1) or 1
    n = len(series)
    pts = []
    for i, p in enumerate(series):
        x = i / max(n - 1, 1) * width
        y = height - (p["views"] / maxv * (height - 20)) - 10
        pts.append(f"{x:.1f},{y:.1f}")
    path = "M" + " L".join(pts)
    area = f"M0,{height} L{path.replace('M','L')[1:]} L{width},{height} Z"
    labels = ""
    for i, p in enumerate(series):
        if i % max(n // 6, 1) == 0:
            x = i / max(n - 1, 1) * width
            lbl = p["date"][5:]  # MM-DD
            labels += f'<text x="{x:.1f}" y="{height-2}" fill="#aaa" font-size="10" text-anchor="middle">{lbl}</text>'
    return f'''<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg" class="chart">
  <path d="{area}" fill="{color}" fill-opacity="0.12"/>
  <path d="{path}" fill="none" stroke="{color}" stroke-width="2"/>
  {labels}
</svg>'''
