"""Time calculations for Puyo Puyo chain efficiency (60 fps)."""

FPS = 60


def consumption_frames(remaining_colors: int, remaining_ojama: int, erased_colors: int) -> float:
    """Estimate frames to replenish erased colored puyos.

    R0 = remaining_colors + remaining_ojama, N = erased_colors.
    t = 27*N - ((R0 + N)**2 - R0**2)/12.
    Erased ojama must not be counted in N.
    """
    values = (remaining_colors, remaining_ojama, erased_colors)
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError("All puyo counts must be nonnegative integers")
    r0 = remaining_colors + remaining_ojama
    n = erased_colors
    return n * (27 - r0 / 6 - n / 12)


def consumption_seconds(remaining_colors: int, remaining_ojama: int, erased_colors: int) -> float:
    return consumption_frames(remaining_colors, remaining_ojama, erased_colors) / FPS
