"""
Eye Movement Feature Extraction and Analysis - Adaptive & Self-Calibrating Version
Calculates exactly 3 fatigue metrics normalized per minute with robust noise filtering.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
from datetime import datetime
import json


@dataclass
class Fixation:
    """Represents a fixation event"""
    start_time: float
    end_time: float
    duration: float
    x: float
    y: float
    amplitude: Optional[float] = None


@dataclass
class Saccade:
    """Represents a saccade event"""
    start_time: float
    end_time: float
    duration: float
    amplitude: float
    velocity: float
    start_x: float
    start_y: float
    end_x: float
    end_y: float


@dataclass
class EyeMovementMetrics:
    """Aggregated eye movement metrics expected by downstream scripts"""
    fixation_duration: float  # סך זמן הפיקסציות לדקה (בשניות)
    fixation_count: float     # מספר פיקסציות לדקה
    saccade_count: float      # מספר סאקאדות לדקה


class EyeMovementAnalyzer:
    """Analyzes eye tracking data with dynamic threshold tuning to auto-correct recording noise"""
    
    def __init__(self, 
                 sampling_rate: float = 120.0,
                 base_dispersion_threshold: float = 1.2,   # סף בסיס לפיזור (מעלות)
                 base_velocity_threshold: float = 45.0,    # סף בסיס למהירות (מעלות/שנייה)
                 min_fixation_duration: float = 0.1,       # משך פיקסציה מינימלי (בשניות)
                 min_saccade_duration: float = 0.03,       # משך סאקאדה מינימלי (בשניות)
                 fixation_window_size: int = 8,           # חלון דגימות התחלתי לפיקסציה
                 smoothing_window_size: int = 5,          # חלון החלקת ממוצע נע
                 screen_width: int = 1920,
                 screen_height: int = 1080,
                 screen_diagonal_cm: float = 54.0,
                 viewing_distance_cm: float = 60.0):
        
        self.sampling_rate = sampling_rate
        self.min_fixation_duration = min_fixation_duration
        self.min_saccade_duration = min_saccade_duration
        self.fixation_window_size = fixation_window_size
        self.smoothing_window_size = smoothing_window_size
        
        # הגדרות מסך פיזיות
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen_diagonal_cm = screen_diagonal_cm
        self.viewing_distance_cm = viewing_distance_cm
        
        # ספים דינמיים שיעודכנו אוטומטית בכל ריצה בהתאם לאיכות האות
        self.base_dispersion_threshold = base_dispersion_threshold
        self.base_velocity_threshold = base_velocity_threshold
        self.dispersion_threshold = base_dispersion_threshold
        self.velocity_threshold = base_velocity_threshold

    def reset_thresholds(self) -> None:
        self.dispersion_threshold = self.base_dispersion_threshold
        self.velocity_threshold = self.base_velocity_threshold

    def _auto_calibrate_thresholds(self, gaze_x: np.ndarray, gaze_y: np.ndarray):
        """
        עוגן אחיד לכיול עצמי: מזהה את רמת הרעש הסטטי בהקלטה (Noise Floor).
        אם הכיול גרוע או שהיו תנועות ראש, הנתונים יראו שונות מוגברת קבועה.
        הפונקציה מתקנת ומעלה את הספים כדי למנוע זיהויי שווא.
        """
        if len(gaze_x) < 20:
            return
            
        # נחשב את המהירות הרגעית בין דגימות עוקבות בפיקסלים כדי להעריך רעש חיישן
        diff_x = np.diff(gaze_x * self.screen_width)
        diff_y = np.diff(gaze_y * self.screen_height)
        instant_distances = np.sqrt(diff_x**2 + diff_y**2)
        
        # המרה למעלות
        instant_degrees = self._pixel_to_degrees(instant_distances)
        median_noise = np.median(instant_degrees)  # חציון יציב יותר מממוצע מפני קפיצות אמיתיות
        
        # אם רמת הרעש הבסיסית גבוהה מהנורמה (מעל 0.1 מעלות לדגימה)
        # זה מעיד על תאורה לקויה, תנועות ראש או קליברציה גרועה
        if median_noise > 0.1:
            noise_factor = median_noise / 0.1
            # התאמה אדפטיבית של הספים (לא מאפשרים להם לעלות מעבר לפי 2 כדי לשמור על גבולות הגיוניים)
            adjustment = min(noise_factor, 2.0)
            self.dispersion_threshold *= adjustment
            self.velocity_threshold *= adjustment
            print(f"[Auto-Calibration] Detected noisy recording (Noise Floor: {median_noise:.4f}°). "
                  f"Adjusting thresholds by factor of {adjustment:.2f}x. "
                  f"New Dispersion Threshold: {self.dispersion_threshold:.2f}°, "
                  f"New Velocity Threshold: {self.velocity_threshold:.2f}°/s")

    def _pixel_to_degrees(self, pixel_distance: float) -> float:
        """Convert pixel distance to visual degrees based on physical settings"""
        screen_diagonal_pixels = np.sqrt(self.screen_width**2 + self.screen_height**2)
        pixels_per_degree = screen_diagonal_pixels / (2 * np.arctan(
            self.screen_diagonal_cm / (2 * self.viewing_distance_cm)
        ) * 180 / np.pi)
        return pixel_distance / pixels_per_degree
    
    def _calculate_velocity(self, 
                           x1: float, y1: float, 
                           x2: float, y2: float,
                           time_diff: float) -> float:
        """Calculate gaze velocity in degrees per second"""
        pixel_distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        distance_degrees = self._pixel_to_degrees(pixel_distance)
        return distance_degrees / time_diff if time_diff > 0 else 0
    
    def _detect_saccades_count(self, gaze_x: np.ndarray, gaze_y: np.ndarray, timestamps: np.ndarray) -> int:
        """Detect valid saccades using the dynamically adjusted velocity threshold"""
        if len(gaze_x) < 2:
            return 0
        
        x_pixels = gaze_x * self.screen_width
        y_pixels = gaze_y * self.screen_height
        
        pixel_distances = np.sqrt(np.diff(x_pixels) ** 2 + np.diff(y_pixels) ** 2)
        time_diffs = np.diff(timestamps)
        velocities = np.zeros(len(gaze_x), dtype=float)
        valid_diffs = time_diffs > 0
        if np.any(valid_diffs):
            velocities[1:][valid_diffs] = (
                self._pixel_to_degrees(pixel_distances[valid_diffs]) / time_diffs[valid_diffs]
            )

        saccade_mask = np.array(velocities) > self.velocity_threshold
        saccades_count = 0
        in_saccade = False
        saccade_start = 0
        
        for i in range(len(saccade_mask)):
            if saccade_mask[i] and not in_saccade:
                in_saccade = True
                saccade_start = i
            elif not saccade_mask[i] and in_saccade:
                in_saccade = False
                duration = timestamps[i] - timestamps[saccade_start]
                if duration >= self.min_saccade_duration:
                    saccades_count += 1
        return saccades_count
    
    def _detect_fixations_data(self, gaze_x: np.ndarray, gaze_y: np.ndarray, timestamps: np.ndarray) -> Tuple[int, float]:
        """Detect fixations using the dynamically adjusted dispersion threshold"""
        window_size = self.fixation_window_size
        if len(gaze_x) < window_size:
            return 0, 0.0
        
        x_pixels = gaze_x * self.screen_width
        y_pixels = gaze_y * self.screen_height
        
        fixations_count = 0
        total_fixation_duration = 0.0
        i = 0
        
        while i < len(gaze_x) - window_size:
            x_window = x_pixels[i:i + window_size]
            y_window = y_pixels[i:i + window_size]
            
            max_disp = max(self._pixel_to_degrees(np.max(x_window) - np.min(x_window)),
                           self._pixel_to_degrees(np.max(y_window) - np.min(y_window)))
            
            if max_disp < self.dispersion_threshold:
                fixation_start = i
                fixation_end = i + window_size
                
                while fixation_end < len(gaze_x):
                    x_w = x_pixels[fixation_start:fixation_end + 1]
                    y_w = y_pixels[fixation_start:fixation_end + 1]
                    max_d = max(self._pixel_to_degrees(np.max(x_w) - np.min(x_w)),
                                self._pixel_to_degrees(np.max(y_w) - np.min(y_w)))
                    if max_d < self.dispersion_threshold:
                        fixation_end += 1
                    else:
                        break
                
                duration = timestamps[fixation_end - 1] - timestamps[fixation_start]
                if duration >= self.min_fixation_duration:
                    fixations_count += 1
                    total_fixation_duration += duration
                i = fixation_end
            else:
                i += 1
                
        return fixations_count, total_fixation_duration
    
    def analyze_gaze_data(self, gaze_x: np.ndarray, gaze_y: np.ndarray, timestamps: np.ndarray) -> EyeMovementMetrics:
        """Main pipeline: dynamically self-calibrates, smooths, and extracts normalized metrics"""
        self.reset_thresholds()
        valid_mask = ~(np.isnan(gaze_x) | np.isnan(gaze_y))
        gaze_x_valid = gaze_x[valid_mask]
        gaze_y_valid = gaze_y[valid_mask]
        timestamps_valid = timestamps[valid_mask]
        
        if len(gaze_x_valid) < max(self.fixation_window_size, self.smoothing_window_size):
            return EyeMovementMetrics(0.0, 0.0, 0.0)
            
        # שלב כיול עצמי דינמי - קביעת רצפת הרעש לפני סינון והחלקה!
        self._auto_calibrate_thresholds(gaze_x_valid, gaze_y_valid)
            
        # החלקת אותות מבוססת ממוצע נע לרגישות תנועות ראש ותאורה
        if self.smoothing_window_size > 1:
            window = np.ones(self.smoothing_window_size) / self.smoothing_window_size
            gaze_x_smoothed = np.convolve(gaze_x_valid, window, mode='same')
            gaze_y_smoothed = np.convolve(gaze_y_valid, window, mode='same')
            
            edge = self.smoothing_window_size // 2
            gaze_x_smoothed[:edge], gaze_x_smoothed[-edge:] = gaze_x_valid[:edge], gaze_x_valid[-edge:]
            gaze_y_smoothed[:edge], gaze_y_smoothed[-edge:] = gaze_y_valid[:edge], gaze_y_valid[-edge:]
        else:
            gaze_x_smoothed, gaze_y_smoothed = gaze_x_valid, gaze_y_valid
        
        # חישוב כמויות וזמנים גולמיים עם הספים המעודכנים
        raw_fix_count, raw_fix_duration = self._detect_fixations_data(gaze_x_smoothed, gaze_y_smoothed, timestamps_valid)
        raw_sac_count = self._detect_saccades_count(gaze_x_smoothed, gaze_y_smoothed, timestamps_valid)
        
        # נרמול הערכים לפי דקה
        total_duration_minutes = (timestamps_valid[-1] - timestamps_valid[0]) / 60.0
        
        if total_duration_minutes > 0:
            return EyeMovementMetrics(
                fixation_duration=raw_fix_duration / total_duration_minutes,
                fixation_count=raw_fix_count / total_duration_minutes,
                saccade_count=raw_sac_count / total_duration_minutes
            )
        else:
            return EyeMovementMetrics(0.0, 0.0, 0.0)
            
    def to_dict(self, metrics: EyeMovementMetrics) -> Dict[str, float]:
        """Helper method to output directly to format expected by external scripts"""
        return {
            "fixation_duration": metrics.fixation_duration,
            "fixation_count": metrics.fixation_count,
            "saccade_count": metrics.saccade_count
        }

    def export_metrics_json(self, metrics: EyeMovementMetrics, filename: str):
        """Export calculated metrics to a JSON file (Kept for backwards compatibility)"""
        data = {
            "metadata": {
                "analyzed_at": datetime.now().isoformat(),
                "metrics_format": "normalized_per_minute"
            },
            "metrics": self.to_dict(metrics)
        }
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Metrics exported to {filename}")


def main_analysis(gaze_data_json_path: str):
    """
    Analyze previously recorded gaze data.
    
    Args:
        gaze_data_json_path: Path to JSON file from eye_tracker_recorder.py
    """
    # Load data
    with open(gaze_data_json_path, 'r') as f:
        data = json.load(f)
    
    gaze_samples = data['gaze_data']
    
    # Extract arrays
    timestamps = np.array([s['timestamp'] for s in gaze_samples]) / 1_000_000  # Convert to seconds
    gaze_x = np.array([s['left_x'] if s['left_x'] is not None else np.nan for s in gaze_samples])
    gaze_y = np.array([s['left_y'] if s['left_y'] is not None else np.nan for s in gaze_samples])
    
    # Normalize timestamps
    if len(timestamps) > 0:
        timestamps = timestamps - timestamps[0]
    
    # Analyze using adaptive analyzer
    analyzer = EyeMovementAnalyzer()
    metrics = analyzer.analyze_gaze_data(gaze_x, gaze_y, timestamps)
    
    print("\n" + "="*20 + " ANALYSIS RESULTS " + "="*20)
    print(f"Fixation Duration/Min: {metrics.fixation_duration:.2f} seconds")
    print(f"Fixation Count/Min:    {metrics.fixation_count:.2f}")
    print(f"Saccade Count/Min:     {metrics.saccade_count:.2f}")
    print("="*58 + "\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        main_analysis(sys.argv[1])
    else:
        print("Usage: python eye_movement_analyzer.py <path_to_gaze_data.json>")
