# =========================
# FEATURE CONFIGURATION
# =========================

FEATURES = {

    # =====================================================
    # VOICE
    # =====================================================
        "dLPC": {
            "modality": "voice",
            "weight": 0.80,              # 80% דיוק זיהוי לפי המחקר
            "direction": 1,              # 1 מסמל עלייה בערך המדד ככל שהעייפות עולה
            "std": None,                 # רמה 3 - אין שונות אוכלוסייה מוגדרת
            "expected_change": 0.35,     # ממוצע מרכז הטווח במחקר (20% עד 50% עלייה)
            "MEASUREMENT_VALID_RANGES": (0.01, 0.45)
        },

        "PARCOR": {
            "modality": "voice",
            "weight": 0.77,              # 77% דיוק זיהוי לפי המחקר
            "direction": -1,             # -1 מסמל ירידה בערך המדד ככל שהעייפות עולה
            "std": None,                 # רמה 3 - אין שונות אוכלוסייה מוגדרת
            "expected_change": 0.22,     # ממוצע מרכז הטווח במחקר (15% עד 30% ירידה)
            "MEASUREMENT_VALID_RANGES": (0.15, 0.85)
        },

        "Pitch": {
            "modality": "voice",
            "weight": 0.76,              # 76% דיוק זיהוי לפי המחקר
            "direction": -1,             # -1 מסמל ירידה בערך המדד ככל שהעייפות עולה
            "std": {
                "male": 18.5,            # ממוצע שונות גברים לפי הספרות (12 עד 25 הרץ)
                "female": 26.5           # ממוצע שונות נשים לפי הספרות (18 עד 35 הרץ)
            },
            "expected_change": 0.075,    # צניחה ממוצעת של כ-7.5% בתדר היסודי (5% עד 10%)
            "MEASUREMENT_VALID_RANGES": (65.0, 350.0)
        },

        "MFCC": {
            "modality": "voice",
            "weight": 0.70,              # מתאם מובהק בהתפלגויות, ממוקם כפיצ'ר משלים
            "direction": -1,             # -1 מסמל ירידה בערך המדד ככל שהעייפות עולה
            "std": 11.5,                 # ממוצע שונות רכיב C1 לפי הספרות (8 עד 15)
            "expected_change": 0.275,    # ממוצע מרכז הטווח במחקר (15% עד 40% ירידה)
            "MEASUREMENT_VALID_RANGES": (5.0, 80.0)
        },

        "LPC": {
            "modality": "voice",
            "weight": 0.65,              # מתאם מובהק ברמת מרחב ההיגוי הכללי במחקר
            "direction": -1,             # -1 מסמל ירידה בערך המדד ככל שהעייפות עולה
            "std": None,                 # רמה 3 - אין שונות אוכלוסייה מוגדרת
            "expected_change": 0.10,     # ממוצע מרכז הטווח במחקר (5% עד 15% ירידה)
            "MEASUREMENT_VALID_RANGES": (500.0, 1800.0)
        },


    # =====================================================
    # EYE TRACKING
    # =====================================================

"fixation_duration": {
        "modality": "eye",
        "weight": 1.00,             # המתאם הגבוה ביותר לעייפות במחקר (t=3.32)
        "direction": 1,             # עליה במדד מצביעה על הגברת עייפות
        "std": 0.08,                # שבריר סטיית התקן מהממוצע בערנות (1.52 / 18.70)
        "expected_change": 0.63,    # האחוז בו המדד משתנה פיזית (62.56%)
        "MEASUREMENT_VALID_RANGES": (5.0, 50.0)  # שניות לדקה
    },

    "saccade_count": {
        "modality": "eye",
        "weight": 0.94,             # מתאם יחסי חזק מאוד (t=3.12, מחושב כ-3.12/3.32)
        "direction": 1,             # עליה במדד מצביעה על הגברת עייפות
        "std": 0.08,                # שבריר סטיית התקן מהממוצע בערנות (3.65 / 43.33)
        "expected_change": 0.39,    # האחוז בו המדד משתנה פיזית (38.98%)
        "MEASUREMENT_VALID_RANGES": (10.0, 120.0) # קצב לדקה
    },

    "fixation_count": {
        "modality": "eye",
        "weight": 0.83,             # מתאם יחסי בינוני-חזק (t=2.76, מחושב כ-2.76/3.32)
        "direction": 1,             # עליה במדד מצביעה על הגברת עייפות
        "std": 0.07,                # שבריר סטיית התקן מהממוצע בערנות (5.49 / 74.01)
        "expected_change": 0.28,    # האחוז בו המדד משתנה פיזית (27.69%)
        "MEASUREMENT_VALID_RANGES": (20.0, 150.0) # קצב לדקה
    },

    # =====================================================
    # GAME
    # =====================================================

    "score": {
        "modality": "game",
        "weight": 0.82,
        "direction": -1,
        "std": 35.0,
        "expected_change": 0.25,
        "MEASUREMENT_VALID_RANGES": (0.0, 100.0)
    },

    # =====================================================
    # SUBJECTIVE QUESTIONNAIRE
    # =====================================================

    "fatigue_self": {
        "modality": "subjective",
        "weight": 1,
        "direction": 1,
        "std": None,
        "expected_change": None,
        "scoring": "absolute",
        "min": 0.0,
        "max": 10.0
    },

    "sleep_last": {
        "modality": "subjective",
        "weight": 1,
        "direction": -1,
        "std": None,
        "expected_change": None,
        "scoring": "absolute",
        "min": 0.0,
        "max": 8.0
    },

    "sleep_previous": {
        "modality": "subjective",
        "weight": 0.8,
        "direction": -1,
        "std": None,
        "expected_change": None,
        "scoring": "absolute",
        "min": 0.0,
        "max": 8.0
    }
}


# =========================
# MODALITY WEIGHTS
# =========================

MODALITY_WEIGHTS = {
    "voice": 0.768,
    "eye": 0.825,
    "game": 0.82,
    "subjective": 0.1
}
