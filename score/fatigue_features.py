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
        "expected_change": 0.20
    },

    "PARCOR": {
        "modality": "voice",
        "weight": 0.77,
        "direction": 1,
        "std": None,
        "expected_change": 0.10
    },

    "LPC": {
        "modality": "voice",
        "weight": 0.76,
        "direction": 1,
        "std": None,
        "expected_change": 0.12
    },

    "Pitch": {
        "modality": "voice",
        "weight": 0.76,
        "direction": 1,
        "std": {
            "male": 20.0,
            "female": 30.0
        },
        "expected_change": 0.18
    },

    "MFCC": {
        "modality": "voice",
        "weight": 0.75,
        "direction": 1,
        "std": 8.0,
        "expected_change": 0.20
    },

    # =====================================================
    # EYE TRACKING
    # =====================================================

    "fixation_duration": {
        "modality": "eye",
        "weight": 1.00,
        "direction": 1,
        "std": 0.09,
        "expected_change": 0.50
    },

    "fixation_count": {
        "modality": "eye",
        "weight": 0.90,
        "direction": 1,
        "std": 0.20,
        "expected_change": 0.45
    },

    "saccade_count": {
        "modality": "eye",
        "weight": 1.00,
        "direction": 1,
        "std": 0.22,
        "expected_change": 0.55
    },

    # =====================================================
    # GAME
    # =====================================================

    "score": {
        "modality": "game",
        "weight": 0.82,
        "direction": -1,
        "std": 35.0,
        "expected_change": 0.25
    }
}


# =========================
# MODALITY WEIGHTS
# =========================

MODALITY_WEIGHTS = {
    "voice": 0.768,
    "eye": 0.825,
    "game": 0.82
}