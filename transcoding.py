"""Transcoding FFmpeg — versions MP4 360/480/720/1080 + (optionnel) HLS.

Exécuté par un worker RQ (file Redis, supervisé par systemd) si disponible,
sinon par un simple thread daemon en repli (dev local).
"""
import os
import shutil
import subprocess
import threading
from pathlib import Path

from db import get_connection
from media import probe_metadata

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# (nom, hauteur, bitrate vidéo kbps, bande passante HLS approx)
QUALITIES = [
    ("360p", 360, 800, 900_000),
    ("480p", 480, 1400, 1_600_000),
    ("720p", 720, 2800, 3_200_000),
    ("1080p", 1080, 5000, 5_800_000),
]

# ---------- File RQ (Redis) avec repli thread ----------
try:
    from redis import Redis as _Redis
    from rq import Queue as _Queue, Retry as _Retry
    _RURL = os.environ.get("REDIS_URL", "").strip()
    if _RURL:
        _conn = _Redis.from_url(_RURL)
        _conn.ping()
        _queue = _Queue("aubevideo", connection=_conn, default_timeout=3600)
    else:
        _queue = None
except Exception:
    _queue = None
    _Retry = None


def _update_video(video_id: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    params = list(fields.values()) + [video_id]
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE videos SET {sets} WHERE id = %s", params)
        conn.commit()
    finally:
        conn.close()


def transcode_video(video_id, video_path, uploads_dir):
    """Génère les versions MP4 (sans upscaler la source). Marque le statut.

    Accepte des chemins str (sérialisation RQ) ou Path.
    """
    video_path = Path(video_path)
    uploads_dir = Path(uploads_dir)
    _update_video(video_id, transcoding_status="processing")
    done = []
    attempted = 0
    try:
        meta = probe_metadata(video_path)
        src_h = meta.get("height", 0) or 100000
        for name, height, bitrate, _bw in QUALITIES:
            if height > src_h * 1.1:      # ne jamais upscaler
                continue
            out = uploads_dir / f"{video_path.stem}_{name}.mp4"
            if out.exists() and out.stat().st_size > 0:
                done.append(name)
                continue
            attempted += 1
            try:
                subprocess.run(
                    [FFMPEG, "-nostdin", "-y", "-i", str(video_path),
                     "-vf", f"scale=-2:{height}",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                     "-c:a", "aac", "-b:a", "128k",
                     "-b:v", f"{bitrate}k",
                     "-movflags", "+faststart",
                     str(out)],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=60 * 60,
                )
                if out.exists() and out.stat().st_size > 0:
                    done.append(name)
            except Exception:
                continue
        status = "error" if (attempted and not done) else "done"
        _update_video(video_id, qualities=",".join(done), transcoding_status=status)
    except Exception:
        _update_video(video_id, qualities=",".join(done), transcoding_status="error")
    # Génère le HLS adaptatif à partir des MP4 produits (best-effort).
    try:
        build_hls(video_id, video_path, uploads_dir, done)
    except Exception:
        pass
    return done


def build_hls(video_id, video_path, uploads_dir, qualities):
    """Construit un HLS VOD multi-qualité (master.m3u8 + variantes) par simple
    segmentation des MP4 déjà transcodés (-c copy, rapide). Best-effort."""
    video_path = Path(video_path)
    uploads_dir = Path(uploads_dir)
    if not qualities:
        return
    hls_dir = uploads_dir / "hls" / video_path.stem
    hls_dir.mkdir(parents=True, exist_ok=True)
    by_name = {q[0]: q for q in QUALITIES}
    master_lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    built = 0
    for name in qualities:
        if name not in by_name:
            continue
        _, height, _br, bw = by_name[name]
        mp4 = uploads_dir / f"{video_path.stem}_{name}.mp4"
        if not (mp4.exists() and mp4.stat().st_size > 0):
            continue
        variant = hls_dir / name
        variant.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [FFMPEG, "-nostdin", "-y", "-i", str(mp4),
                 "-c", "copy", "-f", "hls",
                 "-hls_time", "6", "-hls_playlist_type", "vod",
                 "-hls_segment_filename", str(variant / "seg_%03d.ts"),
                 str(variant / "index.m3u8")],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=60 * 20,
            )
        except Exception:
            continue
        if (variant / "index.m3u8").exists():
            width = int(height * 16 / 9)
            master_lines.append(
                f"#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={width}x{height}")
            master_lines.append(f"{name}/index.m3u8")
            built += 1
    if built:
        (hls_dir / "master.m3u8").write_text("\n".join(master_lines) + "\n")
        _update_video(video_id, hls_ready=True)


def enqueue(video_id, video_path, uploads_dir):
    """Met le transcodage en file RQ (worker supervisé) ou en thread (repli)."""
    if _queue is not None:
        try:
            kwargs = {"job_timeout": 3600}
            if _Retry is not None:
                kwargs["retry"] = _Retry(max=2)
            _queue.enqueue(transcode_video, video_id, str(video_path),
                           str(uploads_dir), **kwargs)
            return
        except Exception:
            pass
    t = threading.Thread(
        target=transcode_video,
        args=(video_id, video_path, uploads_dir),
        daemon=True,
    )
    t.start()
    return t


def transcribe_whisper(video_path: Path, out_vtt: Path, model: str = "base") -> bool:
    """Génère un .vtt via Whisper CLI (si installé)."""
    try:
        subprocess.run(
            ["whisper", str(video_path),
             "--model", model,
             "--output_format", "vtt",
             "--output_dir", str(out_vtt.parent)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60 * 15,
        )
        generated = out_vtt.parent / (video_path.stem + ".vtt")
        if generated.exists() and generated != out_vtt:
            generated.rename(out_vtt)
        return out_vtt.exists()
    except Exception:
        return False
