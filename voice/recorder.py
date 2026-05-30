import os
import sounddevice as sd
import soundfile as sf
import tempfile
import time
import threading
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, Union

import numpy as np
import requests
from requests.adapters import HTTPAdapter
from scipy.signal import resample_poly

from core.hardware_config import using_glasses


class VoiceRecordingError(Exception):
    pass


class VoiceRecorder:
    def __init__(self, target_sample_rate: int = 16000, channels: int = 1, dtype: str = "float32"):
        self.target_sample_rate = int(target_sample_rate)
        self.channels = int(channels)
        self.dtype = dtype
        self.last_device: Optional[int] = None
        self.last_device_name = ""
        self.last_sample_rate = self.target_sample_rate
        self.last_native_sample_rate = self.target_sample_rate
        self.last_tobii_error = ""
        self.active_source = "local"

    def record(
        self,
        duration: float,
        *,
        tobii_runtime: Any | None = None,
        task_runner: Optional[Callable[[Callable[[], None], Callable[[], None]], None]] = None,
    ) -> Tuple[np.ndarray, int]:
        """Record Tobii audio first, while recording the local mic as fallback.

        The recorder is intentionally quiet. User instructions should be printed
        or spoken by task_runner, which is called only after the recorder is ready.
        """
        if duration <= 0:
            raise VoiceRecordingError("Recording duration must be positive")

        self.last_tobii_error = ""
        self.active_source = "local"

        runtime = tobii_runtime
        if runtime is None and using_glasses():
            from ui.eye_tracking_runtime_glasses import EyeTrackingRuntime

            runtime = EyeTrackingRuntime()

        detected_host = getattr(runtime, "active_host", None) if runtime is not None else None
        recording_uuid = getattr(runtime, "current_recording_uuid", None) if runtime is not None else None
        recording_started_at = getattr(runtime, "recording_started_at", None) if runtime is not None else None
        has_active_tobii_recording = bool(
            getattr(runtime, "active", False)
            and detected_host
            and recording_uuid
            and recording_started_at
        )

        tobii_started = False
        is_standalone_tobii_run = False

        if has_active_tobii_recording:
            tobii_started = True
        elif runtime is not None and tobii_runtime is None and using_glasses():
            try:
                ok, start_error = runtime.start(subject_id="voice_standalone")
                if ok:
                    tobii_started = True
                    is_standalone_tobii_run = True
                    detected_host = getattr(runtime, "active_host", None)
                    recording_uuid = getattr(runtime, "current_recording_uuid", None)
                    recording_started_at = getattr(runtime, "recording_started_at", None)
                else:
                    self.last_tobii_error = start_error or "Tobii recording did not start"
            except Exception as exc:
                self.last_tobii_error = str(exc)

        local_device = self.available_input_device()
        local_chunks: list[np.ndarray] = []
        local_error: list[Exception | None] = [None]
        local_ready_event = threading.Event()
        local_stop_event = threading.Event()
        local_start_timestamp = [0.0]
        local_lock = threading.Lock()
        local_sample_count = [0]
        local_window_start_sample: list[int | None] = [None]
        local_window_end_sample: list[int | None] = [None]

        def record_local_thread() -> None:
            try:
                def on_audio(indata, frames, time_info, status) -> None:
                    with local_lock:
                        local_chunks.append(indata.copy())
                        local_sample_count[0] += int(frames)

                with sd.InputStream(
                    samplerate=self.target_sample_rate,
                    channels=self.channels,
                    dtype=self.dtype,
                    device=local_device,
                    callback=on_audio,
                ):
                    local_start_timestamp[0] = time.time()
                    local_ready_event.set()
                    while not local_stop_event.wait(0.05):
                        pass
            except Exception as exc:
                local_error[0] = exc
                local_ready_event.set()

        local_thread: threading.Thread | None = None

        def ensure_local_recording_started() -> None:
            nonlocal local_thread
            if local_thread is None:
                local_thread = threading.Thread(target=record_local_thread, daemon=True)
                local_thread.start()
            local_ready_event.wait(timeout=5.0)
            if local_error[0] is not None:
                self.last_tobii_error = self.last_tobii_error or str(local_error[0])

        self.last_device = local_device
        self.last_device_name = self.describe_device(local_device)
        self.last_native_sample_rate = self.target_sample_rate

        marked_start: list[float | None] = [None]
        marked_end: list[float | None] = [None]

        def mark_start() -> None:
            ensure_local_recording_started()
            marked_start[0] = time.time()
            with local_lock:
                local_window_start_sample[0] = local_sample_count[0]

        def mark_end() -> None:
            marked_end[0] = time.time()
            with local_lock:
                local_window_end_sample[0] = local_sample_count[0]
            local_stop_event.set()

        if task_runner is None:
            mark_start()
            time.sleep(float(duration))
            mark_end()
        else:
            task_runner(mark_start, mark_end)
            if marked_start[0] is None:
                marked_start[0] = time.time()
            if marked_end[0] is None:
                marked_end[0] = time.time()

        speech_window_start_ts = float(marked_start[0])
        speech_window_end_ts = float(marked_end[0])
        if speech_window_end_ts <= speech_window_start_ts:
            speech_window_end_ts = speech_window_start_ts + float(duration)
        if local_thread is None:
            ensure_local_recording_started()
            local_stop_event.set()

        detected_host = getattr(runtime, "active_host", detected_host)
        recording_uuid = getattr(runtime, "current_recording_uuid", recording_uuid)
        recording_started_at = getattr(runtime, "recording_started_at", recording_started_at)

        if tobii_started and detected_host and recording_uuid and not has_active_tobii_recording:
            try:
                if is_standalone_tobii_run:
                    runtime.stop()

                audio_bytes = None
                detected_suffix = ".wav"
                max_retries = 4
                for attempt in range(1, max_retries + 1):
                    try:
                        time.sleep(4.0)
                        audio_bytes, detected_suffix = self._fetch_tobii_media_data(detected_host, recording_uuid)
                        if audio_bytes:
                            break
                    except Exception:
                        if attempt == max_retries:
                            raise

                if audio_bytes:
                    audio, sample_rate = self._decode_audio_data(audio_bytes, detected_suffix)
                    audio = self._ensure_mono(audio)

                    if sample_rate != self.target_sample_rate:
                        audio = self._resample(audio, sample_rate, self.target_sample_rate)

                    if recording_started_at:
                        offset_start_s = max(0.0, speech_window_start_ts - float(recording_started_at))
                        offset_end_s = max(offset_start_s, speech_window_end_ts - float(recording_started_at))
                        start_idx = int(round(offset_start_s * self.target_sample_rate))
                        end_idx = int(round(offset_end_s * self.target_sample_rate))
                        audio = audio[start_idx:min(len(audio), end_idx)]

                    if audio.size > 0:
                        self.active_source = "tobii"
                        self.last_device = None
                        self.last_device_name = f"Tobii Glasses REST ({detected_host})"
                        self.last_native_sample_rate = int(sample_rate)
                        if is_standalone_tobii_run:
                            runtime.reset()
                        return audio.astype(np.float32), self.target_sample_rate
            except Exception as exc:
                self.last_tobii_error = str(exc)

        if is_standalone_tobii_run:
            runtime.reset()

        if local_thread is not None and local_thread.is_alive():
            local_thread.join(timeout=1.0)

        self.active_source = "local"
        self.last_device = local_device
        self.last_device_name = self.describe_device(local_device)
        self.last_native_sample_rate = self.target_sample_rate

        if local_chunks:
            with local_lock:
                audio_full = np.concatenate(local_chunks, axis=0).astype(np.float32).flatten()
                start_sample = local_window_start_sample[0]
                end_sample = local_window_end_sample[0]
            if start_sample is None or end_sample is None or end_sample <= start_sample:
                offset_start_s = speech_window_start_ts - local_start_timestamp[0]
                offset_end_s = speech_window_end_ts - local_start_timestamp[0]
                start_idx = int(max(0, offset_start_s * self.target_sample_rate))
                end_idx = int(min(len(audio_full), offset_end_s * self.target_sample_rate))
            else:
                start_idx = int(max(0, start_sample * self.channels))
                end_idx = int(min(len(audio_full), end_sample * self.channels))
            audio_window = audio_full[start_idx:end_idx]
            if audio_window.size > 0:
                return self._ensure_mono(audio_window), self.target_sample_rate

        detail = f" Local mic error: {local_error[0]}" if local_error[0] else ""
        raise VoiceRecordingError(f"Both Tobii and local mic recording streams failed.{detail}")

    def _fetch_tobii_media_data(self, host: str, recording_uuid: str) -> Tuple[bytes, str]:
        session = requests.Session()
        session.mount("http://", HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0))
        http_path = ""
        try:
            res = session.get(f"http://{host}/rest/recordings/{recording_uuid}.http-path", timeout=2.5)
            if res.status_code == 200:
                res_json = res.json()
                http_path = res_json.get("value", res.text) if isinstance(res_json, dict) else str(res_json)
                http_path = str(http_path).strip().strip('"').strip("/")
        except Exception:
            pass

        if not http_path:
            raise VoiceRecordingError("Could not resolve Tobii storage path")

        metadata = self._fetch_tobii_recording_metadata(session, host, http_path)
        candidates = self._audio_file_candidates(metadata)
        ordered_candidates = ["audio.wav", "microphone.wav", "live.wav"]
        ordered_candidates.extend([c for c in candidates if str(c).lower().endswith(".wav")])
        ordered_candidates.extend([c for c in candidates if str(c).lower().endswith(".mp4")])
        ordered_candidates.extend(["live.mp4", "fullstream.mp4", "audio.mp4"])

        seen = set()
        for media_name in ordered_candidates:
            media_name = str(media_name).strip("/")
            if media_name in seen:
                continue
            seen.add(media_name)
            url = f"http://{host}/{http_path}/{media_name}"
            try:
                res = session.get(url, timeout=4.0)
                if res.status_code == 200 and res.content and len(res.content) > 5000:
                    return res.content, Path(media_name).suffix.lower()
            except Exception:
                continue

        raise VoiceRecordingError("Target audio files could not be extracted from Tobii storage")

    def extract_tobii_window(
        self,
        host: str,
        recording_uuid: str,
        start_offset: float,
        duration: float,
    ) -> Tuple[np.ndarray, int]:
        audio_bytes, suffix = self._fetch_tobii_media_data(host, recording_uuid)
        audio, sample_rate = self._decode_audio_data(audio_bytes, suffix)
        audio = self._ensure_mono(audio)

        if sample_rate != self.target_sample_rate:
            audio = self._resample(audio, sample_rate, self.target_sample_rate)

        start_idx = int(round(max(0.0, float(start_offset)) * self.target_sample_rate))
        end_idx = int(round(max(float(start_offset), float(start_offset) + float(duration)) * self.target_sample_rate))
        audio = audio[start_idx:min(len(audio), end_idx)]
        if audio.size <= 0:
            raise VoiceRecordingError("Tobii audio window was empty")

        self.active_source = "tobii"
        self.last_device = None
        self.last_device_name = f"Tobii Glasses REST ({host})"
        self.last_native_sample_rate = int(sample_rate)
        return audio.astype(np.float32), self.target_sample_rate

    def _fetch_tobii_recording_metadata(self, session, host: str, http_path: str) -> Any:
        for relative_path in (f"{http_path}/recording.g3", http_path):
            try:
                res = session.get(f"http://{host}/{relative_path}", timeout=2.5)
                if res.status_code == 200:
                    return res.json()
            except Exception:
                continue
        return {}

    def _decode_audio_data(self, data: bytes, suffix: str) -> Tuple[np.ndarray, int]:
        import io
        import warnings

        if suffix == ".wav":
            try:
                return sf.read(io.BytesIO(data), dtype="float32")
            except Exception:
                pass

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            from moviepy import AudioFileClip

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                audio_clip = AudioFileClip(tmp_path)
                return audio_clip.to_soundarray(fps=audio_clip.fps), int(audio_clip.fps)
        except Exception:
            try:
                import librosa

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    audio, sample_rate = librosa.load(tmp_path, sr=self.target_sample_rate, mono=True)
                return audio, int(sample_rate)
            except Exception as exc:
                raise VoiceRecordingError(f"Failed to decode Tobii audio media: {exc}")
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    def available_input_device(self) -> Optional[int]:
        try:
            default_input = sd.default.device[0]
            if isinstance(default_input, int) and default_input >= 0:
                return default_input
        except Exception:
            pass
        return 0

    def describe_device(self, device_index: Optional[int]) -> str:
        if device_index is None:
            return ""
        try:
            return str(sd.query_devices(device_index).get("name") or device_index)
        except Exception:
            return str(device_index)

    def _audio_file_candidates(self, value: Any) -> list[str]:
        matches = []
        audio_exts = (".wav", ".flac", ".ogg", ".opus", ".aac", ".m4a", ".mp3", ".mp4")

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for child in node.values():
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)
            elif isinstance(node, str):
                if any(node.lower().endswith(ext) for ext in audio_exts):
                    matches.append(node)

        walk(value)
        return matches

    def _resample(self, audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
        gcd = np.gcd(int(source_rate), int(target_rate))
        return resample_poly(audio, int(target_rate) // gcd, int(source_rate) // gcd).astype(np.float32)

    def save(self, audio: np.ndarray, sample_rate: int, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), audio, int(sample_rate), subtype="PCM_16")
        return path

    def _ensure_mono(self, audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 1:
            return audio.astype(np.float32)
        if audio.ndim == 2:
            return np.mean(audio, axis=1).astype(np.float32)
        return np.asarray(audio).flatten().astype(np.float32)
