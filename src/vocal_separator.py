"""Vocal separation module using Demucs."""

import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "htdemucs"


def separate_vocals(audio_path: str, output_dir: str = "/tmp/separated") -> str:
    """使用 Demucs 进行人声分离"""
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    os.makedirs(output_dir, exist_ok=True)
    filename = Path(audio_path).stem

    cmd = [
        "demucs",
        "--out", output_dir,
        "--two-stems", "vocals",
        "-n", DEFAULT_MODEL,
        audio_path
    ]

    logger.info(f"Running Demucs: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"Demucs failed: {result.stderr}")
            raise RuntimeError(f"Demucs separation failed: {result.stderr}")

        vocal_path = os.path.join(output_dir, DEFAULT_MODEL, filename, "vocals.wav")

        if not os.path.exists(vocal_path):
            raise RuntimeError(f"Demucs output not found. Expected: {vocal_path}")

        logger.info(f"Vocal separation complete: {vocal_path}")
        return vocal_path

    except subprocess.TimeoutExpired:
        raise RuntimeError("Demucs timed out after 5 minutes")
    except FileNotFoundError:
        raise RuntimeError("Demucs not found. Please install: pip install demucs")


class VocalSeparator:
    """人声分离器封装类."""

    def __init__(self, output_dir: str = "/tmp/separated", model: str = "htdemucs"):
        self.output_dir = output_dir
        self.model = model
        self._check_demucs()

    def _check_demucs(self):
        try:
            subprocess.run(["demucs", "--version"], capture_output=True, timeout=10)
            logger.info("Demucs is available")
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Demucs not available: {e}")

    def separate(self, audio_path: str) -> str:
        return separate_vocals(audio_path, self.output_dir)

    def is_available(self) -> bool:
        try:
            subprocess.run(["demucs", "--help"], capture_output=True, timeout=10)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
