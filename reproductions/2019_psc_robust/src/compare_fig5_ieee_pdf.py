"""Compare the IEEE version-of-record Fig. 5 vectors with its web artwork."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from compare_fig5_ieee import (
    ARTWORK_URL,
    IMAGINARY_TICKS,
    REAL_TICKS,
    calibrated_strokes,
    read_blue_artwork,
)
from reproduce import ROOT


DOI = "10.1109/TIE.2018.2874584"
PRINTED_PAGE = 5814
# Grid-line positions in the version-of-record PDF, measured in PDF points.
PDF_REAL_TICKS = {"gp": (149.92801, 122.14001), "gd": (288.71201, 260.92401)}
PDF_IMAGINARY_TICKS = {
    "upper": (117.79597, 128.91197),
    "lower": (234.06300, 245.18001),
}
ARTWORK_IMAGINARY_TICKS = {"upper": IMAGINARY_TICKS, "lower": (560.0, 597.5)}
SCR_BY_DASH_COUNT = {0: 10, 2: 3, 4: 1}
VECTOR_SAMPLE_SPACING_PU = 0.0005


def read_pdf_vectors(pdf):
    """Read normalized line segments from the blue paths on printed p. 5814."""
    import pymupdf

    with pymupdf.open(pdf) as document:
        if not len(document) or DOI.lower() not in document[0].get_text().lower():
            raise ValueError("The first page does not identify the expected IEEE article")
        page_count = len(document)
        for page_index, page in enumerate(document, start=1):
            lines = page.get_text().splitlines()
            if lines and lines[0].strip() == str(PRINTED_PAGE):
                if "Fig. 5." not in lines:
                    raise ValueError("Fig. 5 is missing from the expected journal page")
                paths = page.get_drawings()
                break
        else:
            raise ValueError(f"Printed page {PRINTED_PAGE} was not found")

    traces = {}
    for path in paths:
        bounds = path["rect"]
        if path["color"] != (0.0, 0.0, 1.0) or bounds.x1 > 291 or bounds.y1 > 278:
            continue
        row = "upper" if bounds.y0 < 175 else "lower"
        loop = "gp" if bounds.x1 < 175 else "gd"
        dash_count = len(path["dashes"].split("]", 1)[0][1:].split())
        scr = SCR_BY_DASH_COUNT[dash_count]
        x_zero, x_minus_half = PDF_REAL_TICKS[loop]
        y_zero, y_minus_point_two = PDF_IMAGINARY_TICKS[row]

        def calibrate(point):
            real = (point.x - x_zero) * 0.5 / (x_zero - x_minus_half)
            imag = (y_zero - point.y) * 0.2 / (y_minus_point_two - y_zero)
            return complex(real, imag)

        segments = traces.setdefault((row, loop, scr), [])
        for segment in path["items"]:
            if segment[0] != "l":
                raise ValueError("Expected line segments in the Fig. 5 vector paths")
            _, start, end = segment
            segments.append((calibrate(start), calibrate(end)))
    if len(traces) != 12:
        raise ValueError(f"Expected 12 vector curves, found {len(traces)}")
    return page_index, page_count, traces


def compare_panel(strokes, curves):
    samples = np.concatenate(
        [
            np.linspace(
                start, end, 1 + int(np.ceil(abs(end - start) / VECTOR_SAMPLE_SPACING_PU))
            )
            for segments in curves
            for start, end in segments
        ]
    )
    tree = cKDTree(np.column_stack((samples.real, samples.imag)))
    distances, _ = tree.query(strokes)
    return {
        "interior_artwork_pixels": len(strokes),
        "rms_distance_pu": float(np.sqrt(np.mean(distances**2))),
        "max_distance_pu": float(distances.max()),
    }


def real_crossing(segments):
    crossings = []
    for start, end in segments:
        if start.imag * end.imag < 0:
            crossing = (start - (end - start) * start.imag / (end - start).imag).real
            if crossing < -0.03:
                crossings.append(crossing)
    if len(crossings) != 1:
        raise ValueError("Expected one nonzero negative-real-axis crossing for SCR=10")
    return crossings[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--artwork", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "verification/fig5_ieee_pdf_comparison.json"
    )
    args = parser.parse_args()

    try:
        blue, artwork_hash = read_blue_artwork(args.artwork)
    except ValueError as error:
        parser.error(str(error))
    page_index, page_count, traces = read_pdf_vectors(args.pdf)
    panels = {}
    for row, imaginary_ticks in ARTWORK_IMAGINARY_TICKS.items():
        for loop in REAL_TICKS:
            strokes = calibrated_strokes(blue, loop, imaginary_ticks)
            curves = [traces[row, loop, scr] for scr in (1, 3, 10)]
            panels[f"{row}_{loop}"] = compare_panel(strokes, curves)

    crossing = real_crossing(traces["upper", "gd", 10])
    report = {
        "doi": DOI,
        "pdf_sha256": sha256(args.pdf.read_bytes()).hexdigest(),
        "pdf_page_count": page_count,
        "pdf_page_one_based": page_index,
        "printed_page": PRINTED_PAGE,
        "artwork_url": ARTWORK_URL,
        "artwork_sha256": artwork_hash,
        "upper_row_label_visual_reading_pu": [0.95, 0.2],
        "pdf_trace_count": len(traces),
        "pdf_real_zero_and_minus_half_pt": PDF_REAL_TICKS,
        "pdf_imaginary_zero_and_minus_point_two_pt": PDF_IMAGINARY_TICKS,
        "artwork_imaginary_zero_and_minus_point_two_px": ARTWORK_IMAGINARY_TICKS,
        "vector_max_sample_spacing_pu": VECTOR_SAMPLE_SPACING_PU,
        "artwork_pixel_to_pdf_vector_by_panel": panels,
        "upper_gd_scr10_pdf_crossing_pu": crossing,
        "upper_gd_scr10_pdf_gain_margin": -1 / crossing,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
