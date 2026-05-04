def init_state():
    return {
        "screen": "enter_id",
        "session_id": None,
        "features": {}
    }


def set_screen(new_screen):
    return new_screen