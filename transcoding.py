"""Transcoding FFmpeg background — génère 360/480/720p à la demande.

Mis à jour via un worker séparé (voir `worker_transcode.py`) ou via un simple thread
pour démarrer (scalable vers Celery/rq plus tard).
"""
import os
import shutil
import subprocess
import threading
from pathlib import Path

from db import db_cursor, get_connection

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

QUALITIES = [
    ("360p", 360, 800),
    ("480p", 480, 1400),
    ("720p", 720, 2800),
]


def transcode_video(video_id: int, video_path: Path, uploads_dir: Path):
    """Génère les versions 360/480/720 à côté de la source."""
    _set_status(video_id, "processing")
    done = []
    for name, height, bitrate in QUALITIES:
        out = uploads_dir / f"{video_path.stem}_{name}.mp4"
        if out.exists():
            done.append(name)
            continue
        try:
            subprocess.run(
                [FFMPEG, "-y", "-i", str(video_path),
                 "-vf", f"scale=-2:{height}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "128k",
                 "-b:v", f"{bitrate}k",
                 "-movflags", "+faststart",
                 str(out)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=60 * 30,
            )
            if out.exists() and out.stat().st_size > 0:
                done.append(name)
        except Exception:
            continue
    _set_qualities(video_id, done)
    _set_status(video_id, "done")
    return done


def _set_status(video_id, status):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE videos SET transcoding_status = %s WHERE id = %s",
                        (status, video_id))
        conn.commit()
    finally:
        conn.close()


def _set_qualities(video_id, qualities):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE videos SET qualities = %s WHERE id = %s",
                        (",".join(qualities), video_id))
        conn.commit()
    finally:
        conn.close()


def enqueue(video_id, video_path, uploads_dir):
    """Lance le transcoding en arrière-plan (thread simple)."""
    t = threading.Thread(
        target=transcode_video,
        args=(video_id, video_path, uploads_dir),
        daemon=True,
    )
    t.start()
    return t


def transcribe_whisper(video_path: Path, out_vtt: Path, model: str = "base") -> bool:
    """Génère un .vtt via Whisper CLI (si installé).

    Nécessite: `pip install openai-whisper` + `brew install ffmpeg`
    OU conda/pip `faster-whisper`. On shell-out pour rester léger.
    """
    try:
        subprocess.run(
            ["whisper", str(video_path),
             "--model", model,
             "--output_format", "vtt",
             "--output_dir", str(out_vtt.parent)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60 * 15,
        )
        # Whisper nomme la sortie avec le stem de la vidéo
        generated = out_vtt.parent / (video_path.stem + ".vtt")
        if generated.exists() and generated != out_vtt:
            generated.rename(out_vtt)
        return out_vtt.exists()
    except Exception:
        return False
