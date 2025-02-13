from dataclasses import dataclass
import warnings

from matplotlib.axes import Axes

warnings.filterwarnings("ignore")

import pandas as pd
import seaborn as sns
from pathlib import Path
import numpy as np
import json
import matplotlib
from matplotlib import pyplot as plt
from scipy import integrate
import sys

sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils import dump_dref

matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42

sns.set_style("whitegrid")
sns.set_context("poster", font_scale=0.75)
sns.set_palette("colorblind6")


root = Path(".")


@dataclass
class BTimes:
    start: list[float]
    build: list[float]
    clean: list[float]
    cpu: dict[str, float]


def load_mode(mode: str, path: Path, vm: int, i=0) -> tuple[pd.DataFrame, BTimes]:
    basedir = root / path / f"vm_{vm}"
    data = pd.read_csv(basedir / f"out_{i}.csv", dtype=np.float64).dropna()
    data["time"] /= 60
    data = data.rename(columns={"rss": f"VM {vm}"})
    data[f"VM {vm}"] /= 1024**3
    data = data[["time", f"VM {vm}"]]
    data.insert(0, "mode", mode)
    data.set_index(["mode", "time"])

    raw: dict = json.load((basedir / f"times_{i}.json").open())
    times = BTimes(
        [v / 60 for v in raw["start"]],
        [v / 60 for v in raw["build"]],
        [v / 60 for v in raw["clean"]],
        raw["cpu"],
    )
    return data, times


def load_data(
    max_mem: int, modes: dict[str, Path], vms: int
) -> tuple[pd.DataFrame, dict[str, list[BTimes]]]:
    datas: list[pd.DataFrame] = []
    times: dict[str, list[BTimes]] = {}
    for mode, path in modes.items():
        inner = []
        times[mode] = []
        for vm in range(vms):
            data, time = load_mode(mode, path, vm)
            inner.append(data)
            times[mode].append(time)
        data = inner[0]
        for d in inner[1:]:
            data = pd.merge_ordered(data, d, how="outer", fill_method="ffill")
        datas.append(data)

    data = pd.concat(datas, ignore_index=True)
    # merge and interpolate data

    return data, times


def y_at(data: pd.DataFrame, x: float, measurement="VM memory"):
    return data[data["measurement"] == measurement][(data["time"] - x).abs() < 2 / 60][
        "bytes"
    ].max()


def calc_gib_min(data: pd.DataFrame, start: float, end: float) -> float:
    build_d = data[
        (start <= data["time"])
        & (data["time"] <= end)
        & (data["measurement"] == "VM memory")
    ]
    return integrate.trapezoid(build_d["bytes"], x=build_d["time"]) / 1024**3


def relplot(
    max_mem: int,
    data: pd.DataFrame,
    times: dict[str, list[BTimes]],
    col_wrap=10,
    run="build",
) -> tuple[sns.FacetGrid, dict[str, float]]:

    modes = data["mode"].unique()
    runs: dict[str, list[str]] = {}
    for mode in modes:
        for col in data.columns[2:]:
            runs.setdefault(mode, []).append(col)
    print(runs)
    vms = list(runs.values())[0]

    grid = sns.FacetGrid(data, col="mode", height=5, aspect=0.8, col_wrap=col_wrap)

    def draw_area(data: pd.DataFrame, **kwargs):
        plot_data = data.drop(columns=["mode"])
        kwargs.pop("color")
        ax: Axes = plot_data.plot.area(
            x="time", stacked=True, legend=True, ax=plt.gca(), **kwargs
        )
        total_gib = data[vms].sum(axis=1)
        gib_max = total_gib.max()
        gib_min = integrate.trapezoid(total_gib, x=data["time"])
        ax.set_xlim(0, None)
        ax.set_ylim(0, (max_mem * len(vms)) / 1024**3)
        ax.annotate(f"{gib_min:.0f} GiB*min\nMax: {gib_max:.1f} GiB", xy=(0.5, 0.05), xycoords='axes fraction',
               ha='center', bbox=dict(facecolor='white', alpha=0.5, edgecolor='black'))

    grid.map_dataframe(draw_area)
    grid.set_titles("{col_name}")
    grid.set(ylabel="Memory consumption [GiB]")
    grid.set(xlabel="Time [min]")

    h = list(grid.axes[0].get_legend_handles_labels()[0])
    # grid.add_legend(dict(zip(vms, h)), loc="upper center", bbox_to_anchor=(0.14, 0.04), ncol=7, frameon=True)
    grid.add_legend(
        dict(zip(vms, h)),
        loc="upper center",
        bbox_to_anchor=(0.278, 0.9),
        ncol=1,
        frameon=True,
    )

    if False:
        colors = sns.color_palette("colorblind6")
        for mode, mt in times.items():
            for i, time in enumerate(mt):
                for start, end in zip(time.start, time.build):
                    # grid.axes_dict[mode].axvspan(start, end, color=colors[i], alpha=0.3)
                    grid.axes_dict[mode].axvline(
                        start, color=colors[i], linestyle=":", alpha=0.5
                    )
                    grid.axes_dict[mode].axvline(
                        end, color=colors[i], linestyle="--", alpha=0.5
                    )

    extra_keys = {}
    baseline = None
    for mode, vms in runs.items():
        mode_d = data[data["mode"] == mode]
        total_gib = mode_d[vms].sum(axis=1)

        gib_min = integrate.trapezoid(total_gib, x=mode_d["time"])
        gib_max = total_gib.max()
        vm_gib_max = mode_d[vms].max().max()
        extra_keys[f"multivm/{mode}/gib_min"] = gib_min
        extra_keys[f"multivm/{mode}/gib_max"] = gib_max
        extra_keys[f"multivm/{mode}/vm_gib_max"] = vm_gib_max
        if baseline is None:
            baseline = (gib_min, gib_max)

        print(
            f"{mode}: {gib_min:.2f} GiB*min",
            f"({(gib_min - baseline[0]) / baseline[0]:.2%})",
        )
        print(
            f"  max: {gib_max:.2f} GiB",
            f"({(gib_max - baseline[1]) / baseline[1]:.2%})",
        )
        print(f"  VM max: {vm_gib_max:.2f} GiB")

    return grid, extra_keys


def visualize(
    modes: dict[str, Path],
    save_as: str | None = None,
    col_wrap=10,
    run="build",
    out: Path = Path("out"),
) -> sns.FacetGrid:
    meta = json.load((list(modes.values())[0] / "meta.json").open())
    max_mem = meta["args"]["mem"] * 1024**3
    data, times = load_data(max_mem, modes, meta["args"]["vms"])
    p, extra_keys = relplot(max_mem, data, times, col_wrap, run=run)
    if save_as:
        p.savefig(out / f"{save_as}.pdf")
        p.savefig(out / f"{save_as}.svg")
        # dref_dataframe(save_as, out, ["mode", "measurement", "time"], data)
        with (out / f"{save_as}_extra.dref").open("w+") as f:
            dump_dref(f, save_as, extra_keys)
    return p
