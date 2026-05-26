FROM soulx-singer:v2

# Fix torchaudio compatibility issue:
# The container has FFmpeg 4 with libavutil.so.56 but torchcodec (used by torchaudio.load)
# requires FFmpeg 5-8 with libavutil.so.57-60. The solution is to:
# 1. Uninstall torchcodec
# 2. Patch audio_utils.py to use soundfile/librosa for audio loading instead of torchaudio

# Uninstall torchcodec (not compatible with FFmpeg 4 in this container)
RUN pip uninstall -y torchcodec

# Patch audio_utils.py to use soundfile instead of torchaudio for audio loading
RUN cat > /workspace/SoulX-Singer/soulxsinger/utils/audio_utils.py << 'PYTHON'
import torch
import soundfile as sf
import numpy as np
import librosa


def load_wav(wav_path: str, sample_rate: int):
    """Load wav file and resample to target sample rate.

    Args:
        wav_path (str): Path to wav file.
        sample_rate (int): Target sample rate.

    Returns:
        torch.Tensor: Waveform tensor with shape (1, T).
    """
    # Use soundfile to load audio
    waveform, sr = sf.read(wav_path, dtype='float32')

    # Convert to torch tensor
    waveform = torch.from_numpy(waveform).float()

    # Ensure channel dimension
    if len(waveform.shape) == 1:
        waveform = waveform.unsqueeze(0)

    # Resample if needed using librosa (v0.10+ uses librosa.resample)
    if sr != sample_rate:
        waveform = torch.from_numpy(librosa.resample(
            waveform.numpy(), orig_sr=sr, target_sr=sample_rate
        )).float()

    # Convert stereo to mono if needed
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)

    return waveform
PYTHON

CMD ["python", "webui_svc.py"]