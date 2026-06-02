"""Transcoding FFmpeg background — génère 360/480/720p à la demande.

Mis à jour via un worker séparé (voir `worker_transcode.py`) ou via un simple thread
pour démarrer (scalable vers Celery/rq plus tard).
"""
import shutil
import subprocess
import threading
from pathlib import Path

from db import get_connection

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

QUALITIES = [
    ("360p", 360, 800),
    ("480p", 480, 1400),
    ("720p", 720, 2800),
]


def _update_video(video_id: int, **fields) -> None:
    """UPDATE générique sur la table videos (champs whitelisés par l'appelant)."""
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


def transcode_video(video_id: int, video_path: Path, uploads_dir: Path):
    """Génère les versions 360/480/720 à côté de la source.

    La source originale reste toujours lisible : si tout échoue, on marque
    `error` (au lieu de `done` mensonger) mais la lecture reste possible.
    """
    _update_video(video_id, transcoding_status="processing")
    done = []
    attempted = 0
    try:
        for name, height, bitrate in QUALITIES:
            out = uploads_dir / f"{video_path.stem}_{name}.mp4"
            if out.exists() and out.stat().st_size > 0:
                done.append(name)
                continue
            attempted += 1
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
        # error seulement si on a tenté des conversions et que TOUTES ont échoué.
        status = "error" if (attempted and not done) else "done"
        _update_video(video_id, qualities=",".join(done), transcoding_status=status)
    except Exception:
        _update_video(video_id, qualities=",".join(done), transcoding_status="error")
    return done


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
        generated = out_vtt.parent / (video_path.stem + ".vtt")
        if generated.exists() and generated != out_vtt:
            generated.rename(out_vtt)
        return out_vtt.exists()
    except Exception:
        return False
