import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from typing import Optional, Tuple, Union


class VoiceRecordingError(Exception):
    pass


class VoiceRecorder:
    def __init__(self, target_sample_rate: int = 16000, channels: int = 1, dtype: str = "float32"):
        self.target_sample_rate = int(target_sample_rate)
        self.channels = int(channels)
        self.dtype = dtype

    def available_input_device(self) -> Optional[int]:
        try:
            default_input = sd.default.device[0]
            if isinstance(default_input, int) and default_input >= 0:
                return default_input
        except Exception:
            pass

        try:
            devices = sd.query_devices()
        except Exception:
            return None

        for index, device in enumerate(devices):
            try:
                if device.get("max_input_channels", 0) > 0:
                    return index
            except Exception:
                continue

        return None

    def record(self, duration: float) -> Tuple[np.ndarray, int]:
        if duration <= 0:
            raise VoiceRecordingError("Recording duration must be positive")

        device = self.available_input_device()
        if device is None:
            raise VoiceRecordingError("No microphone input device available")

        frames = int(round(duration * self.target_sample_rate))
        if frames < 1:
            raise VoiceRecordingError("Recording duration is too short")

        try:
            sd.check_input_settings(
                device=device,
                samplerate=self.target_sample_rate,
                channels=self.channels,
            )
            recording = sd.rec(
                frames,
                samplerate=self.target_sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                device=device,
            )
            sd.wait()

        except Exception as exc:
            raise VoiceRecordingError(
                f"Failed to record audio: {exc}"
            ) from exc

        audio = np.asarray(recording, dtype=np.float32)
        audio = self._ensure_mono(audio)
        return audio, self.target_sample_rate

    def save(self, audio: np.ndarray, sample_rate: int, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio, int(sample_rate), subtype="PCM_16")
        return path

    def _ensure_mono(self, audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 1:
            return audio
        if audio.ndim == 2:
            return np.mean(audio, axis=1).astype(np.float32)
        return np.asarray(audio).flatten().astype(np.float32)
