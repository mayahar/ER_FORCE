"""
Eye Movement Feature Extraction and Analysis
Calculates fixations, saccades, and eye movement metrics per minute.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional
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
    """Aggregated eye movement metrics"""
    total_duration: float
    num_fixations: int
    num_saccades: int
    fixations_per_minute: float
    saccades_per_minute: float
    mean_fixation_duration: float
    median_fixation_duration: float
    total_fixation_duration: float
    fixation_duration_per_minute: float
    mean_saccade_duration: float
    mean_saccade_amplitude: float
    mean_saccade_velocity: float
    blink_rate: float


class EyeMovementAnalyzer:
    """Analyzes eye tracking data to detect events and calculate metrics"""
    
    def __init__(self, 
                 sampling_rate: float = 250.0,
                 velocity_threshold: float = 30.0,
                 dispersion_threshold: float = 0.5,
                 min_fixation_duration: float = 0.1):
        """
        Initialize the eye movement analyzer.
        
        Args:
            sampling_rate: Hz, typical 250-1000 Hz for Tobii trackers
            velocity_threshold: deg/s, threshold for saccade detection
            dispersion_threshold: visual degrees, threshold for fixation detection
            min_fixation_duration: seconds, minimum duration for valid fixation
        """
        self.sampling_rate = sampling_rate
        self.velocity_threshold = velocity_threshold
        self.dispersion_threshold = dispersion_threshold
        self.min_fixation_duration = min_fixation_duration
        self.screen_width = 1920
        self.screen_height = 1080
        self.screen_diagonal_cm = 54  # Adjust based on your display
        
    def _pixel_to_degrees(self, pixel_distance: float) -> float:
        """Convert pixel distance to visual degrees"""
        screen_diagonal_pixels = np.sqrt(self.screen_width**2 + self.screen_height**2)
        pixels_per_degree = screen_diagonal_pixels / (2 * np.arctan(
            self.screen_diagonal_cm / (2 * 60)
        ) * 180 / np.pi)  # Assuming viewing distance of 60cm
        return pixel_distance / pixels_per_degree
    
    def _calculate_velocity(self, 
                           x1: float, y1: float, 
                           x2: float, y2: float,
                           time_diff: float) -> float:
        """Calculate gaze velocity in degrees per second"""
        pixel_distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        screen_diagonal_pixels = np.sqrt(self.screen_width**2 + self.screen_height**2)
        
        # Convert to degrees (rough approximation)
        distance_degrees = (pixel_distance / screen_diagonal_pixels) * 60
        
        if time_diff > 0:
            return distance_degrees / time_diff
        return 0
    
    def detect_saccades_velocity(self, 
                                gaze_x: np.ndarray, 
                                gaze_y: np.ndarray,
                                timestamps: np.ndarray) -> List[Saccade]:
        """
        Detect saccades using velocity-based detection (I-VT algorithm).
        
        Args:
            gaze_x: Array of x gaze positions (normalized 0-1)
            gaze_y: Array of y gaze positions (normalized 0-1)
            timestamps: Array of timestamps
        
        Returns:
            List of detected saccades
        """
        if len(gaze_x) < 2:
            return []
        
        # Convert normalized coordinates to pixels
        x_pixels = gaze_x * self.screen_width
        y_pixels = gaze_y * self.screen_height
        
        # Calculate velocities
        velocities = []
        for i in range(1, len(gaze_x)):
            vel = self._calculate_velocity(
                x_pixels[i-1], y_pixels[i-1],
                x_pixels[i], y_pixels[i],
                timestamps[i] - timestamps[i-1]
            )
            velocities.append(vel)
        
        velocities = np.array([0] + velocities)  # Prepend 0 for first sample
        
        # Detect saccade periods (velocity > threshold)
        saccade_mask = velocities > self.velocity_threshold
        
        saccades = []
        in_saccade = False
        saccade_start = 0
        
        for i in range(len(saccade_mask)):
            if saccade_mask[i] and not in_saccade:
                # Saccade starts
                in_saccade = True
                saccade_start = i
            elif not saccade_mask[i] and in_saccade:
                # Saccade ends
                in_saccade = False
                saccade_end = i
                
                if saccade_end > saccade_start:
                    duration = timestamps[saccade_end] - timestamps[saccade_start]
                    amplitude = np.sqrt(
                        (x_pixels[saccade_end] - x_pixels[saccade_start])**2 +
                        (y_pixels[saccade_end] - y_pixels[saccade_start])**2
                    )
                    mean_velocity = np.mean(velocities[saccade_start:saccade_end])
                    
                    saccade = Saccade(
                        start_time=timestamps[saccade_start],
                        end_time=timestamps[saccade_end],
                        duration=duration,
                        amplitude=amplitude,
                        velocity=mean_velocity,
                        start_x=gaze_x[saccade_start],
                        start_y=gaze_y[saccade_start],
                        end_x=gaze_x[saccade_end],
                        end_y=gaze_y[saccade_end]
                    )
                    saccades.append(saccade)
        
        return saccades
    
    def detect_fixations_dispersion(self,
                                   gaze_x: np.ndarray,
                                   gaze_y: np.ndarray,
                                   timestamps: np.ndarray,
                                   window_size: int = 20) -> List[Fixation]:
        """
        Detect fixations using dispersion-based detection (I-DT algorithm).
        
        Args:
            gaze_x: Array of x gaze positions (normalized 0-1)
            gaze_y: Array of y gaze positions (normalized 0-1)
            timestamps: Array of timestamps
            window_size: Number of samples in sliding window
        
        Returns:
            List of detected fixations
        """
        if len(gaze_x) < window_size:
            return []
        
        # Convert to pixels
        x_pixels = gaze_x * self.screen_width
        y_pixels = gaze_y * self.screen_height
        
        fixations = []
        i = 0
        
        while i < len(gaze_x) - window_size:
            # Get window
            x_window = x_pixels[i:i + window_size]
            y_window = y_pixels[i:i + window_size]
            
            # Calculate dispersion
            x_dispersion = np.max(x_window) - np.min(x_window)
            y_dispersion = np.max(y_window) - np.min(y_window)
            
            # Check if within dispersion threshold (converted to degrees)
            x_dispersion_deg = self._pixel_to_degrees(x_dispersion)
            y_dispersion_deg = self._pixel_to_degrees(y_dispersion)
            max_dispersion_deg = max(x_dispersion_deg, y_dispersion_deg)
            
            if max_dispersion_deg < self.dispersion_threshold:
                # Start of potential fixation
                fixation_start = i
                fixation_end = i + window_size
                
                # Extend fixation while still within threshold
                while fixation_end < len(gaze_x):
                    x_window = x_pixels[fixation_start:fixation_end + 1]
                    y_window = y_pixels[fixation_start:fixation_end + 1]
                    
                    x_disp = np.max(x_window) - np.min(x_window)
                    y_disp = np.max(y_window) - np.min(y_window)
                    
                    x_disp_deg = self._pixel_to_degrees(x_disp)
                    y_disp_deg = self._pixel_to_degrees(y_disp)
                    max_disp_deg = max(x_disp_deg, y_disp_deg)
                    
                    if max_disp_deg < self.dispersion_threshold:
                        fixation_end += 1
                    else:
                        break
                
                # Create fixation if meets minimum duration
                duration = timestamps[fixation_end - 1] - timestamps[fixation_start]
                if duration >= self.min_fixation_duration:
                    center_x = np.mean(x_pixels[fixation_start:fixation_end])
                    center_y = np.mean(y_pixels[fixation_start:fixation_end])
                    
                    fixation = Fixation(
                        start_time=timestamps[fixation_start],
                        end_time=timestamps[fixation_end - 1],
                        duration=duration,
                        x=center_x / self.screen_width,  # Normalize back
                        y=center_y / self.screen_height,
                        amplitude=None
                    )
                    fixations.append(fixation)
                
                i = fixation_end
            else:
                i += 1
        
        return fixations
    
    def calculate_metrics(self,
                         fixations: List[Fixation],
                         saccades: List[Saccade],
                         total_duration: float) -> EyeMovementMetrics:
        """
        Calculate aggregated eye movement metrics.
        
        Args:
            fixations: List of detected fixations
            saccades: List of detected saccades
            total_duration: Total duration of recording in seconds
        
        Returns:
            EyeMovementMetrics object
        """
        # Calculate per-minute rates
        duration_minutes = total_duration / 60
        
        fixations_per_minute = len(fixations) / duration_minutes if duration_minutes > 0 else 0
        saccades_per_minute = len(saccades) / duration_minutes if duration_minutes > 0 else 0
        
        # Fixation statistics
        fixation_durations = [f.duration for f in fixations]
        mean_fixation_duration = np.mean(fixation_durations) if fixation_durations else 0
        median_fixation_duration = np.median(fixation_durations) if fixation_durations else 0
        total_fixation_duration = np.sum(fixation_durations)
        fixation_duration_per_minute = total_fixation_duration / duration_minutes if duration_minutes > 0 else 0
        
        # Saccade statistics
        saccade_durations = [s.duration for s in saccades]
        saccade_amplitudes = [s.amplitude for s in saccades]
        saccade_velocities = [s.velocity for s in saccades]
        
        mean_saccade_duration = np.mean(saccade_durations) if saccade_durations else 0
        mean_saccade_amplitude = np.mean(saccade_amplitudes) if saccade_amplitudes else 0
        mean_saccade_velocity = np.mean(saccade_velocities) if saccade_velocities else 0
        
        # Estimate blink rate (gaps in gaze data)
        # Simplified: assume large gaps indicate blinks
        blink_rate = 0  # Placeholder
        
        return EyeMovementMetrics(
            total_duration=total_duration,
            num_fixations=len(fixations),
            num_saccades=len(saccades),
            fixations_per_minute=fixations_per_minute,
            saccades_per_minute=saccades_per_minute,
            mean_fixation_duration=mean_fixation_duration,
            median_fixation_duration=median_fixation_duration,
            total_fixation_duration=total_fixation_duration,
            fixation_duration_per_minute=fixation_duration_per_minute,
            mean_saccade_duration=mean_saccade_duration,
            mean_saccade_amplitude=mean_saccade_amplitude,
            mean_saccade_velocity=mean_saccade_velocity,
            blink_rate=blink_rate
        )
    
    def analyze_gaze_data(self,
                         gaze_x: np.ndarray,
                         gaze_y: np.ndarray,
                         timestamps: np.ndarray) -> Tuple[List[Fixation], List[Saccade], EyeMovementMetrics]:
        """
        Complete analysis pipeline.
        
        Args:
            gaze_x: Array of x gaze positions (normalized 0-1)
            gaze_y: Array of y gaze positions (normalized 0-1)
            timestamps: Array of timestamps (seconds)
        
        Returns:
            Tuple of (fixations, saccades, metrics)
        """
        # Filter out invalid samples
        valid_mask = ~(np.isnan(gaze_x) | np.isnan(gaze_y))
        gaze_x_valid = gaze_x[valid_mask]
        gaze_y_valid = gaze_y[valid_mask]
        timestamps_valid = timestamps[valid_mask]
        
        if len(gaze_x_valid) < 2:
            return [], [], None
        
        # Detect events
        fixations = self.detect_fixations_dispersion(gaze_x_valid, gaze_y_valid, timestamps_valid)
        saccades = self.detect_saccades_velocity(gaze_x_valid, gaze_y_valid, timestamps_valid)
        
        # Calculate metrics
        total_duration = timestamps_valid[-1] - timestamps_valid[0]
        metrics = self.calculate_metrics(fixations, saccades, total_duration)
        
        return fixations, saccades, metrics
    
    def print_metrics(self, metrics: EyeMovementMetrics):
        """Pretty print metrics"""
        print("\n" + "="*60)
        print("EYE MOVEMENT METRICS")
        print("="*60)
        print(f"Total Duration: {metrics.total_duration:.2f} seconds")
        print("\nFIXATIONS:")
        print(f"  Count: {metrics.num_fixations}")
        print(f"  Per Minute: {metrics.fixations_per_minute:.2f}")
        print(f"  Mean Duration: {metrics.mean_fixation_duration*1000:.2f} ms")
        print(f"  Median Duration: {metrics.median_fixation_duration*1000:.2f} ms")
        print(f"  Total Duration: {metrics.total_fixation_duration:.2f} seconds")
        print(f"  Duration per Minute: {metrics.fixation_duration_per_minute:.2f} seconds")
        print("\nSACCADES:")
        print(f"  Count: {metrics.num_saccades}")
        print(f"  Per Minute: {metrics.saccades_per_minute:.2f}")
        print(f"  Mean Duration: {metrics.mean_saccade_duration*1000:.2f} ms")
        print(f"  Mean Amplitude: {metrics.mean_saccade_amplitude:.2f} pixels")
        print(f"  Mean Velocity: {metrics.mean_saccade_velocity:.2f} deg/s")
        print("="*60 + "\n")
    
    def export_metrics_json(self, metrics: EyeMovementMetrics, filename: str):
        """Export metrics to JSON"""
        data = {
            "total_duration_seconds": metrics.total_duration,
            "fixations": {
                "count": metrics.num_fixations,
                "per_minute": metrics.fixations_per_minute,
                "mean_duration_ms": metrics.mean_fixation_duration * 1000,
                "median_duration_ms": metrics.median_fixation_duration * 1000,
                "total_duration_seconds": metrics.total_fixation_duration,
                "duration_per_minute_seconds": metrics.fixation_duration_per_minute
            },
            "saccades": {
                "count": metrics.num_saccades,
                "per_minute": metrics.saccades_per_minute,
                "mean_duration_ms": metrics.mean_saccade_duration * 1000,
                "mean_amplitude_pixels": metrics.mean_saccade_amplitude,
                "mean_velocity_deg_per_sec": metrics.mean_saccade_velocity
            }
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
    gaze_x = np.array([s['left_x'] if s['left_x'] is not None else np.nan 
                      for s in gaze_samples])
    gaze_y = np.array([s['left_y'] if s['left_y'] is not None else np.nan 
                      for s in gaze_samples])
    
    # Normalize timestamps
    timestamps = timestamps - timestamps[0]
    
    # Analyze
    analyzer = EyeMovementAnalyzer()
    fixations, saccades, metrics = analyzer.analyze_gaze_data(gaze_x, gaze_y, timestamps)
    
    # Print results
    print(f"\nAnalysis complete: {len(gaze_samples)} samples processed")
    analyzer.print_metrics(metrics)
    
    # Export
    analyzer.export_metrics_json(metrics, "eye_movement_metrics.json")


if __name__ == "__main__":
    # Example: analyze previously recorded data
    main_analysis("gaze_data.json")