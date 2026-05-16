# =========================
# FEATURE CONFIGURATION
# =========================

FEATURES = {

    # =====================================================
    # VOICE
    # =====================================================

    "dLPC": {
        "modality": "voice",
        "weight": 0.80,
        "direction": 1,
        "std": None,
        "expected_change": 0.20,
        "MEASUREMENT_VALID_RANGES": (0.001, 0.3)
    },

    "PARCOR": {
        "modality": "voice",
        "weight": 0.77,
        "direction": 1,
        "std": None,
        "expected_change": 0.10,
        "MEASUREMENT_VALID_RANGES": (-1.0, 1.0)
    },

    "LPC": {
        "modality": "voice",
        "weight": 0.76,
        "direction": 1,
        "std": None,
        "expected_change": 0.12,
        "MEASUREMENT_VALID_RANGES": (-1.45, -0.35)
    },

    "Pitch": {
        "modality": "voice",
        "weight": 0.76,
        "direction": 1,
        "std": {
            "male": 20.0,
            "female": 30.0
        },
        "expected_change": 0.18,
        "MEASUREMENT_VALID_RANGES": (65.0, 350.0)
    },

    "MFCC": {
        "modality": "voice",
        "weight": 0.75,
        "direction": 1,
        "std": 8.0,
        "expected_change": 0.20,
        "MEASUREMENT_VALID_RANGES": (-110.0, -25.0)
    },

    # =====================================================
    # EYE TRACKING
    # =====================================================

    "fixation_duration": {
        "modality": "eye",
        "weight": 1.00,
        "direction": 1,
        "std": 0.09,
        "expected_change": 0.50,
        "MEASUREMENT_VALID_RANGES": (0.01, 10.0)
    },

    "fixation_count": {
        "modality": "eye",
        "weight": 0.90,
        "direction": 1,
        "std": 0.20,
        "expected_change": 0.45,
        "MEASUREMENT_VALID_RANGES": (1.0, 10000.0)
    },

    "saccade_count": {
        "modality": "eye",
        "weight": 1.00,
        "direction": 1,
        "std": 0.22,
        "expected_change": 0.55,
        "MEASUREMENT_VALID_RANGES": (1.0, 10000.0)
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
        "weight": 0.0,
        "direction": 1,
        "std": None,
        "expected_change": None,
        "scoring": "absolute",
        "min": 0.0,
        "max": 10.0
    },

    "sleep_last": {
        "modality": "subjective",
        "weight": 0.0,
        "direction": -1,
        "std": None,
        "expected_change": None,
        "scoring": "absolute",
        "min": 0.0,
        "max": 8.0
    },

    "sleep_previous": {
        "modality": "subjective",
        "weight": 0.0,
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
    "subjective": 0.0
}
