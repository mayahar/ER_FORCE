import json
import time
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

import numpy as np
import sounddevice as sd
import soundfile as sf

from .events import VoiceEvent
from .recorder import VoiceRecorder, VoiceRecordingError
from .processing import VoiceFeatureExtractor, VoiceFeatureExtractionError
from .tts import speak_text
from core.hardware_config import using_glasses

pd = None


def _get_pandas():
    global pd
    if pd is None:
        try:
            import pandas as pandas_module
        except ImportError:
            return None
        pd = pandas_module
    return pd


class VoiceSessionError(Exception):
    pass


class VoiceSessionManager:
    DEFAULT_RECORDING_ROOT = Path("temp_voice_recordings")
    DEFAULT_REPORTS_ROOT = Path("voice_reports")
    FEATURE_ARRAY_KEYS = ("mfcc", "pitch", "lpc", "parcor", "delta_lpc")

    # ׳§׳•׳‘׳¥ ׳”ײ¾WAV ׳©׳ ׳”׳¦׳׳™׳ "׳׳׳׳׳"
    PROMPT_AUDIO_FILE = Path(__file__).parent / "Ahhhh.wav"

    def __init__(
        self,
        subject_id: Optional[str] = None,
        session_id: Optional[str] = None,
        events: Optional[List[VoiceEvent]] = None,
        recording_root: Optional[Path] = None,
        speak_prompts: bool = True,
        tobii_runtime: Any | None = None,
    ):
        self.subject_id = str(subject_id) if subject_id is not None else None
        self.session_id = str(session_id or int(time.time()))
        self.recorder = VoiceRecorder()
        self.speak_prompts = bool(speak_prompts)
        self.tobii_runtime = tobii_runtime
        self.start_timestamp: Optional[float] = None
        self.finish_timestamp: Optional[float] = None
        self.events = events if events is not None else self._default_events()

        if recording_root:
            self.recording_root = Path(recording_root)
        else:
            self.recording_root = Path(self.DEFAULT_RECORDING_ROOT) / self.session_id
        self.recording_root.mkdir(parents=True, exist_ok=True)
        self.attempts_root = self.recording_root / "attempts"
        self.attempts_root.mkdir(parents=True, exist_ok=True)
        self.attempt_index = self._next_attempt_index()
        self.attempt_id = f"attempt_{self.attempt_index:03d}"
        self.attempt_dir = self.attempts_root / self.attempt_id
        self.attempt_dir.mkdir(parents=True, exist_ok=True)
        self.attempt_log_path = self.attempt_dir / "attempt_log.json"

        # Pre-load prompt audio to ensure immediate transition after TTS
        self._prompt_audio_cache = None
        self._prompt_sr_cache = None
        self._preload_prompt_audio()

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._active_future: Optional[Future] = None
        self._active_event_id: Optional[str] = None
        self._finalized = False
        self._event_results: List[Dict[str, Any]] = []
        self._write_attempt_log({"status": "created"})

    def _next_attempt_index(self) -> int:
        existing = []
        for path in self.attempts_root.glob("attempt_*"):
            if not path.is_dir():
                continue
            try:
                existing.append(int(path.name.rsplit("_", 1)[1]))
            except Exception:
                continue
        return (max(existing) + 1) if existing else 1

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, np.ndarray):
            return {
                "type": "ndarray",
                "shape": list(value.shape),
                "dtype": str(value.dtype),
            }
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            safe = {}
            for key, child in value.items():
                if key == "samples":
                    safe[key] = self._json_safe(child)
                else:
                    safe[key] = self._json_safe(child)
            return safe
        if isinstance(value, list):
            return [self._json_safe(child) for child in value]
        if isinstance(value, tuple):
            return [self._json_safe(child) for child in value]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        return value

    def _event_snapshot(self, event: VoiceEvent) -> Dict[str, Any]:
        return {
            "event_id": event.event_id,
            "status": event.status,
            "timestamp": event.timestamp,
            "duration": event.duration,
            "audio_path": str(event.audio_path) if event.audio_path else None,
            "error": event.error,
            "metadata": self._json_safe(event.metadata),
        }

    def _write_attempt_log(self, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "attempt_id": self.attempt_id,
            "attempt_index": self.attempt_index,
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "recording_root": str(self.recording_root),
            "attempt_dir": str(self.attempt_dir),
            "started_at": self.start_timestamp,
            "finished_at": self.finish_timestamp,
            "events": [self._event_snapshot(event) for event in self.events],
        }
        if extra:
            payload.update(self._json_safe(extra))
        with self.attempt_log_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _save_attempt_features(self, event: VoiceEvent, features: Dict[str, Any]) -> Path:
        path = self.attempt_dir / f"{event.event_id}_features_raw.npz"
        arrays = {
            key: np.asarray(value)
            for key, value in features.items()
            if value is not None
        }
        if arrays:
            np.savez_compressed(path, **arrays)
            event.metadata["raw_features_path"] = str(path)
        return path

    def _default_events(self) -> List[VoiceEvent]:
        return [
            VoiceEvent(
                event_id="voice_phrase_1",
                prompt_text="Sustained vowel 'Ah'",
                duration=10.0,
                trigger_time=5.0,
                prompt_type="phrase",
                event_type="phrase",
            )
        ]

    def _preload_prompt_audio(self) -> None:
        """Loads the prompt audio file into memory to minimize latency during playback."""
        try:
            if self.PROMPT_AUDIO_FILE.exists():
                audio, sr = sf.read(str(self.PROMPT_AUDIO_FILE), dtype="float32")
                if audio.ndim > 1:
                    audio = np.mean(audio, axis=1)
                self._prompt_audio_cache = audio
                self._prompt_sr_cache = int(sr)
        except Exception:
            pass

    @property
    def pending_events(self) -> List[VoiceEvent]:
        return [event for event in self.events if event.status == "pending"]

    @property
    def completed_events(self) -> List[VoiceEvent]:
        return [event for event in self.events if event.status == "completed"]

    @property
    def failed_events(self) -> List[VoiceEvent]:
        return [event for event in self.events if event.status == "failed"]

    @property
    def active_event(self) -> Optional[VoiceEvent]:
        return next((event for event in self.events if event.status == "recording"), None)

    @property
    def current_prompt(self) -> Optional[str]:
        active = self.active_event

        if active is not None:
            return f"Recording now: {active.prompt_text}"

        next_event = next((event for event in self.pending_events), None)

        if next_event is not None:
            return f"Upcoming prompt in the session: {next_event.prompt_text}"

        return None

    def start_session(self) -> None:
        self.start_timestamp = time.time()
        self.finish_timestamp = None
        self._finalized = False
        self._write_attempt_log({"status": "started"})

    def update(self, elapsed_time: float) -> None:
        if self._finalized:
            return

        if self.active_event is not None:
            return

        for event in self.events:
            if event.status == "pending" and elapsed_time >= event.trigger_time:
                self._begin_event(event)
                break

    def trigger_gameplay_event(self, event_type: str) -> None:
        if self.active_event is not None:
            return

        target = next(
            (
                event
                for event in self.events
                if event.status == "pending" and event.event_type == event_type
            ),
            None,
        )

        if target is not None:
            self._begin_event(target)

    def _begin_event(self, event: VoiceEvent) -> None:
        event.status = "recording"
        event.timestamp = time.time()
        self._active_event_id = event.event_id
        event.metadata["attempt_id"] = self.attempt_id
        event.metadata["attempt_dir"] = str(self.attempt_dir)
        self._write_attempt_log({"status": "recording", "active_event_id": event.event_id})
        self._active_future = self._executor.submit(self._record_event, event)

    def _play_prompt_audio(self) -> None:
        if self._prompt_audio_cache is not None:
            sd.play(self._prompt_audio_cache, self._prompt_sr_cache)
            sd.wait()
            return

        if not self.PROMPT_AUDIO_FILE.exists():
            raise FileNotFoundError(
                f"Prompt audio file not found: {self.PROMPT_AUDIO_FILE}"
            )

        audio, sr = sf.read(str(self.PROMPT_AUDIO_FILE), dtype="float32")

        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        sd.play(audio, sr)
        sd.wait()

    def _record_event(self, event: VoiceEvent) -> None:
        try:
            is_tobii_mode = using_glasses() and self.tobii_runtime is not None
            tobii_audio = None

            if is_tobii_mode:
                print("[ER Force Voice] ׳׳׳×׳™׳ ׳׳™׳™׳¦׳•׳‘ ׳¢׳¨׳•׳¥ ׳”׳׳•׳“׳™׳• ׳”׳׳׳—׳•׳˜׳™ ׳׳•׳ ׳”׳׳©׳§׳₪׳™׳™׳...")
                max_wait = 5.0
                start_wait_ts = time.time()
                tobii_audio = self._active_tobii_audio_context()
                
                while tobii_audio is None and (time.time() - start_wait_ts) < max_wait:
                    time.sleep(0.1)
                    tobii_audio = self._active_tobii_audio_context()
                
                if tobii_audio is None:
                    event.metadata["tobii_audio_warning"] = (
                        "No active Tobii recording was available; using local microphone."
                    )

            # ׳”׳ ׳—׳™׳•׳× ׳§׳•׳׳™׳•׳× ׳׳׳©׳×׳׳© (TTS) ׳׳₪׳ ׳™ ׳×׳—׳™׳׳× ׳—׳׳•׳ ׳”׳”׳§׳׳˜׳” ׳”׳׳¡׳•׳ ׳›׳¨׳
            voice_window = {}

            def run_voice_prompt(mark_start, mark_end):
                if self.speak_prompts:
                    try:
                        speak_text("Please keep making the following sound continuously until told to stop")
                        self._play_prompt_audio()
                        speak_text("Recording started.")
                    except Exception as exc:
                        event.metadata["tts_error"] = str(exc)

                voice_window["start_ts"] = time.time()
                mark_start()
                time.sleep(float(event.duration))
                mark_end()
                voice_window["end_ts"] = time.time()

            # ׳§׳¨׳™׳׳” ׳׳׳§׳׳™׳˜ ׳”׳׳¨׳›׳–׳™ ׳©׳׳ ׳”׳ ׳׳× ׳”-Countdown ׳‘׳¦׳•׳¨׳” ׳׳¡׳•׳ ׳›׳¨׳ ׳×
            audio, sample_rate = self.recorder.record(
                event.duration,
                tobii_runtime=self.tobii_runtime,
                task_runner=run_voice_prompt,
            )
            
            # ׳©׳׳™׳¨׳× ׳”׳ ׳×׳•׳ ׳™׳ ׳‘׳”׳×׳׳ ׳׳׳•׳“ ׳”׳₪׳¢׳™׳
            if tobii_audio is not None:
                tobii_audio = self._active_tobii_audio_context() or tobii_audio
                recording_started_at = float(tobii_audio["recording_started_at"])
                event.metadata["tobii_audio_window"] = {
                    **tobii_audio,
                    "start_offset": max(0.0, float(voice_window.get("start_ts", 0.0)) - recording_started_at),
                    "duration": max(
                        0.0,
                        float(voice_window.get("end_ts", 0.0)) - float(voice_window.get("start_ts", 0.0)),
                    ),
                    "source_used": self.recorder.active_source,
                }
            
            event.metadata["audio"] = {
                "samples": audio,
                "sr": sample_rate,
            }
            event.metadata["input_device"] = {
                "index": self.recorder.last_device,
                "name": self.recorder.last_device_name,
                "native_sample_rate": self.recorder.last_native_sample_rate,
            }
            event.metadata["recorder"] = {
                "initial_source": self.recorder.active_source,
                "active_source": self.recorder.active_source,
                "last_tobii_error": self.recorder.last_tobii_error,
            }
            
            event.audio_path = self.attempt_dir / f"{event.event_id}_recorded.wav"
            self.recorder.save(audio, sample_rate, event.audio_path)
            latest_path = self.recording_root / f"{event.event_id}.wav"
            self.recorder.save(audio, sample_rate, latest_path)
            event.metadata["latest_audio_path"] = str(latest_path)
            event.status = "completed"
            self._write_attempt_log({"status": "recorded", "active_event_id": event.event_id})
            
            if self.speak_prompts:
                speak_text("Recording completed. Thank you!")

        except VoiceRecordingError as exc:
            event.error = str(exc)
            event.metadata["error_code"] = "RECORDING_FAILED"
            event.status = "failed"
            self._write_attempt_log({"status": "recording_failed", "active_event_id": event.event_id})
        except Exception as exc:
            event.error = f"Unexpected recording failure: {exc}"
            event.metadata["error_code"] = "RECORDING_FAILED"
            event.status = "failed"
            self._write_attempt_log({"status": "recording_failed", "active_event_id": event.event_id})

    def _active_tobii_audio_context(self) -> Dict[str, Any] | None:
        runtime = self.tobii_runtime
        if runtime is None:
            return None
        sync = getattr(runtime, "_sync_from_runtime", None)
        if callable(sync):
            sync()
        if not getattr(runtime, "active", False):
            return None
        recording_uuid = getattr(runtime, "current_recording_uuid", None)
        host = getattr(runtime, "active_host", None)
        started_at = getattr(runtime, "recording_started_at", None)
        if not recording_uuid or not host or not started_at:
            return None
        return {
            "recording_uuid": recording_uuid,
            "host": host,
            "recording_started_at": float(started_at),
        }

    def finalize_session(self) -> Dict[str, Any]:
        if self._finalized:
            return self._build_result(include_feature_arrays=False)

        if self._active_future is not None:
            try:
                active = self.active_event
                timeout = max(45.0, (active.duration if active else 10.0) + 35.0)
                self._active_future.result(timeout=timeout)
            except Exception:
                pass

        self.finish_timestamp = time.time()
        self._event_results = []

        for event in self.completed_events:
            audio_loaded = False
            audio, sample_rate = None, None
            
            try:
                audio, sample_rate = self._load_audio(event)
                audio_loaded = True
            except Exception as exc:
                event.error = f"׳˜׳¢׳™׳ ׳× ׳”׳׳•׳“׳™׳• ׳ ׳›׳©׳׳”: {exc}"
                event.metadata["error_code"] = "AUDIO_LOAD_FAILED"
                event.status = "failed"

            features = None
            if audio_loaded:
                try:
                    features = VoiceFeatureExtractor.extract_features(
                        audio,
                        sample_rate,
                        input_device=event.metadata.get("input_device"),
                    )
                    self._save_attempt_features(event, features)
                    
                    self._event_results.append(
                        {
                            "event_id": event.event_id,
                            "prompt_text": event.prompt_text,
                            "prompt_type": event.prompt_type,
                            "event_type": event.event_type,
                            "status": event.status,
                            "timestamp": event.timestamp,
                            "duration": event.duration,
                            "attempt_id": self.attempt_id,
                            "attempt_dir": str(self.attempt_dir),
                            "audio_path": str(event.audio_path) if event.audio_path else None,
                            "input_device": event.metadata.get("input_device"),
                            "final_audio_source": event.metadata.get("final_audio_source"),
                            "error": event.error,
                            "mfcc": features["mfcc"].tolist(),
                            "pitch": features["pitch"].tolist(),
                            "lpc": features["lpc"].tolist(),
                            "parcor": features["parcor"].tolist(),
                            "delta_lpc": features["delta_lpc"].tolist(),
                        }
                    )
                except VoiceFeatureExtractionError as exc:
                    event.error = str(exc)
                    event.metadata["error_code"] = getattr(exc, "error_code", None) or "FEATURE_EXTRACTION_FAILED"
                    event.status = "failed"
                    self._write_attempt_log({"status": "feature_extraction_failed", "active_event_id": event.event_id})
                except Exception as exc:
                    event.error = str(exc)
                    event.metadata["error_code"] = "FEATURE_EXTRACTION_FAILED"
                    event.status = "failed"
                    self._write_attempt_log({"status": "feature_extraction_failed", "active_event_id": event.event_id})

            # ׳”׳‘׳˜׳—׳× ׳₪׳׳˜ ׳”׳ ׳×׳•׳ ׳™׳ ׳”׳’׳•׳׳׳™׳™׳ ׳‘׳׳™׳׳•׳ ׳’׳ ׳‘׳׳¦׳‘׳™ ׳›׳©׳ ׳©׳ ׳”׳₪׳™׳™׳₪׳׳™׳™׳
            if event.status == "failed" and audio_loaded:
                fallback_pitch = VoiceFeatureExtractor.extract_pitch(audio, sample_rate) if hasattr(VoiceFeatureExtractor, 'extract_pitch') else np.array([])
                fallback_features = {
                    "mfcc": np.zeros((len(audio) // 160, 13)),
                    "pitch": fallback_pitch if fallback_pitch.size > 0 else np.zeros(len(audio) // 160),
                    "lpc": np.zeros((len(audio) // 160, 10)),
                    "parcor": np.zeros((len(audio) // 160, 10)),
                    "delta_lpc": np.zeros(len(audio) // 160),
                }
                self._save_attempt_features(event, fallback_features)
                
                self._event_results.append(
                    {
                        "event_id": event.event_id,
                        "prompt_text": event.prompt_text,
                        "prompt_type": event.prompt_type,
                        "event_type": event.event_type,
                        "status": "failed",
                        "timestamp": event.timestamp,
                        "duration": event.duration,
                        "attempt_id": self.attempt_id,
                        "attempt_dir": str(self.attempt_dir),
                        "audio_path": str(event.audio_path) if event.audio_path else None,
                        "input_device": event.metadata.get("input_device"),
                        "final_audio_source": event.metadata.get("final_audio_source"),
                        "error": event.error,
                        "error_code": event.metadata.get("error_code"),
                        "mfcc": fallback_features["mfcc"].tolist(),
                        "pitch": fallback_features["pitch"].tolist(),
                        "lpc": fallback_features["lpc"].tolist(),
                        "parcor": fallback_features["parcor"].tolist(),
                        "delta_lpc": fallback_features["delta_lpc"].tolist(),
                    }
                )

        for event in self.failed_events:
            if not any(r["event_id"] == event.event_id for r in self._event_results):
                self._event_results.append(
                    {
                        "event_id": event.event_id,
                        "prompt_text": event.prompt_text,
                        "prompt_type": event.prompt_type,
                        "event_type": event.event_type,
                        "status": event.status,
                        "timestamp": event.timestamp,
                        "duration": event.duration,
                        "attempt_id": self.attempt_id,
                        "attempt_dir": str(self.attempt_dir),
                        "audio_path": str(event.audio_path) if event.audio_path else None,
                        "final_audio_source": event.metadata.get("final_audio_source"),
                        "error": event.error,
                        "error_code": event.metadata.get("error_code"),
                    }
                )

        self._finalized = True

        result = self._build_result(include_feature_arrays=True)
        self._write_attempt_log({"status": "finalized", "result": self._compact_result(result)})
        self._save_results_to_file_async(result)
        return self._compact_result(result)

    def _load_audio(self, event: VoiceEvent):
        tobii_window = event.metadata.get("tobii_audio_window")
        if tobii_window is not None:
            try:
                audio, sr = self.recorder.extract_tobii_window(
                    tobii_window["host"],
                    tobii_window["recording_uuid"],
                    tobii_window.get("start_offset", 0.0),
                    tobii_window.get("duration", event.duration),
                )
                rms = float(np.sqrt(np.mean(audio**2))) if audio.size > 0 else 0.0
                peak = float(np.max(np.abs(audio))) if audio.size > 0 else 0.0
                if rms < 0.0015 or peak < 0.01:
                    raise VoiceRecordingError(
                        f"Tobii audio window is too quiet for analysis (rms={rms:.6f}, peak={peak:.6f})"
                    )
                event.metadata["input_device"] = {
                    "index": self.recorder.last_device,
                    "name": self.recorder.last_device_name,
                    "native_sample_rate": self.recorder.last_native_sample_rate,
                }
                event.metadata["audio"] = {"samples": audio, "sr": sr}
                tobii_audio_path = self.attempt_dir / f"{event.event_id}_tobii_window.wav"
                self.recorder.save(audio, sr, tobii_audio_path)
                event.audio_path = tobii_audio_path
                event.metadata["final_audio_source"] = "tobii"
                event.metadata["final_audio_path"] = str(tobii_audio_path)
                recorder_meta = event.metadata.setdefault("recorder", {})
                recorder_meta["final_source"] = "tobii"
                recorder_meta["active_source"] = "tobii"
                return audio, sr
            except Exception as exc:
                event.metadata["tobii_audio_error"] = str(exc)

        stored = event.metadata.get("audio")
        if stored is not None:
            event.metadata["final_audio_source"] = event.metadata.get("final_audio_source") or "local"
            recorder_meta = event.metadata.setdefault("recorder", {})
            recorder_meta["final_source"] = recorder_meta.get("final_source") or "local"
            return stored["samples"], stored["sr"]

        if event.audio_path is None or not Path(event.audio_path).exists():
            raise VoiceSessionError("No local audio file available for event")

        audio, sr = sf.read(str(event.audio_path), dtype="float32")
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        return audio, int(sr)

    def _build_result(self, include_feature_arrays: bool = False) -> Dict[str, Any]:
        events = self._event_results
        if not include_feature_arrays:
            events = [self._compact_event_result(event) for event in self._event_results]

        summary = self._aggregate_summary()
        for event in events:
            error_code = event.get("error_code")
            if error_code:
                summary["error_code"] = error_code
                break

        return {
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "started_at": self.start_timestamp,
            "finished_at": self.finish_timestamp,
            "events": events,
            "summary": summary,
        }

    def _compact_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        compact = dict(result)
        compact["events"] = [
            self._compact_event_result(event)
            for event in result.get("events", [])
        ]
        return compact

    def _compact_event_result(self, event: Dict[str, Any]) -> Dict[str, Any]:
        compact = {}
        for key, value in event.items():
            if isinstance(value, (list, np.ndarray)):
                continue
            compact[key] = value
        return compact

    def _feature_array_dataframe(self, event: Dict[str, Any], feature_name: str):
        pandas = _get_pandas()
        if pandas is None:
            raise VoiceSessionError("Pandas is required for voice feature workbook export")

        values = event.get(feature_name, [])
        array = np.asarray(values)

        if array.ndim == 0:
            array = array.reshape(1)

        if array.ndim == 1:
            df = pandas.DataFrame({feature_name: array})
        else:
            flat = array.reshape(array.shape[0], -1)
            df = pandas.DataFrame(
                flat,
                columns=[f"{feature_name}_{idx}" for idx in range(flat.shape[1])],
            )

        df.insert(0, "frame", range(len(df)))
        df.insert(0, "event_id", event.get("event_id"))
        df.insert(1, "audio_path", event.get("audio_path"))
        return df

    def _save_feature_workbook(self, result: Dict[str, Any], subject: str) -> None:
        pandas = _get_pandas()
        if pandas is None:
            return

        workbook_path = self.recording_root / f"voice_features_{subject}_{self.session_id}.xlsx"
        sheets = [("summary", pandas.DataFrame([result["summary"]]))]

        event_status_df = pandas.DataFrame(
            [
                {
                    "event_id": event.get("event_id"),
                    "prompt_text": event.get("prompt_text"),
                    "prompt_type": event.get("prompt_type"),
                    "event_type": event.get("event_type"),
                    "status": event.get("status"),
                    "error": event.get("error"),
                    "audio_path": event.get("audio_path"),
                }
                for event in result["events"]
            ]
        )
        sheets.append(("event_status", event_status_df))

        for feature_name in self.FEATURE_ARRAY_KEYS:
            frames = [
                self._feature_array_dataframe(event, feature_name)
                for event in result["events"]
                if feature_name in event
            ]
            if frames:
                feature_df = pandas.concat(frames, ignore_index=True)
            else:
                feature_df = pandas.DataFrame(columns=["event_id", "audio_path", "frame"])

            sheets.append((feature_name[:31], feature_df))

        self._write_xlsx(workbook_path, sheets)

    def _write_xlsx(self, path: Path, sheets) -> None:
        sheet_xml = []
        for _, df in sheets:
            sheet_xml.append(self._worksheet_xml(df))

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types_xml(len(sheets)))
            zf.writestr("_rels/.rels", self._root_rels_xml())
            zf.writestr("xl/workbook.xml", self._workbook_xml([name for name, _ in sheets]))
            zf.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels_xml(len(sheets)))
            zf.writestr("xl/styles.xml", self._styles_xml())
            for index, xml in enumerate(sheet_xml, start=1):
                zf.writestr(f"xl/worksheets/sheet{index}.xml", xml)

    def _content_types_xml(self, sheet_count: int) -> str:
        overrides = [
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        ]
        for index in range(1, sheet_count + 1):
            overrides.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            + "".join(overrides)
            + "</Types>"
        )

    def _root_rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

    def _workbook_xml(self, sheet_names) -> str:
        sheets_xml = []
        for index, name in enumerate(sheet_names, start=1):
            safe_name = escape(str(name).replace(":", "_").replace("/", "_").replace("\\", "_")[:31])
            sheets_xml.append(
                f'<sheet name="{safe_name}" sheetId="{index}" r:id="rId{index}"/>'
            )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/workbookml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(sheets_xml)
            + "</sheets></workbook>"
        )

    def _workbook_rels_xml(self, sheet_count: int) -> str:
        rels = []
        for index in range(1, sheet_count + 1):
            rels.append(
                f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            )
        rels.append(
            f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(rels)
            + "</Relationships>"
        )

    def _styles_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/workbookml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            "</styleSheet>"
        )

    def _worksheet_xml(self, df) -> str:
        pandas = _get_pandas()
        if pandas is None:
            return ""

        rows_xml = []
        rows = [list(df.columns)] + df.astype(object).where(pandas.notnull(df), None).values.tolist()

        for row_index, row in enumerate(rows, start=1):
            cells = []
            for col_index, value in enumerate(row, start=1):
                cells.append(self._cell_xml(row_index, col_index, value))
            rows_xml.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/workbookml/2006/main">'
            "<sheetData>"
            + "".join(rows_xml)
            + "</sheetData></worksheet>"
        )

    def _cell_xml(self, row_index: int, col_index: int, value) -> str:
        cell_ref = f"{self._column_name(col_index)}{row_index}"

        if value is None:
            return f'<c r="{cell_ref}"/>'

        if isinstance(value, (np.integer, int)):
            return f'<c r="{cell_ref}"><v>{int(value)}</v></c>'

        if isinstance(value, (np.floating, float)):
            value = float(value)
            if not np.isfinite(value):
                return f'<c r="{cell_ref}"/>'
            return f'<c r="{cell_ref}"><v>{value}</v></c>'

        text = escape(str(value))
        return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    def _column_name(self, col_index: int) -> str:
        name = ""
        while col_index:
            col_index, remainder = divmod(col_index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def _save_results_to_file_async(self, result: Dict[str, Any]) -> None:
        def save_after_ui_release() -> None:
            time.sleep(1.0)
            self._save_results_to_file(result)

        thread = threading.Thread(
            target=save_after_ui_release,
            name=f"voice-report-save-{self.session_id}",
            daemon=True,
        )
        thread.start()

    def _save_results_to_file(self, result: Dict[str, Any]) -> None:
        pandas = _get_pandas()
        if pandas is None:
            return

        try:
            subject = self.subject_id if self.subject_id else "unknown"
            self._save_feature_workbook(result, subject)
            print(f"Voice reports saved to: {self.recording_root}")
        except Exception as e:
            print(f"Error saving voice report to {self.recording_root}: {e}")

    def _aggregate_summary(self) -> Dict[str, Any]:
        if not self._event_results:
            return {
                "dLPC": 0.0,
                "PARCOR": 0.0,
                "LPC": 0.0,
                "Pitch": 0.0,
                "MFCC": 0.0,
            }

        dLPC_list = []
        parcor_list = []
        lpc_formants_list = []
        pitch_list = []
        mfcc_list = []

        sampling_rate = 16000

        for event in self._event_results:
            try:
                if not event.get("mfcc") or not event.get("lpc"):
                    continue
                    
                mfcc_array = np.asarray(event["mfcc"], dtype=np.float32)
                if mfcc_array.ndim == 2 and mfcc_array.shape[1] > 1:
                    coef_1 = mfcc_array[:, 1]
                    rms_mfcc = np.sqrt(np.nanmean(coef_1 ** 2))
                    mfcc_list.append(rms_mfcc)

                lpc_array = np.asarray(event["lpc"], dtype=np.float32)
                if lpc_array.size > 0 and lpc_array.ndim == 2:
                    frame_formants = []
                    for frame_lpc in lpc_array:
                        if np.all(frame_lpc == 0):
                            continue
                        roots = np.roots(frame_lpc)
                        roots = [r for r in roots if np.imag(r) >= 0]
                        angles = np.angle(roots)
                        freqs = sorted(angles * (sampling_rate / (2 * np.pi)))
                        
                        valid_freqs = [f for f in freqs if 250 < f < 4000]
                        if valid_freqs:
                            frame_formants.append(valid_freqs[0])
                    
                    if frame_formants:
                        lpc_formants_list.append(np.nanmean(frame_formants))

                parcor_array = np.asarray(event["parcor"], dtype=np.float32)
                if parcor_array.size > 0 and parcor_array.ndim == 2:
                    rms_parcor = np.sqrt(np.nanmean(parcor_array[:, 0:3] ** 2))
                    parcor_list.append(rms_parcor)

                dlpc_arr = np.asarray(event["delta_lpc"], dtype=np.float32)
                if dlpc_arr.size > 0:
                    dLPC_list.append(np.sqrt(np.nanmean(dlpc_arr ** 2)))

                pitch_array = np.asarray(event["pitch"], dtype=np.float32)
                voiced = pitch_array[~np.isnan(pitch_array)]
                if voiced.size > 0:
                    pitch_list.append(np.nanmean(voiced))

            except Exception:
                continue

        def _safe_mean(vals):
            if not vals: 
                return 0.0
            m = np.nanmean(vals)
            return float(m) if np.isfinite(m) else 0.0

        return {
            "dLPC": _safe_mean(dLPC_list),
            "PARCOR": _safe_mean(parcor_list),
            "LPC": _safe_mean(lpc_formants_list),
            "Pitch": _safe_mean(pitch_list),
            "MFCC": _safe_mean(mfcc_list),
        }
