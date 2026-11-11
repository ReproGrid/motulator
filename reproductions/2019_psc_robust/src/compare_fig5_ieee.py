"""Compare the publisher's Fig. 5 raster with the frozen PSC model."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from compare_fig5_conditions import VARIANTS
from reproduce import ROOT, loops, response


ARTWORK_URL = (
    "https://ieeexplore.ieee.org/mediastore/IEEE/content/media/41/"
    "8678530/8490668/harne5-2874584-large.gif"
)
ARTWORK_SHA256 = "a5bf260a6d22be44ea6c45542d128f884024d6acd377f28fcbd8159bc3558ca8"
FIGURES_URL = "https://ieeexplore.ieee.org/document/8490668/figures"
ARTWORK_SIZE = (820, 766)
UPPER_LABEL_VISUAL_READING = (0.95, 0.2)
# Pixel centers read from the labeled grid lines in the upper plots.
REAL_TICKS = {"gp": (350.0, 257.5), "gd": (814.5, 721.5)}
IMAGINARY_TICKS = (171.0, 208.5)
# The caption identifies the solid trace as SCR=10. This row separates it
# from the dashed and dash-dotted traces at the negative-real-axis crossing.
SOLID_CROSSING_ROW = 171
SOLID_CROSSING_COLUMNS = (762, 768)


def calibrated_strokes(blue, loop):
    """Return interior blue-pixel centers in the plot's complex coordinates."""
    y, x = np.nonzero(blue)
    x_zero, x_minus_half = REAL_TICKS[loop]
    y_zero, y_minus_point_two = IMAGINARY_TICKS
    re = (x - x_zero) * 0.5 / (x_zero - x_minus_half)
    im = (y_zero - y) * 0.2 / (y_minus_point_two - y_zero)
    interior = (re > -1.49) & (re < -0.01) & (abs(im) < 0.735)
    return np.column_stack((re[interior], im[interior]))


def compare_models(config, variants, strokes):
    """Measure each observed blue pixel's distance to the three-SCR locus union."""
    w = np.geomspace(1e-6, 1e3, 300_001)
    nominal = config["nominal"]
    kp = nominal["Ra"] / (nominal["kappa"] * nominal["V"] ** 2)
    kd = 1 / (4 * np.sqrt(2))
    inferred = variants["curve_inferred"]
    current_d, printed_q = config["fig5"]["active"]

    comparisons = {}
    for name, (flip, rounding) in VARIANTS.items():
        current_q = inferred["upper_iq_pu"] if flip else printed_q
        loci = {loop: [] for loop in strokes}
        for scr in config["fig5"]["scr"]:
            inductance = 1 / scr
            if rounding:
                inductance = inferred["inductance_by_scr_label_pu"].get(
                    str(scr), inductance
                )
            systems, _ = loops((current_d, current_q), inductance, nominal, kp, kd)
            for loop in loci:
                locus = response(systems[loop], w)
                visible = (locus.real > -1.52) & (locus.real < 0.02)
                visible &= abs(locus.imag) < 0.77
                loci[loop].append(locus[visible])
        rms = {}
        for loop, curve_parts in loci.items():
            locus = np.concatenate(curve_parts)
            tree = cKDTree(np.column_stack((locus.real, locus.imag)))
            distance, _ = tree.query(strokes[loop])
            rms[loop] = float(np.sqrt(np.mean(distance**2)))
        comparisons[name] = {
            "i_q0_pu": current_q,
            "rms_distance_pu": rms,
        }
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artwork", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "verification/fig5_ieee_comparison.json"
    )
    args = parser.parse_args()

    artwork_hash = sha256(args.artwork.read_bytes()).hexdigest()
    if artwork_hash != ARTWORK_SHA256:
        parser.error("The artwork does not match the pinned IEEE Xplore Fig. 5 GIF")
    with Image.open(args.artwork) as artwork:
        if artwork.size != ARTWORK_SIZE:
            parser.error("Unexpected artwork dimensions")
        red, green, blue_channel = np.asarray(artwork.convert("RGB"), dtype=int).transpose(
            2, 0, 1
        )
    blue = (blue_channel > 160) & (blue_channel - red > 40) & (blue_channel - green > 40)
    strokes = {loop: calibrated_strokes(blue, loop) for loop in REAL_TICKS}

    col_min, col_max = SOLID_CROSSING_COLUMNS
    col_ids = np.flatnonzero(blue[SOLID_CROSSING_ROW, col_min : col_max + 1]) + col_min
    x_zero, x_minus_half = REAL_TICKS["gd"]
    crossing = float((col_ids.mean() - x_zero) * 0.5 / (x_zero - x_minus_half))

    config = json.loads((ROOT / "configs/protocol.json").read_text())
    variants = json.loads((ROOT / "configs/fig5_variants.json").read_text())
    if tuple(config["fig5"]["active"]) != UPPER_LABEL_VISUAL_READING:
        parser.error("The printed-condition parameters disagree with the artwork label")
    comparisons = compare_models(config, variants, strokes)
    report = {
        "doi": config["doi"],
        "figures_url": FIGURES_URL,
        "artwork_url": ARTWORK_URL,
        "artwork_sha256": artwork_hash,
        "artwork_size_px": list(ARTWORK_SIZE),
        "upper_label_visual_reading_pu": UPPER_LABEL_VISUAL_READING,
        "real_zero_and_minus_half_px": REAL_TICKS,
        "imaginary_zero_and_minus_point_two_px": IMAGINARY_TICKS,
        "interior_blue_pixel_count": {loop: len(xy) for loop, xy in strokes.items()},
        "upper_gd_scr10_solid_crossing": {
            "row_px": SOLID_CROSSING_ROW,
            "blue_columns_px": col_ids.tolist(),
            "real_pu": crossing,
            "gain_margin_estimate": -1 / crossing,
        },
        "upper_panel_comparisons": comparisons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
