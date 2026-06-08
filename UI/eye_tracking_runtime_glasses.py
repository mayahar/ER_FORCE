"""Eye tracking session helpers for Tobii Pro Glasses 3 via REST API."""

from __future__ import annotations

import json
import os
import time
import gzip
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
import requests
from requests.adapters import HTTPAdapter

import numpy as np

# שומרים על אותם מייבאים של האנלייזר הקיים שלך
from eye_tracking_analysis.eye_movement_analyzer import EyeMovementAnalyzer
from core.hardware_config import glasses_host
from score.eye_features import apply_controller_eye_features

SKIP_EYE_CALIBRATION = False
VERBOSE_TOBII_STATUS = os.environ.get("TOBII_VERBOSE_STATUS", "").lower() in ("1", "true", "yes")
# הגדרה קשיחה של ה-IP הסטטי האלחוטי של Tobii Glasses 3
# החליפי את ההגדרות בראש הקובץ eye_tracking_runtime.py (סביב שורות 20-50):

# החליפי חזרה את ההגדרות בראש הקובץ eye_tracking_runtime.py למצבן הבטוח:

GLASSES_ENV_HOST = os.environ.get("TOBII_GLASSES_HOST")
GLASSES_FALLBACK_HOSTS = (
    "TG03B-080203015551.local",
    "TG03B-080203015551",
)
_LAST_WORKING_HOST = None

def _unique_hosts() -> list[str]:
    hosts = []
    for host in (_LAST_WORKING_HOST, glasses_host(), GLASSES_ENV_HOST, *GLASSES_FALLBACK_HOSTS):
        if host and host not in hosts:
            hosts.append(host)
    return hosts

def _candidate_hosts(preferred_host: str | None = None) -> list[str]:
    hosts = []
    for host in (preferred_host, *_unique_hosts()):
        if host and host not in hosts:
            hosts.append(host)
        if host and host.startswith("TG03B-") and "." not in host:
            local_host = f"{host}.local"
            if local_host not in hosts:
                hosts.append(local_host)
    return hosts

    def ensure_tracker(self) -> bool:
        """בודק האם המשקפיים זמינים ברשת ומאפשר המתנה סבלנית לייצוב החיבור הקווי"""
        self._log("בודק זמינות Tobii Glasses ברשת")
        response = None
        host = ""
        error = None
        max_attempts = 8
        for attempt in range(1, max_attempts + 1):
            response, host, error = _request(
                "GET",
                "/rest/system.recording-unit-serial",
                timeout=2.0,
            )
            if response is not None and response.status_code == 200:
                self.tracker_connected = True
                self.active_host = host
                self.last_error = ""
                self._log(f"המשקפיים נמצאו דרך host={host}, ניסיון {attempt}/{max_attempts}")
                return True
            self._log(f"בדיקת זמינות ניסיון {attempt}/{max_attempts} נכשלה: {error}")
            time.sleep(0.8)

        self.tracker_connected = False
        detail = f" ({error})" if error else ""
        self.last_error = (
            "לא נמצאו משקפי Tobii ברשת. ודא חיבור ל-Wi-Fi של המשקפיים "
            f"{detail}"
        )
        self._log(self.last_error)
        return False


