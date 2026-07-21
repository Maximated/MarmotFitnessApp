def scale_points(
    values: list[float], width: int = 600, height: int = 200, padding: int = 20
) -> list[tuple[float, float]]:
    if not values:
        return []

    min_v, max_v = min(values), max(values)
    if min_v == max_v:
        min_v -= 1
        max_v += 1

    n = len(values)
    x_step = (width - 2 * padding) / (n - 1) if n > 1 else 0
    y_range = max_v - min_v

    points = []
    for i, v in enumerate(values):
        x = padding + i * x_step
        y = height - padding - ((v - min_v) / y_range) * (height - 2 * padding)
        points.append((round(x, 1), round(y, 1)))
    return points


def polyline_points(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x},{y}" for x, y in points)
