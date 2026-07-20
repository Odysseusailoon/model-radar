"""Chart geometry for the dashboard.

Line/area geometry is computed here because it needs real coordinate math;
bar-style marks are laid out as percentage widths in the template, where CSS
handles responsiveness and the labels stay selectable text.

Series colors come from the validated categorical palette and are assigned by
PRODUCT NAME, never by rank — filtering the dashboard must not repaint the
surviving series. Slots are taken in fixed order from the reference palette
(blue, green, magenta); the light/dark pairs were validated together with
scripts/validate_palette (all-pairs, both modes: worst CVD dE 13.0, worst
normal-vision dE 26.5, well clear of the 8/15 gates).
"""
from __future__ import annotations

from dataclasses import dataclass

# Categorical slots 1-3, light and dark steps of the same hues.
PALETTE = [
    {"slot": 1, "hue": "blue", "light": "#2a78d6", "dark": "#3987e5"},
    {"slot": 2, "hue": "green", "light": "#008300", "dark": "#008300"},
    {"slot": 3, "hue": "magenta", "light": "#e87ba4", "dark": "#d55181"},
]
# Past three products we fold the tail into "Other" rather than generating a
# fourth hue — a generated hue is indistinguishable under CVD.
OTHER = {"slot": 0, "hue": "gray", "light": "#898781", "dark": "#898781"}


def assign_colors(product_names: list[str]) -> dict[str, dict]:
    """Map product name -> palette slot, stable in configured product order.

    The `css` value is a custom property, not a hex literal, so the light and
    dark steps of the same hue swap with the theme in one place.
    """
    out = {}
    for i, name in enumerate(product_names):
        slot = PALETTE[i] if i < len(PALETTE) else OTHER
        out[name] = {
            **slot,
            "css": f"var(--series-{slot['slot']})" if slot["slot"] else "var(--series-other)",
        }
    return out


@dataclass
class LineChart:
    width: int
    height: int
    pad_l: int
    pad_b: int
    y_max: int
    series: list          # [{name, color_var, points: [(x, y, value, label)], path}]
    x_labels: list        # [(x, text)]
    y_ticks: list         # [(y, text)]
    empty: bool = False


def build_line_chart(days, series: dict, width=680, height=200, pad_l=34, pad_b=26) -> LineChart:
    """Multi-series line geometry over a shared daily x-axis."""
    plot_w = width - pad_l - 8
    plot_h = height - pad_b - 10
    n = len(days)
    peak = max([max(v) for v in series.values() if v] or [0], default=0)
    # Round the axis up to something readable rather than the raw peak.
    y_max = 4
    while y_max < peak:
        y_max *= 2
    step = plot_w / max(n - 1, 1)

    built = []
    for name, values in series.items():
        pts = []
        for i, v in enumerate(values):
            x = pad_l + i * step
            y = 10 + plot_h - (v / y_max * plot_h if y_max else 0)
            pts.append((round(x, 1), round(y, 1), v, days[i].strftime("%m-%d")))
        path = " ".join(f"{'M' if i == 0 else 'L'}{x},{y}" for i, (x, y, _, _) in enumerate(pts))
        built.append({"name": name, "points": pts, "path": path})

    x_labels = []
    if n:
        # Label ~5 ticks so they never collide at narrow widths.
        stride = max(1, n // 5)
        for i in range(0, n, stride):
            x_labels.append((round(pad_l + i * step, 1), days[i].strftime("%m-%d")))
    y_ticks = [
        (round(10 + plot_h - f * plot_h, 1), str(int(y_max * f)))
        for f in (0, 0.5, 1.0)
    ]
    return LineChart(
        width=width, height=height, pad_l=pad_l, pad_b=pad_b, y_max=y_max,
        series=built, x_labels=x_labels, y_ticks=y_ticks,
        empty=peak == 0,
    )


def pct(value: int, total: int) -> float:
    return (value / total * 100) if total else 0.0


def build_sentiment_bars(by_sentiment: dict, product_names: list[str]) -> list[dict]:
    """Diverging stacked bars for an ordered sentiment scale.

    Each row is centered on neutral: the neutral block straddles the midline,
    so the left arm is `negative + neutral/2` and the right arm is
    `positive + neutral/2`. Arms are scaled by the widest arm across all rows,
    which keeps rows comparable and guarantees nothing overflows its half —
    percentage-of-own-total would let a positive-heavy row run past the track.
    """
    rows = []
    for name in product_names:
        neg = by_sentiment.get("negative", {}).get(name, 0)
        neu = by_sentiment.get("neutral", {}).get(name, 0)
        pos = by_sentiment.get("positive", {}).get(name, 0)
        total = neg + neu + pos
        if not total:
            continue
        half = neu / total / 2
        rows.append({
            "name": name, "neg": neg, "neu": neu, "pos": pos, "total": total,
            "neg_f": neg / total, "neu_f": neu / total, "pos_f": pos / total,
            "left_arm": neg / total + half, "right_arm": pos / total + half,
        })

    scale = max([max(r["left_arm"], r["right_arm"]) for r in rows], default=0) or 1
    for r in rows:
        # Widths as a percentage of the half-track each arm occupies.
        r["neg_w"] = round(r["neg_f"] / scale * 100, 1)
        r["pos_w"] = round(r["pos_f"] / scale * 100, 1)
        r["neu_half_w"] = round(r["neu_f"] / 2 / scale * 100, 1)
        r["pos_pct"] = round(r["pos_f"] * 100)
    return rows