def _request(
    method: str,
    path: str,
    *,
    json_body=None,
    timeout: float = 3.0,
    preferred_host: str | None = None,
):
    global _LAST_WORKING_HOST
    last_error = None
    errors = []
    for host in _candidate_hosts(preferred_host):
        url = f"http://{host}{path}"
        try:
            response = requests.request(method, url, json=json_body, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            errors.append(f"{host}: {exc}")
            continue
        if response.status_code != 404:
            _LAST_WORKING_HOST = host
            return response, host, None
        last_error = requests.HTTPError(f"HTTP 404 for {url}", response=response)
        errors.append(f"{host}: HTTP 404")
    if errors:
        last_error = RuntimeError("; ".join(errors))
    return None, "", last_error

class EyeTrackingRuntime:
    def __init__(self):
        self.analyzer: EyeMovementAnalyzer | None = None
        self.active = False
        self.last_error = ""
        self.export_paths: dict[str, str] | None = None
        self.raw_sample_count = 0
        self.tracker_connected = False
        self.tracker_label = "Tobii Pro Glasses 3"
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_attempted = False
        self.calibration_preview_path = None
        self.calibration_summary: dict[str, Any] | None = None
        
        # משתנה לשמירת מזהה ההקלטה הנוכחית מהמשקפיים
        self.current_recording_uuid = None
        self.active_host = None
        self.session_eye_dir: Path | None = None
        self.session_log_path: Path | None = None
        self._pending_raw_gaze: tuple[Path, str] | None = None
        self.recording_started_at: float | None = None

    def configure_session(self, controller: Any | None = None) -> None:
        session = getattr(controller, "session", None)
        eye_dir = getattr(session, "eye_dir", None)
        self.session_eye_dir = None
        self.session_log_path = None
        if eye_dir:
            self.session_eye_dir = Path(eye_dir)
            self.session_eye_dir.mkdir(parents=True, exist_ok=True)
            self.session_log_path = self.session_eye_dir / "tobii_runtime.log"

    def _log(self, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"[{timestamp}] {message}"
        print(line)
        if self.session_log_path is None:
            return
        try:
            log_path = self.session_log_path
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
        except Exception:
            pass

    def ensure_tracker(self) -> bool:
        """בודק האם המשקפיים זמינים ברשת"""
        self._log("בודק זמינות Tobii Glasses ברשת")
        response = None
        host = ""
        error = None
        max_attempts = 8
        for attempt in range(1, max_attempts + 1):
            response, host, error = _request(
                "GET",
                "/rest/system.recording-unit-serial",
                timeout=2.0,
            )
            if response is not None and response.status_code == 200:
                self.tracker_connected = True
                self.active_host = host
                self.last_error = ""
                self._log(f"המשקפיים נמצאו דרך host={host}, ניסיון {attempt}/{max_attempts}")
                return True
            self._log(f"בדיקת זמינות ניסיון {attempt}/{max_attempts} נכשלה: {error}")
            time.sleep(0.8)

        self.tracker_connected = False
        detail = f" ({error})" if error else ""
        self.last_error = (
            "לא נמצאו משקפי Tobii ברשת. ודא חיבור ל-Wi-Fi של המשקפיים "
            "או הגדר TOBII_GLASSES_HOST לכתובת ה-IP שלהם."
            f"{detail}"
        )
        self._log(self.last_error)
        return False

    def start(self, camera_index: int = 0, subject_id: str | None = None) -> tuple[bool, str]:
        """מפעיל את ההקלטה במשקפיים באופן אלחוטי בתחילת המשחק"""
        if self.session_eye_dir is None:
            self.last_error = "Cannot start eye recording before configuring a session eye directory."
            self._log(self.last_error)
            return False, self.last_error
        if not self.ensure_tracker():
            return False, self.last_error

        try:
            self._log("Starting Tobii recording")
            if self.active_host and VERBOSE_TOBII_STATUS:
                self._log_device_status(self.active_host)
                self._stop_or_cancel_existing_recording(self.active_host)

            last_detail = ""
            max_start_attempts = 10
            for attempt in range(1, max_start_attempts + 1):
                res, host, error = self._post_recorder_start()
                if res is None:
                    last_detail = f"communication error: {error}"
                    self._log(f"recorder!start attempt {attempt}/{max_start_attempts} failed: {last_detail}")
                    time.sleep(0.5)
                    continue

                start_value = self._response_value(res)
                action_error = res.headers.get("X-g3-action-error", "")
                last_detail = (
                    f"HTTP {res.status_code}, body={start_value!r}, host={host}, "
                    f"X-g3-action-error={action_error!r}"
                )
                self._log(f"recorder!start attempt {attempt}/{max_start_attempts} returned {last_detail}")

                if action_error:
                    friendly_error = self._friendly_action_error(action_error)
                    self._log(f"recorder!start action error: {friendly_error}")
                    if action_error == "resource;/system/battery":
                        self.active = False
                        self.current_recording_uuid = None
                        self.last_error = friendly_error
                        self._log(self.last_error)
                        return False, self.last_error

                if res.status_code != 200:
                    time.sleep(0.5)
                    continue

                self.active_host = host
                time.sleep(0.3)
                recording_uuid, uuid_host, uuid_detail = self._read_current_recording_uuid()
                self._log(f"recorder.uuid after attempt {attempt}/{max_start_attempts}: {uuid_detail}")

                if self._looks_like_uuid(recording_uuid):
                    self.current_recording_uuid = recording_uuid
                    self.active_host = uuid_host or self.active_host
                    self.active = True
                    self.recording_started_at = time.time()
                    self.last_error = ""
                    self._log(
                        f"Tobii recording started: uuid={self.current_recording_uuid}, host={self.active_host}"
                    )
                    return True, ""

                fallback_uuid = self._extract_uuid_from_start_response(res)
                if self._looks_like_uuid(fallback_uuid):
                    self.current_recording_uuid = fallback_uuid
                    self.active = True
                    self.recording_started_at = time.time()
                    self.last_error = ""
                    self._log(
                        f"Tobii recording started from start response: uuid={self.current_recording_uuid}, host={self.active_host}"
                    )
                    return True, ""

                if start_value.lower() == "false":
                    if VERBOSE_TOBII_STATUS:
                        self._log_device_status(host or self.active_host)
                    self._log("recorder!start returned false; waiting before retry")
                time.sleep(0.5)

            self.active = False
            self.recording_started_at = None
            self.current_recording_uuid = None
            self.last_error = (
                "Tobii recording did not start. recorder!start kept returning no active UUID. "
                f"Last detail: {last_detail}"
            )
            self._log(self.last_error)
            return False, self.last_error
        except Exception as e:
            self.active = False
            self.last_error = f"נכשלה הפעלת הקלטה: {str(e)}"
            self._log(self.last_error)
            return False, self.last_error

    def stop(self, controller: Any | None = None) -> tuple[dict[str, Any] | None, str]:
        """עוצר את ההקלטה, מושך את ה-RAW Data מיידית דרך הרשת ומנתח עייפות"""
        if controller is not None:
            self.configure_session(controller)
        if not self.active:
            self.last_error = "אין הקלטה פעילה לעצירה"
            self._log(self.last_error)
            return None, self.last_error

        try:
            self._log(
                f"עוצר הקלטת Tobii: uuid={self.current_recording_uuid}, host={self.active_host}"
            )
            # 1. עצירת ההקלטה במשקפיים
            recording_uuid = self.current_recording_uuid
            active_host = self.active_host

            res, stop_host, err = self._post_recorder_stop(active_host)
            self.active = False
            if res is None:
                if self._looks_like_uuid(recording_uuid):
                    self._log(
                        "recorder!stop timed out, but UUID exists; continuing to fetch recording. "
                        f"stop error: {err}"
                    )
                else:
                    self.last_error = f"נכשלה עצירת ההקלטה מול המשקפיים: {err}"
                    self._log(self.last_error)
                    return None, self.last_error
            if stop_host:
                active_host = stop_host
            
            if not active_host:
                active_host = "192.168.75.51"
            
            # השהייה קלה של שנייה כדי לאפשר למשקפיים לסגור את הקובץ פיזית בדיסק שלהם
            time.sleep(0.5)
            
            if not self._looks_like_uuid(recording_uuid):
                self.last_error = f"אין UUID תקין להקלטה שהסתיימה: {recording_uuid!r}"
                self._log(self.last_error)
                return None, self.last_error

            gaze_text, fetch_error = self._fetch_recording_gaze_text(active_host, recording_uuid)
            if fetch_error:
                self.last_error = fetch_error
                self._log(self.last_error)
                return None, fetch_error

            # 3. פארסינג של ה-RAW Data לתוך מערכים
            timestamps = []
            gaze_left_x, gaze_left_y = [], []
            gaze_right_x, gaze_right_y = [], []
            pupil_left, pupil_right = [], []

            for line in gaze_text.splitlines():
                if not line.strip():
                    continue
                try:
                    packet = json.loads(line)
                except Exception:
                    continue
                
                if packet.get("type") == "gaze" and "data" in packet:
                    data = packet["data"]
                    timestamps.append(float(packet["timestamp"]))
                    
                    g2d = data.get("gaze2d", [np.nan, np.nan])
                    gaze_left_x.append(g2d[0])
                    gaze_left_y.append(g2d[1])
                    gaze_right_x.append(g2d[0])
                    gaze_right_y.append(g2d[1])
                    
                    pupil_left.append(data.get("eyeleft", {}).get("pupildiameter", np.nan))
                    pupil_right.append(data.get("eyeright", {}).get("pupildiameter", np.nan))

            self.raw_sample_count = len(timestamps)
            if self.raw_sample_count == 0:
                self.last_error = "לא נאספו דגימות תנועות עיניים במהלך המשחק"
                self._log(self.last_error)
                return {}, self.last_error

            # 4. התאמת המבנה לפורמט של ה-EyeMovementAnalyzer
            mock_session_data = {
                "timestamp": np.array(timestamps),
                "left_gaze_point_on_display_area_x": np.array(gaze_left_x),
                "left_gaze_point_on_display_area_y": np.array(gaze_left_y),
                "right_gaze_point_on_display_area_x": np.array(gaze_right_x),
                "right_gaze_point_on_display_area_y": np.array(gaze_right_y),
                "left_pupil_diameter": np.array(pupil_left),
                "right_pupil_diameter": np.array(pupil_right),
            }

            mock_session_data["timestamp"] = mock_session_data["timestamp"] - mock_session_data["timestamp"][0]

            # 5. הרצת האנליזה
            features, err = self._analyze_extracted_data(mock_session_data)
            
            if err:
                self.last_error = err
                self._log(self.last_error)
                return None, err

            if features is not None:
                features = dict(features)
                features["calibration"] = self._calibration_metadata()

            if controller is not None:
                apply_controller_eye_features(controller, features)

            self._save_features(recording_uuid, features)
            self._defer_raw_gaze_text(recording_uuid, gaze_text)
            self.save_pending_raw_gaze_async()
            self.last_error = ""
            self._log(
                f"עיבוד Tobii הסתיים בהצלחה: samples={self.raw_sample_count}, uuid={recording_uuid}"
            )
            return features, ""

        except Exception as e:
            self.last_error = f"שגיאה בעיבוד נתוני המשקפיים בסיום המשחק: {str(e)}"
            self._log(self.last_error)
            return None, self.last_error
        
    def _analyze_extracted_data(self, session_data: dict[str, np.ndarray]) -> tuple[dict[str, Any] | None, str]:
        """מריץ את ה-Pipeline הקיים של האנלייזר שלך (העתק מדויק מהקוד המקורי)"""
        try:
            gaze_x = np.nanmean(
                np.vstack(
                    [
                        session_data["left_gaze_point_on_display_area_x"],
                        session_data["right_gaze_point_on_display_area_x"],
                    ]
                ),
                axis=0,
            )
            gaze_y = np.nanmean(
                np.vstack(
                    [
                        session_data["left_gaze_point_on_display_area_y"],
                        session_data["right_gaze_point_on_display_area_y"],
                    ]
                ),
                axis=0,
            )
            timestamps = session_data["timestamp"]
            self.analyzer = EyeMovementAnalyzer()
            metrics = self.analyzer.analyze_gaze_data(gaze_x, gaze_y, timestamps)
        except Exception as e:
            return None, f"אנליזת תנועות עיניים נכשלה: {str(e)}"

        total_duration = float(timestamps[-1] - timestamps[0]) if timestamps.size > 1 else 0.0

        features = {
            "fixation_duration": float(metrics.fixation_duration),
            "fixation_count": float(metrics.fixation_count),
            "saccade_count": float(metrics.saccade_count),
            "analysis": {
                "total_duration": total_duration,
                "fixations_per_minute": float(metrics.fixation_count),
                "saccades_per_minute": float(metrics.saccade_count),
                "fixation_duration_per_minute": float(metrics.fixation_duration),
                "mean_fixation_duration": 0.0,
                "mean_saccade_velocity": 0.0,
            },
        }
        return features, ""

    @staticmethod
    def _response_value(response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text.strip().strip('"')
        if isinstance(data, dict):
            return str(data.get("uuid") or data.get("id") or data.get("value") or "")
        return str(data).strip().strip('"')

    def _extract_uuid_from_start_response(self, response) -> str:
        value = self._response_value(response)
        if self._looks_like_uuid(value):
            return value
        return ""

    def _post_recorder_start(self):
        last_error = None
        preferred_hosts = _candidate_hosts(self.active_host)
        for host in preferred_hosts:
            try:
                response = requests.post(
                    f"http://{host}/rest/recorder!start",
                    json=[],
                    timeout=(1.0, 5.0),
                )
            except requests.RequestException as exc:
                last_error = exc
                self._log(f"recorder!start host {host} failed: {exc}")
                continue

            if response.status_code != 404:
                self.active_host = host
                return response, host, None

            last_error = requests.HTTPError(
                f"HTTP 404 for http://{host}/rest/recorder!start",
                response=response,
            )

        return None, "", last_error

    def _post_recorder_stop(self, preferred_host: str | None):
        last_error = None
        for host in _candidate_hosts(preferred_host):
            try:
                response = requests.post(
                    f"http://{host}/rest/recorder!stop",
                    json=[],
                    timeout=(2.0, 4.0),
                )
            except requests.RequestException as exc:
                last_error = exc
                self._log(f"recorder!stop host {host} did not confirm quickly: {exc}")
                continue

            if response.status_code != 404:
                self.active_host = host
                return response, host, None

            last_error = requests.HTTPError(
                f"HTTP 404 for http://{host}/rest/recorder!stop",
                response=response,
            )

        return None, "", last_error

    def _stop_or_cancel_existing_recording(self, host: str) -> None:
        value, _, detail = self._read_current_recording_uuid()
        self._log(f"pre-start recorder.uuid: {detail}")
        if not self._looks_like_uuid(value):
            return

        self._log(f"found existing active recording {value}; stopping it before new start")
        try:
            response = requests.post(f"http://{host}/rest/recorder!stop", json=[], timeout=5.0)
            self._log(
                "pre-start recorder!stop returned "
                f"HTTP {response.status_code}, body={self._response_value(response)!r}, "
                f"X-g3-action-error={response.headers.get('X-g3-action-error', '')!r}"
            )
            time.sleep(1.0)
        except requests.RequestException as exc:
            self._log(f"pre-start recorder!stop failed: {exc}")

    def _log_device_status(self, host: str | None) -> None:
        if not host:
            return
        status_paths = (
            "/rest/recorder.uuid",
            "/rest/system.battery-level",
            "/rest/system.head-unit-battery-level",
            "/rest/system.recording-unit-battery-level",
            "/rest/system.sd-card-state",
            "/rest/system.storage-state",
            "/rest/recorder.remaining-time",
        )
        for path in status_paths:
            last_error = ""
            logged = False
            for candidate_host in _candidate_hosts(host):
                try:
                    response = requests.get(f"http://{candidate_host}{path}", timeout=2.0)
                except requests.RequestException as exc:
                    last_error = f"{candidate_host}: {exc}"
                    continue
                if response.status_code == 404:
                    continue
                value = self._response_value(response)
                self._log(
                    f"status {path}: HTTP {response.status_code}, body={value!r}, host={candidate_host}"
                )
                logged = True
                break
            if logged:
                continue
            if last_error:
                self._log(f"status {path}: request failed: {last_error}")

    @staticmethod
    def _friendly_action_error(action_error: str) -> str:
        if action_error == "resource;/system/battery":
            return (
                "Tobii לא התחיל הקלטה כי משאב הסוללה לא זמין או נמוך מדי. "
                "צריך להטעין/לחבר לחשמל את יחידת ההקלטה ואת יחידת הראש, לוודא שהסוללה יושבת טוב, "
                "ואז להתחיל סשן חדש."
            )
        if action_error.startswith("resource;"):
            resource = action_error.split(";", 1)[1]
            return f"Tobii לא התחיל הקלטה בגלל משאב לא זמין: {resource}"
        return f"Tobii לא התחיל הקלטה. שגיאת פעולה: {action_error}"

    def _read_current_recording_uuid(self) -> tuple[str, str, str]:
        last_error = None
        for host in _candidate_hosts(self.active_host):
            try:
                response = requests.get(f"http://{host}/rest/recorder.uuid", timeout=3.0)
            except requests.RequestException as exc:
                last_error = exc
                continue
            if response.status_code == 404:
                last_error = requests.HTTPError(
                    f"HTTP 404 for http://{host}/rest/recorder.uuid",
                    response=response,
                )
                continue
            value = self._response_value(response)
            return value, host, f"HTTP {response.status_code}, body={value!r}, host={host}"
        return "", "", f"request failed: {last_error}"

    @staticmethod
    def _looks_like_uuid(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        parts = value.strip().split("-")
        return len(parts) == 5 and all(parts)

    def _fetch_recording_gaze_text(self, host: str, recording_uuid: str) -> tuple[str, str]:
        self._log(f"מושך http-path להקלטה {recording_uuid}; host מועדף: {host}")
        session = requests.Session()
        session.mount("http://", HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0))
        http_path_res = None
        working_host = ""
        last_error = ""
        for candidate_host in _candidate_hosts(host):
            self._log(f"מנסה http-path מול {candidate_host}")
            try:
                http_path_res = session.get(
                    f"http://{candidate_host}/rest/recordings/{recording_uuid}.http-path",
                    timeout=5.0,
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if http_path_res.status_code == 200:
                working_host = candidate_host
                break
            last_error = f"HTTP {http_path_res.status_code} מול {candidate_host}"

        retry_until = time.time() + 10.0
        while (http_path_res is None or http_path_res.status_code != 200) and time.time() < retry_until:
            time.sleep(0.4)
            for candidate_host in _candidate_hosts(host):
                self._log(f"מנסה http-path מול {candidate_host}")
                try:
                    http_path_res = session.get(
                        f"http://{candidate_host}/rest/recordings/{recording_uuid}.http-path",
                        timeout=(1.0, 1.5),
                    )
                except requests.RequestException as exc:
                    last_error = str(exc)
                    continue
                if http_path_res.status_code == 200:
                    working_host = candidate_host
                    break
                last_error = f"HTTP {http_path_res.status_code} מול {candidate_host}"

        if http_path_res is None or http_path_res.status_code != 200:
            return "", f"נכשלה קבלת http-path להקלטה {recording_uuid}. {last_error}"

        http_path = self._response_value(http_path_res).strip("/")
        self._log(f"http-path להקלטה: {http_path}")
        if http_path.startswith("http://") or http_path.startswith("https://"):
            parsed = urlsplit(http_path)
            working_host = parsed.netloc or working_host
            http_path = parsed.path.strip("/")

        for candidate_host in _candidate_hosts(working_host):
            direct_gaze_url = f"http://{candidate_host}/{http_path}/gazedata.gz?use-content-encoding=true"
            self._log(f"מנסה להוריד gaze data ישירות: {direct_gaze_url}")
            try:
                direct_gaze_res = session.get(direct_gaze_url, timeout=8.0)
            except requests.RequestException as exc:
                last_error = str(exc)
                continue
            if direct_gaze_res.status_code == 200:
                return self._decode_gaze_response(direct_gaze_res), ""
            last_error = f"HTTP {direct_gaze_res.status_code} מול {candidate_host}"

        recording_res = None
        recording_paths = self._recording_metadata_paths(http_path)
        for candidate_host in _candidate_hosts(working_host):
            for recording_path in recording_paths:
                recording_url = f"http://{candidate_host}/{recording_path}"
                self._log(f"מנסה recording.g3: {recording_url}")
                try:
                    recording_res = session.get(recording_url, timeout=8.0)
                except requests.RequestException as exc:
                    last_error = f"{recording_url}: {exc}"
                    continue
                self._log(
                    f"recording.g3 response: HTTP {recording_res.status_code}, url={recording_url}"
                )
                if recording_res.status_code == 200:
                    working_host = candidate_host
                    http_path = recording_path.rsplit("/", 1)[0]
                    break
                last_error = f"HTTP {recording_res.status_code} מול {recording_url}"
            if recording_res is not None and recording_res.status_code == 200:
                break

        if recording_res is None or recording_res.status_code != 200:
            return "", f"נכשלה קבלת recording.g3 להקלטה {recording_uuid}. {last_error}"

        try:
            recording_info = recording_res.json()
        except ValueError as exc:
            return "", f"recording.g3 לא היה JSON תקין: {exc}"

        gaze_file = recording_info.get("gaze", {}).get("file") or "gazedata.gz"

        gaze_res = None
        for candidate_host in _candidate_hosts(working_host):
            gaze_url = f"http://{candidate_host}/{http_path}/{gaze_file}?use-content-encoding=true"
            self._log(f"מנסה להוריד gaze data: {gaze_url}")
            for attempt in range(6):
                try:
                    gaze_res = session.get(gaze_url, timeout=8.0)
                    if gaze_res.status_code == 200:
                        return self._decode_gaze_response(gaze_res), ""
                    last_error = f"HTTP {gaze_res.status_code} מול {candidate_host}"
                    print(f"[*] ניסיון משיכת gazedata {attempt + 1} מצא קוד {gaze_res.status_code}, מנסה שוב...")
                except requests.RequestException as exc:
                    last_error = str(exc)
                    print(f"[*] ניסיון משיכת gazedata {attempt + 1} מול {candidate_host} נכשל: {exc}")
                time.sleep(0.8)

        status_code = gaze_res.status_code if gaze_res is not None else "Unknown"
        return "", f"נכשלה משיכת gazedata מהמשקפיים. קוד שגיאה: {status_code}. {last_error}"

    @staticmethod
    def _recording_metadata_paths(http_path: str) -> list[str]:
        normalized = http_path.strip("/")
        if normalized.endswith(".g3"):
            return [normalized]
        return [f"{normalized}/recording.g3", normalized]

    def _recording_dir(self, recording_uuid: str) -> Path:
        if self.session_eye_dir is None:
            raise RuntimeError("Cannot save eye recording without a configured session eye directory.")
        path = self.session_eye_dir
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _recording_file(self, recording_uuid: str, filename: str) -> Path:
        return self._recording_dir(recording_uuid) / filename

    def _save_raw_gaze_text(self, path: Path, gaze_text: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(gaze_text, encoding="utf-8")
            self.export_paths = dict(self.export_paths or {})
            self.export_paths["raw_gaze"] = str(path)
            self._log(f"נשמר raw gaze: {path}")
        except Exception as exc:
            self._log(f"שמירת raw gaze נכשלה: {exc}")

    def _save_features(self, recording_uuid: str, features: dict[str, Any]) -> None:
        try:
            path = self._recording_file(recording_uuid, "eye_features.json")
            path.write_text(json.dumps(features, ensure_ascii=False, indent=2), encoding="utf-8")
            self.export_paths = dict(self.export_paths or {})
            self.export_paths["features"] = str(path)
            self._log(f"נשמרו eye features: {path}")
        except Exception as exc:
            self._log(f"שמירת eye features נכשלה: {exc}")

    def _calibration_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "attempted": bool(self.calibration_attempted),
            "passed": bool(self.calibration_passed),
            "message": self.calibration_message,
            "tracker": self.tracker_label,
            "preview_path": self.calibration_preview_path,
            "method": "tobii_glasses_rest_single_point",
            "target_points": [{"x": 0.5, "y": 0.5}],
            "accuracy_available": False,
        }
        if self.calibration_summary:
            metadata["result"] = self.calibration_summary
        return metadata

    def _save_raw_gaze_text_async(self, path: Path, gaze_text: str) -> None:
        thread = threading.Thread(
            target=self._save_raw_gaze_text,
            args=(path, gaze_text),
            name=f"tobii-raw-save-{path.parent.name}",
            daemon=True,
        )
        thread.start()

    def _defer_raw_gaze_text(self, recording_uuid: str, gaze_text: str) -> None:
        self._pending_raw_gaze = (
            self._recording_file(recording_uuid, "gazedata.jsonl"),
            gaze_text,
        )

    def save_pending_raw_gaze_async(self) -> None:
        pending = self._pending_raw_gaze
        self._pending_raw_gaze = None
        if pending is None:
            return
        path, gaze_text = pending
        self._save_raw_gaze_text_async(path, gaze_text)

    @staticmethod
    def _decode_gaze_response(response) -> str:
        content = response.content
        if content.lstrip().startswith(b"{"):
            return content.decode(response.encoding or "utf-8", errors="replace")
        try:
            return gzip.decompress(content).decode("utf-8")
        except OSError:
            return content.decode("utf-8", errors="replace")

    @staticmethod
    def _metric_value(metrics, *names, default=0.0) -> float:
        for name in names:
            if hasattr(metrics, name):
                try:
                    value = float(getattr(metrics, name))
                except (TypeError, ValueError):
                    continue
                if np.isfinite(value):
                    return value
        return default

    def reset(self) -> None:
        self.active = False
        self.recording_started_at = None
        self.current_recording_uuid = None
        self.active_host = None
        self.raw_sample_count = 0
        self.last_error = ""

    def reset_calibration(self) -> None:
        self.calibration_passed = False
        self.calibration_message = ""
        self.calibration_attempted = False
        self.calibration_preview_path = None
        self.calibration_summary = None

