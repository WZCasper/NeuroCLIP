"""
Извлечение аудиодорожки из видео через ffmpeg — реальный вызов внешнего
процесса, не имитация. Нужен установленный ffmpeg (обычно уже есть в
системе; на Windows — https://ffmpeg.org/download.html, добавить в PATH).
"""

import os
import subprocess
import tempfile


class AudioExtractionError(Exception):
    """Не удалось извлечь аудио из видео (нет ffmpeg, нет звуковой дорожки и т.п.)."""


def extract_audio(video_path: str, target_sr: int = 22050) -> str:
    """
    Извлекает аудиодорожку видео в отдельный WAV-файл (моно, PCM 16-бит).
    Возвращает путь к ВРЕМЕННОМУ файлу — вызывающая сторона обязана удалить
    его после использования (см. try/finally в analysis_pipeline.py).
    """
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="neuroclip_audio_")
    os.close(fd)

    command = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",                     # без видео
        "-acodec", "pcm_s16le",
        "-ar", str(target_sr),
        "-ac", "1",                 # моно
        wav_path,
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except FileNotFoundError as exc:
        os.remove(wav_path) if os.path.exists(wav_path) else None
        raise AudioExtractionError(
            "ffmpeg не найден в системе. Установите его: https://ffmpeg.org/download.html "
            "и убедитесь, что он доступен в PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        if os.path.exists(wav_path):
            os.remove(wav_path)
        raise AudioExtractionError("Извлечение аудио заняло слишком много времени (>10 минут).") from exc

    if result.returncode != 0:
        if os.path.exists(wav_path):
            os.remove(wav_path)
        stderr_tail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "неизвестная ошибка"
        raise AudioExtractionError(f"ffmpeg не смог извлечь аудио: {stderr_tail}")

    if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
        raise AudioExtractionError("Аудиодорожка не найдена в видео (файл может быть без звука).")

    return wav_path
