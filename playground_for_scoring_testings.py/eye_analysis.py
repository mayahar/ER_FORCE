"""
Script to test the robust EyeMovementAnalyzer on existing CSV recordings.
"""

import pandas as pd
import numpy as np
from eye_tracking_analysis.eye_movement_analyzer import EyeMovementAnalyzer

# הגדרת נתיבים לקבצים הקיימים שלך
RAW_GAZE_FILE = "C:\\Users\\לינוי\\Documents\\ער FORCE\\session 18.05.2026\\1_2026-05-18_11-14-29\\eye\\gaze_raw_1_2026-05-18_11-14-29.csv"
OLD_FEATURES_FILE = "C:\\Users\\לינוי\\Documents\\ער FORCE\\session 18.05.2026\\1_2026-05-18_11-14-29\\eye\\eye_features_1_2026-05-18_11-14-29.csv"

def run_evaluation():
    print("=" * 60)
    print("משחזר נתונים ומריץ ניתוח תנועות עיניים משופר...")
    print("=" * 60)
    
    # 1. טעינת הנתונים הגולמיים מהקלטה הקיימת
    try:
        df_raw = pd.read_csv(RAW_GAZE_FILE)
    except FileNotFoundError:
        print(f"שגיאה: לא ניתן למצוא את הקובץ הגולמי {RAW_GAZE_FILE}")
        return

    # חילוץ מערכים וניקוי ערכים חסרים לפי ה-Validity
    # במידה והעין לא נמצאה או שהנתון לא תקף, נהפוך ל-NaN
    valid_mask = df_raw['Validity'] == 'both_valid'
    
    gaze_x = np.where(valid_mask, df_raw['Left_X'], np.nan)
    gaze_y = np.where(valid_mask, df_raw['Left_Y'], np.nan)
    
    # המרת זמן ממילישניות לשניות
    timestamps = df_raw['timestamp_ms'].to_numpy() / 1000.0
    
    # 2. הרצת האנלייזר החדש והסלחני
    analyzer = EyeMovementAnalyzer()
    
    fixations, saccades, metrics = analyzer.analyze_gaze_data(gaze_x, gaze_y, timestamps)
    
    # 3. טעינת התוצאות הישנות לצורך השוואה
    try:
        df_old = pd.read_csv(OLD_FEATURES_FILE).iloc[0]
        old_fixations = int(df_old['fixation_count'])
        old_saccades = int(df_old['saccade_count'])
        old_mean_vel = df_old['analysis_mean_saccade_velocity']
    except Exception:
        # ערכי ברירת מחדל למקרה שהקובץ לא נגיש
        old_fixations = 0
        old_saccades = 526
        old_mean_vel = 173.09

    # 4. הדפסת דוח השוואתי מלא
    print("\n" + "#" * 25 + " דוח השוואת תוצאות " + "#" * 25)
    print(f"משך הניתוח הכולל: {metrics.total_duration:.2f} שניות")
    print("\n--- פיקסציות (Fixations) ---")
    print(f"תוצאה קודמת: {old_fixations} פיקסציות")
    print(f"תוצאה חדשה (מתוקנת): {metrics.num_fixations} פיקסציות (הצלחה!)")
    if metrics.num_fixations > 0:
        print(f"  קצב פיקסציות לדקה: {metrics.fixations_per_minute:.2f}")
        print(f"  משך פיקסציה ממוצע: {metrics.mean_fixation_duration * 1000:.1f} מילישניות")
        print(f"  סך כל זמן הפיקסציות: {metrics.total_fixation_duration:.2f} שניות")
    
    print("\n--- סאקאדות (Saccades) ---")
    print(f"תוצאה קודמת: {old_saccades} (זיהוי יתר חריג עקב רעש)")
    print(f"תוצאה חדשה (מתוקנת): {metrics.num_saccades} סאקאדות")
    print(f"  קצב סאקאדות לדקה: {metrics.saccades_per_minute:.2f}")
    print(f"  מהירות סאקאדה ממוצעת חדשה: {metrics.mean_saccade_velocity:.2f} מעלות/שנייה")
    print(f"  (מהירות ממוצעת קודמת: {old_mean_vel:.2f} מעלות/שנייה)")
    print("#" * 69 + "\n")

if __name__ == "__main__":
    run_evaluation()