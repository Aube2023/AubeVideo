"""AubeVideo - utilitaires média (FFmpeg/FFprobe)."""
import subprocess
import json
import shutil
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


def ffprobe_duration(video_path: Path) -> int:
    """Retourne la durée en secondes (entier). 0 si erreur."""
    try:
        out = subprocess.check_output(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(video_path)],
            stderr=subprocess.DEVNULL, timeout=30,
        )
        data = json.loads(out)
        return int(float(data.get("format", {}).get("duration", 0)))
    except Exception:
        return 0


def generate_thumbnail(video_path: Path, out_path: Path, timestamp_sec: int = 1) -> bool:
    """Génère une miniature JPG depuis la vidéo (capture à timestamp)."""
    try:
        subprocess.run(
            [FFMPEG, "-y", "-ss", str(timestamp_sec), "-i", str(video_path),
             "-vframes", "1", "-vf", "scale=1280:-1", "-q:v", "3", str(out_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60,
        )
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception:
        return False


def srt_to_vtt(text: str) -> str:
    """Convertit un sous-titrage SRT en WEBVTT (passe linéaire)."""
    out = ["WEBVTT", ""]
    for line in text.splitlines():
        if "-->" in line:
            line = line.replace(",", ".")
        if not line.strip().isdigit():
            out.append(line)
    return "\n".join(out)


def probe_metadata(video_path: Path) -> dict:
    """Retourne {duration, width, height, codec} ou {} en cas d'erreur."""
    try:
        out = subprocess.check_output(
            [FFPROBE, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,codec_name:format=duration",
             "-of", "json", str(video_path)],
            stderr=subprocess.DEVNULL, timeout=30,
        )
        data = json.loads(out)
        stream = (data.get("streams") or [{}])[0]
        duration = int(float(data.get("format", {}).get("duration", 0)))
        return {
            "duration": duration,
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "codec": stream.get("codec_name", ""),
        }
    except Exception:
        return {"duration": 0, "width": 0, "height": 0, "codec": ""}
