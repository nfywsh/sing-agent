"""Audio preprocessing module for SoulX-Singer."""

import soundfile as sf
import numpy as np
import os
import tempfile
from scipy import signal


def prepare_audio_for_soulx(audio_path: str, target_sr: int = 24000) -> str:
    """Convert audio to 24kHz mono WAV format for SoulX-Singer.

    SoulX-Singer internally uses 24kHz sample rate. Using native 24kHz
    avoids double resampling (24kHz→16kHz→24kHz) which causes quality loss.

    Args:
        audio_path: Path to input audio file (any format supported by soundfile).
        target_sr: Target sample rate (default 24000, matching SoulX-Singer config).

    Returns:
        Path to the converted WAV file in temporary directory.

    Raises:
        FileNotFoundError: If input file does not exist.
        ValueError: If audio cannot be loaded or converted.
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        # Load audio using soundfile
        audio_data, sr = sf.read(audio_path, dtype='float32')

        # Convert to mono if stereo
        if audio_data.ndim > 1:
            audio_data = audio_data[:, 0]

        # Resample to target sample rate if necessary
        if sr != target_sr:
            # Use scipy for resampling (faster than librosa)
            num_samples = int(len(audio_data) * target_sr / sr)
            audio_data = signal.resample(audio_data, num_samples)

        # Ensure float32 range is valid
        audio_data = np.clip(audio_data, -1.0, 1.0)

        # Save to temporary directory as WAV
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"soulx_input_{os.getpid()}_{id(audio_path)}.wav")
        sf.write(temp_path, audio_data, target_sr, subtype='PCM_16')

        return temp_path

    except Exception as e:
        raise ValueError(f"Failed to process audio: {e}") from e


def validate_audio_format(audio_path: str) -> tuple[bool, dict]:
    """Validate that audio is 24kHz mono WAV for SoulX-Singer.

    Args:
        audio_path: Path to audio file to validate.

    Returns:
        Tuple of (is_valid, info_dict) where info_dict contains:
        - sample_rate: int
        - channels: int
        - duration: float (seconds)
        - format: str
        - subtype: str
        - is_valid: bool
        - errors: list of validation error messages
    """
    info = {
        "sample_rate": 0,
        "channels": 0,
        "duration": 0.0,
        "format": "",
        "subtype": "",
        "is_valid": True,
        "errors": []
    }

    if not os.path.exists(audio_path):
        info["is_valid"] = False
        info["errors"].append(f"File not found: {audio_path}")
        return False, info

    try:
        # Get audio info without loading full file
        info_dict = sf.info(audio_path)
        info["sample_rate"] = info_dict.samplerate
        info["channels"] = info_dict.channels
        info["duration"] = info_dict.duration
        info["format"] = info_dict.format
        info["subtype"] = info_dict.subtype

        # Validate sample rate (SoulX-Singer uses 24kHz)
        if info_dict.samplerate != 24000:
            info["is_valid"] = False
            info["errors"].append(f"Expected 24kHz sample rate, got {info_dict.samplerate}Hz")

        # Validate channels (WhisperFeatureExtractor only supports mono)
        if info_dict.channels != 1:
            info["is_valid"] = False
            info["errors"].append(f"Expected mono (1 channel), got {info_dict.channels} channels")

        # Validate format is WAV
        if info_dict.format != 'WAV':
            info["is_valid"] = False
            info["errors"].append(f"Expected WAV format, got {info_dict.format}")

    except Exception as e:
        info["is_valid"] = False
        info["errors"].append(f"Failed to read audio info: {e}")

    return info["is_valid"], info