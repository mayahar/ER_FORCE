"""
Eye Movement Feature Extraction and Analysis - Optimized for Fatigue Scoring
Calculates exactly 3 metrics normalized per minute with robust noise filtering.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict


@dataclass
class EyeMovementMetrics:
    """Aggregated eye movement metrics expected by downstream scripts"""
    fixation_duration: float  # סך זמן הפיקסציות לדקה (בשניות)
    fixation_count: float     # מספר פיקסציות לדקה
    saccade_count: float      # מספר סאקאדות לדקה


class EyeMovementAnalyzer:
    """Analyzes eye tracking data with robust filters and outputs 3 core fatigue metrics"""
    
    def __init__(self, 
                 sampling_rate: float = 120.0,
                 dispersion_threshold: float = 1.2,       # סף פיזור סלחני לכיול (מעלות)
                 velocity_threshold: float = 45.0,        # סף מהירות מסונן רעש (מעלות/שנייה)
                 min_fixation_duration: float = 0.1,     # משך פיקסציה מינימלי (בשניות)
                 min_saccade_duration: float = 0.03,      # משך סאקאדה מינימלי למניעת רעש (בשניות)
                 fixation_window_size: int = 8,           # חלון דגימות התחלתי לפיקסציה
                 smoothing_window_size: int = 5,          # חלון החלקת ממוצע נע לכיול גרוע
                 screen_width: int = 1920,
                 screen_height: int = 1080,
                 screen_diagonal_cm: float = 54.0,
                 viewing_distance_cm: float = 60.0):
        
        self.sampling_rate = sampling_rate
        self.dispersion_threshold = dispersion_threshold
        self.velocity_threshold = velocity_threshold
        self.min_fixation_duration = min_fixation_duration
        self.min_saccade_duration = min_saccade_duration
        self.fixation_window_size = fixation_window_size
        self.smoothing_window_size = smoothing_window_size
        
        # הגדרות פיזיות למסך
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.screen_diagonal_cm = screen_diagonal_cm
        self.viewing_distance_cm = viewing_distance_cm
        
    def _pixel_to_degrees(self, pixel_distance: float) -> float:
        """Convert pixel distance to visual degrees"""
        screen_diagonal_pixels = np.sqrt(self.screen_width**2 + self.screen_height**2)
        pixels_per_degree = screen_diagonal_pixels / (2 * np.arctan(
            self.screen_diagonal_cm / (2 * self.viewing_distance_cm)
        ) * 180 / np.pi)
        return pixel_distance / pixels_per_degree
    
    def _calculate_velocity(self, x1: float, y1: float, x2: float, y2: float, time_diff: float) -> float:
        """Calculate gaze velocity in degrees per second"""
        pixel_distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        distance_degrees = self._pixel_to_degrees(pixel_distance)
        return distance_degrees / time_diff if time_diff > 0 else 0
    
    def _detect_saccades_count(self, gaze_x: np.ndarray, gaze_y: np.ndarray, timestamps: np.ndarray) -> int:
        """Detect valid saccades and return the total count"""
        if len(gaze_x) < 2:
            return 0
        
        x_pixels = gaze_x * self.screen_width
        y_pixels = gaze_y * self.screen_height
        
        velocities = [0]
        for i in range(1, len(gaze_x)):
            vel = self._calculate_velocity(x_pixels[i-1], y_pixels[i-1], x_pixels[i], y_pixels[i], timestamps[i] - timestamps[i-1])
            velocities.append(vel)
            
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
        """Detect fixations and return (count, total_duration_seconds)"""
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
        """Main pipeline: smooths data, extracts events, and returns the 3 metrics per minute"""
        valid_mask = ~(np.isnan(gaze_x) | np.isnan(gaze_y))
        gaze_x_valid = gaze_x[valid_mask]
        gaze_y_valid = gaze_y[valid_mask]
        timestamps_valid = timestamps[valid_mask]
        
        if len(gaze_x_valid) < max(self.fixation_window_size, self.smoothing_window_size):
            return EyeMovementMetrics(0.0, 0.0, 0.0)
            
        # החלקת אותות מבוססת ממוצע נע לרגישות כיול
        if self.smoothing_window_size > 1:
            window = np.ones(self.smoothing_window_size) / self.smoothing_window_size
            gaze_x_smoothed = np.convolve(gaze_x_valid, window, mode='same')
            gaze_y_smoothed = np.convolve(gaze_y_valid, window, mode='same')
            
            edge = self.smoothing_window_size // 2
            gaze_x_smoothed[:edge], gaze_x_smoothed[-edge:] = gaze_x_valid[:edge], gaze_x_valid[-edge:]
            gaze_y_smoothed[:edge], gaze_y_smoothed[-edge:] = gaze_y_valid[:edge], gaze_y_valid[-edge:]
        else:
            gaze_x_smoothed, gaze_y_smoothed = gaze_x_valid, gaze_y_valid
        
        # חישוב כמויות וזמנים גולמיים
        raw_fix_count, raw_fix_duration = self._detect_fixations_data(gaze_x_smoothed, gaze_y_smoothed, timestamps_valid)
        raw_sac_count = self._detect_saccades_count(gaze_x_smoothed, gaze_y_smoothed, timestamps_valid)
        
        # נרמול הערכים לפי דקה (חלוקה במשך הניסוי הכולל בדקות)
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