"""Plot the Type-II clearing cases and mark the ideal model's scope boundary."""

import argparse
import json
from pathlib import Path

import numpy as np

from reproduce import ROOT, plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "figures/type_ii_clearing_comparison.png"
    )
    args = parser.parse_args()

    config = json.loads((ROOT / "configs/protocol.json").read_text())
    manifest = json.loads((args.results / "run_manifest.json").read_text())
    schedule = config["schedule"]
    onset = schedule["disturbance_s"]
    threshold = config["base"]["current_limit_pu"]
    cases = manifest["branches"]["table_pu"]["cases"]
    colors = {"early": "#136286", "late": "#af4e25"}

    fig, (angle_axis, current_axis) = plt.subplots(
        2, 1, sharex=True, figsize=(9.5, 6.5), layout="constrained"
    )
    fig.suptitle("Type-II fault clearing · Table I per-unit reactances")
    for case in ("early", "late"):
        metadata = cases[f"type_ii_{case}"]
        with np.load(args.results / metadata["npz"], allow_pickle=False) as data:
            time = data["time_s"] - onset
            angle = np.degrees(data["angle_rad"])
            current = data["current_pu"]
        duration = schedule[f"{case}_fault_duration_s"]
        label = f"Cleared at {duration:g} s"
        color = colors[case]
        crossing = metadata["first_current_limit_crossing_s"]
        boundary = len(time) if crossing is None else int(np.searchsorted(time, crossing - onset))
        for axis, values in ((angle_axis, angle), (current_axis, current)):
            axis.plot(time[:boundary], values[:boundary], lw=2, color=color, label=label)
            if crossing is not None:
                axis.plot(
                    time[boundary - 1 :],
                    values[boundary - 1 :],
                    "--",
                    lw=1.8,
                    color=color,
                    label="Late case · ideal-model continuation",
                )
        if crossing is not None:
            peak = int(np.argmax(current))
            current_axis.scatter(time[[boundary, peak]], current[[boundary, peak]], color=color, zorder=3)
            current_axis.annotate(
                f"{current[boundary]:.3f} pu at clearing",
                (time[boundary], current[boundary]),
                xytext=(-16, 28),
                textcoords="offset points",
                ha="right",
                arrowprops={"arrowstyle": "-", "color": color},
            )
            current_axis.annotate(
                f"{current[peak]:.3f} pu peak",
                (time[peak], current[peak]),
                xytext=(28, 9),
                textcoords="offset points",
                arrowprops={"arrowstyle": "-", "color": color},
            )

    for axis in (angle_axis, current_axis):
        for case in ("early", "late"):
            axis.axvline(schedule[f"{case}_fault_duration_s"], color=colors[case], alpha=0.24)
        axis.grid(alpha=0.25)
    current_axis.axhline(threshold, linestyle=":", color="#323943", lw=1.3)
    current_axis.text(
        schedule["stop_s"] - onset - 0.08, threshold + 0.035,
        f"{threshold:g} pu reported threshold", ha="right", va="bottom",
    )
    angle_axis.legend(loc="center right", frameon=False)
    angle_axis.set_ylabel("Unwrapped angle (°)")
    current_axis.set_ylabel("PCC current magnitude (pu)")
    current_axis.set_xlabel("Time since fault inception (s)")
    current_axis.set_xlim(-0.12, schedule["stop_s"] - onset)
    current_axis.set_ylim(0, 2.33)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
