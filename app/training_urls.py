from urllib.parse import urlencode


def training_url(block_exercise_id: int, exercise_id: int | None, params: dict) -> str:
    """URL for a training slot: the catalog route when it resolves to a real
    Exercise, the block-exercise route otherwise (no gif/catálogo, but the
    same training screen)."""
    if exercise_id is not None:
        return f"/exercises/{exercise_id}/log?{urlencode(params)}"
    return f"/block-exercises/{block_exercise_id}/log?{urlencode(params)}"
