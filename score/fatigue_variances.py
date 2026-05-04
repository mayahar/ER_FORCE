# =========================
# POPULATION STD (LITERATURE-BASED)
# =========================

VOICE_STD = {
    # strong literature support
    "Pitch": {
        "male": 20.0,
        "female": 30.0
    },

    # MFCC — noisy, use conservative estimate
    "MFCC": 8.0,

    # NO RELIABLE STD → None
    "dLPC": None,
    "PARCOR": None,
    "LPC": None
}

EYE_STD = {
    # based on literature ranges
    "fixation_duration": 0.09,   # ~90ms normalized
    "fixation_count": 0.20,
    "saccade_count": 0.22
}

GAME_STD = {
    "score": 35.0  # PVT-like variability (ms scale or normalized equivalent)
}