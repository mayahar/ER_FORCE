import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
try:
    import pandas as pd
except ImportError:
    pd = None

from .events import VoiceEvent
from .recorder import VoiceRecorder, VoiceRecordingError
from .processing import VoiceFeatureExtractor, VoiceFeatureExtractionError
from .tts import speak_text


class VoiceSessionError(Exception):
    pass


class VoiceSessionManager:
    DEFAULT_RECORDING_ROOT = Path("temp_voice_recordings")
    DEFAULT_REPORTS_ROOT = Path("voice_reports")

    # קובץ ה־WAV של הצליל "אאאאא"
    PROMPT_AUDIO_FILE = Path(__file__).parent / "Ahhhh.wav"

    def __init__(
        self,
        subject_id: Optional[str] = None,
        session_id: Optional[str] = None,
        events: Optional[List[VoiceEvent]] = None,
        recording_root: Optional[Path] = None,
        speak_prompts: bool = True,
    ):
        self.subject_id = str(subject_id) if subject_id is not None else None
        self.session_id = str(session_id or int(time.time()))
        self.recorder = VoiceRecorder()
        self.speak_prompts = bool(speak_prompts)
        self.start_timestamp: Optional[float] = None
        self.finish_timestamp: Optional[float] = None
        self.events = events if events is not None else self._default_events()

        self.recording_root = Path(recording_root or self.DEFAULT_RECORDING_ROOT) / self.session_id
        self.recording_root.mkdir(parents=True, exist_ok=True)

        # Pre-load prompt audio to ensure immediate transition after TTS
        self._prompt_audio_cache = None
        self._prompt_sr_cache = None
        self._preload_prompt_audio()

        self._executor = ThreadPoolExecutor(max_workers=1)
        self._active_future: Optional[Future] = None
        self._active_event_id: Optional[str] = None
        self._finalized = False
        self._event_results: List[Dict[str, Any]] = []

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
        self._active_future = self._executor.submit(self._record_event, event)

    def _play_prompt_audio(self) -> None:
        # Use cached audio for immediate response if available
        if self._prompt_audio_cache is not None:
            sd.play(self._prompt_audio_cache, self._prompt_sr_cache)
            sd.wait()
            return

        if not self.PROMPT_AUDIO_FILE.exists():
            raise FileNotFoundError(
                f"Prompt audio file not found: {self.PROMPT_AUDIO_FILE}"
            )

        audio, sr = sf.read(str(self.PROMPT_AUDIO_FILE), dtype="float32")

        # המרה למונו אם צריך
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        sd.play(audio, sr)
        sd.wait()

    def _record_event(self, event: VoiceEvent) -> None:
        try:
            if self.speak_prompts:
                try:
                    # TTS instruction
                    speak_text("Please imitate the following sound for 10 seconds")

                    # השמעת קובץ ה־WAV
                    self._play_prompt_audio()

                except Exception as exc:
                    event.metadata["tts_error"] = str(exc)

            # התחלת ההקלטה
            audio, sample_rate = self.recorder.record(event.duration)

            event.metadata["audio"] = {
                "samples": audio,
                "sr": sample_rate,
            }

            event.audio_path = self.recording_root / f"{event.event_id}.wav"

            self.recorder.save(audio, sample_rate, event.audio_path)

            event.status = "completed"
            if self.speak_prompts:
                # Announce the end of recording
                speak_text("Recording completed. Thank you!")

        except VoiceRecordingError as exc:
            event.error = str(exc)
            event.status = "failed"

        except Exception as exc:
            event.error = f"Unexpected recording failure: {exc}"
            event.status = "failed"

    def finalize_session(self) -> Dict[str, Any]:
        if self._finalized:
            return self._build_result()

        if self._active_future is not None:
            try:
                self._active_future.result(timeout=10.0)
            except Exception:
                pass

        self.finish_timestamp = time.time()
        self._event_results = []

        for event in self.completed_events:
            try:
                audio, sample_rate = self._load_audio(event)

                features = VoiceFeatureExtractor.extract_features(
                    audio,
                    sample_rate,
                )

                self._event_results.append(
                    {
                        "event_id": event.event_id,
                        "prompt_text": event.prompt_text,
                        "prompt_type": event.prompt_type,
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "duration": event.duration,
                        "audio_path": (
                            str(event.audio_path)
                            if event.audio_path else None
                        ),
                        "error": event.error,
                        "mfcc": features["mfcc"].tolist(),
                        "pitch": features["pitch"].tolist(),
                        "lpc": features["lpc"].tolist(),
                        "parcor": features["parcor"].tolist(),
                        "delta_lpc": features["delta_lpc"].tolist(),
                    }
                )

            except (VoiceFeatureExtractionError, Exception) as exc:
                event.error = str(exc)
                event.status = "failed"

        self._finalized = True

        result = self._build_result()
        self._save_results_to_file(result)
        return result

    def _load_audio(self, event: VoiceEvent):
        stored = event.metadata.get("audio")

        if stored is not None:
            return stored["samples"], stored["sr"]

        if event.audio_path is None:
            raise VoiceSessionError("No audio available for event")

        audio, sr = sf.read(str(event.audio_path), dtype="float32")

        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)

        return audio, int(sr)

    def _build_result(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "subject_id": self.subject_id,
            "started_at": self.start_timestamp,
            "finished_at": self.finish_timestamp,
            "events": self._event_results,
            "summary": self._aggregate_summary(),
        }

    def _save_results_to_file(self, result: Dict[str, Any]) -> None:
        """
        Saves the session metrics to an Excel file with multiple sheets.
        Note: Since CSV files do not support multiple sheets, we use .xlsx format.
        """
        if pd is None:
            # Pandas is required for multi-sheet export
            return

        try:
            self.DEFAULT_REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
            
            # Generate filename: {subject_id}_{YYYY-MM-DD}.xlsx
            ts = self.start_timestamp or time.time()
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            subject = self.subject_id if self.subject_id else "unknown"
            filename = f"{subject}_{date_str}.xlsx"
            report_path = self.DEFAULT_REPORTS_ROOT / filename

            summary_df = pd.DataFrame([result["summary"]])
            
            # Filter event results to include only scalar values (exclude raw audio/feature arrays)
            report_events = []
            for event in result["events"]:
                clean_event = {k: v for k, v in event.items() if not isinstance(v, (list, np.ndarray))}
                report_events.append(clean_event)
            events_df = pd.DataFrame(report_events)

            # Write to Excel with multiple sheets
            with pd.ExcelWriter(report_path, engine='openpyxl') as writer:
                summary_df.to_excel(writer, sheet_name='Session Summary', index=False)
                events_df.to_excel(writer, sheet_name='Event Details', index=False)
        except Exception:
            # Fallback for logging or silent failure during session finalization
            pass

    def _aggregate_summary(self) -> Dict[str, Any]:
        if not self._event_results:
            return {
                "dLPC": 0.0,
                "PARCOR": 0.0,
                "LPC": 0.0,
                "Pitch": 0.0,
                "MFCC": 0.0,
            }

        dLPC = []
        parcor = []
        lpc = []
        pitch_means = []
        pitch_jitters = [] # מדד נוסף לעייפות
        mfcc_focus = [] # נתמקד במקדם MFCC 1 ו-2

        for event in self._event_results:
            try:
                # שימוש ב-MFCC: במקום ממוצע של הכל, ניקח את MFCC 1 (מייצג גוון קול)
                # אנחנו לא עושים Absolute Value כדי לא לאבד את הכיווניות של האנרגיה
                mfcc_array = np.asarray(event["mfcc"], dtype=np.float32)
                if mfcc_array.ndim == 2 and mfcc_array.shape[1] > 1:
                    # ממוצע של מקדם 1 (השני בסדרה) - נחשב למדד יציבות ספקטרלית
                    mfcc_focus.append(np.nanmean(mfcc_array[:, 1])) 
                
                # LPC ו-PARCOR: במקום ממוצע ערך מוחלט, נחשב ממוצע פשוט של המקדמים הראשונים
                lpc_array = np.asarray(event["lpc"], dtype=np.float32)
                parcor_array = np.asarray(event["parcor"], dtype=np.float32)
                
                if lpc_array.size > 0:
                    lpc.append(np.nanmean(lpc_array[:, 1:4])) # מקדמי המבנה העיקריים
                if parcor_array.size > 0:
                    parcor.append(np.nanmean(parcor_array[:, 0:3]))

                # deltaLPC: נשאר עם ממוצע ערך מוחלט כי הוא מייצג "שינוי" (יציבות)
                dlpc_arr = np.abs(np.asarray(event["delta_lpc"], dtype=np.float32))
                if dlpc_arr.size > 0:
                    dLPC.append(np.nanmean(dlpc_arr))

                # Pitch ו-Jitter
                pitch_array = np.asarray(event["pitch"], dtype=np.float32)
                voiced = pitch_array[~np.isnan(pitch_array)]
                if voiced.size > 1:
                    pitch_means.append(np.nanmean(voiced))
                    # חישוב Jitter בסיסי: ממוצע ההפרשים בין פריימים עוקבים
                    jitter = np.nanmean(np.abs(np.diff(voiced)))
                    pitch_jitters.append(jitter)

            except Exception:
                continue

        def _safe_mean(vals):
            if not vals: return 0.0
            m = np.nanmean(vals)
            return float(m) if np.isfinite(m) else 0.0

        # החזרת התוצאות באותו פורמט בדיוק
        return {
            "dLPC": _safe_mean(dLPC),
            "PARCOR": _safe_mean(parcor),
            "LPC": _safe_mean(lpc),
            "Pitch": _safe_mean(pitch_means), # ממוצע תדר יסודי
            "MFCC": _safe_mean(mfcc_focus),   # ממוצע המקדם ה-1 (Spectral Slope)
        }