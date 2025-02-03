from dataclasses import dataclass
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
import seaborn as sns
from pathlib import Path
import numpy as np
import json
from matplotlib import patheffects
from scripts.utils import dref_dataframe, dump_dref
import matplotlib
from scipy import integrate


def init():
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42
    sns.set_style("whitegrid")
    sns.set_context("poster", font_scale=0.75)
    sns.set_palette("colorblind6")


@dataclass
class BTimes:
    build: list[float]
    delay: list[float]
    clean: float | None
    drop: float
    cpu: dict[str, float]


def parse_frag(file: Path) -> pd.DataFrame:
    raw = file.read_text()
    data = ""
    for line in raw.splitlines():
        data += line + ((len(line) + 31) // 32 * 32 - len(line)) * "0"
    huge_pages = len(data)
    out = np.zeros(huge_pages)
    for i, char in enumerate(data):
        level = int(char)
        assert 0 <= level <= 9
        out[i] = float(level)
    return pd.DataFrame(out)


def load_mode(max_mem: int, mode: str, path: Path, i=0) -> tuple[pd.DataFrame, BTimes]:
    data = pd.read_csv(path / f"out_{i}.csv", dtype=np.float64).dropna()
    data["mode"] = mode
    if "time" not in data.columns:
        data["time"] = data.index
    data["time"] /= 60  # seconds to minutes
    if "total" not in data.columns:
        data["total"] = max_mem
    data["small"] = data["total"] - data["small"] * 2**12
    data["huge"] = data["total"] - data["huge"] * 2 ** (12 + 9)
    data["VM memory"] = data["rss"]
    del data["rss"]

    data = data.melt(
        id_vars=["mode", "time"],
        var_name="measurement",
        value_name="bytes",
        value_vars=["VM memory", "small", "huge", "cached"],
    )

    raw: dict = json.load((path / f"times_{i}.json").open())
    times = BTimes(
        [v / 60 for v in x] if isinstance(x := raw["build"], list) else [x],
        [v / 60 for v in y] if isinstance(y := raw["delay"], list) else [y],
        raw["clean"] / 60 if "clean" in raw and raw["clean"] is not None else None,
        (raw["drop"] if "drop" in raw else raw["shrink"]) / 60,
        raw["cpu"],
    )
    return data, times


def load_data(
    max_mem: int, modes: dict[str, Path]
) -> tuple[pd.DataFrame, list[BTimes]]:
    datas: list[pd.DataFrame] = []
    times: list[BTimes] = []
    for mode, path in modes.items():
        data, time = load_mode(max_mem, mode, path)
        datas.append(data)
        times.append(time)
    data = pd.concat(datas, ignore_index=True)
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
    max_mem: int, data: pd.DataFrame, times: list[BTimes], col_wrap=10, run="build"
) -> tuple[sns.FacetGrid, dict[str, float]]:
    col_wrap = min(col_wrap, len(data["mode"].unique()))
    p = sns.relplot(
        data=data,
        kind="line",
        x="time",
        y="bytes",
        col="mode",
        col_wrap=col_wrap,
        hue="measurement",
        height=5.5,
        legend=False,
    )
    p.set_titles("{col_name}")
    p.set(ylabel="Memory consumption [GiB]")
    p.set(xlabel="Time [min]")
    p.set(xlim=(0, None))
    p.set(ylim=(0, max_mem * 1.1))
    p.set(
        yticks=[x for x in range(0, max_mem + 1, 2 * 1024**3)],
        yticklabels=[str(x // 1024**3) for x in range(0, max_mem + 1, 2 * 1024**3)],
    )

    modes = data["mode"].unique()
    extra_keys = {}

    for ax in p.axes:
        ax.get_lines()[0].set(zorder=10, linestyle=(0, (1, 1)))

    h = list(p.axes[0].get_lines())
    l = list(data["measurement"].unique())
    p.add_legend(
        dict(zip(l, h)),
        loc="upper center",
        bbox_to_anchor=(0.3, 0.04),
        ncol=7,
        frameon=True,
    )

    p.refline(y=max_mem, color=sns.crayons["Gray"])
    for i, time in enumerate(times):
        axis = p.facet_axis(0, i)
        celld = data[data["mode"] == modes[i]]

        tstart = 0
        j = 0
        prefix = ""
        for tbuild, tdelay in zip(time.build, time.delay):
            if len(time.build) > 1:
                axis.axvspan(
                    xmin=tstart,
                    xmax=tbuild,
                    ymax=0.91,
                    edgecolor="black",
                    facecolor="whitesmoke",
                    zorder=-1,
                )

                b_mid = tstart + (tbuild - tstart) / 2
                axis.text(
                    b_mid,
                    max_mem * 1.02,
                    run,
                    horizontalalignment="center",
                    path_effects=[
                        patheffects.withStroke(linewidth=3, foreground="white")
                    ],
                )
            else:
                axis.axvline(x=tbuild, color="black", linewidth=3, zorder=1)

            gib_m = calc_gib_min(celld, tstart, tbuild)
            print(f"{modes[i]}: {gib_m:.2f} GiB*m, {tbuild - tstart:.2f} min")
            extra_keys[f"{modes[i]}/{j}/run/gib_m"] = gib_m
            extra_keys[f"{modes[i]}/{j}/run/time"] = tbuild - tstart

            gib = y_at(celld, tbuild + (tdelay - tbuild) / 2) / 1024**3
            prefix += f"delay {gib:.2f} GiB, "
            extra_keys[f"{modes[i]}/{j}/delay/gib"] = gib
            tstart = tdelay
            j += 1

        tdelay = time.delay[-1]
        if time.clean is not None:
            axis.annotate(
                "clean",
                (tdelay, y_at(celld, tdelay, "huge") + max_mem / 32),
                (tdelay, max_mem * 1.02),
                horizontalalignment="center",
                path_effects=[patheffects.withStroke(linewidth=3, foreground="white")],
                arrowprops={"facecolor": "black"},
                zorder=11,
            )
            tdelay = time.clean
            gib = y_at(celld, tdelay) / 1024**3
            prefix += f"clean {gib:.2f} GiB, "
            extra_keys[f"{modes[i]}/clean/gib"] = gib

        axis.annotate(
            "drop",
            (tdelay, y_at(celld, tdelay, "huge") + max_mem / 32),
            (tdelay, max_mem * 0.925),
            horizontalalignment="center",
            path_effects=[patheffects.withStroke(linewidth=3, foreground="white")],
            arrowprops={"facecolor": "black"},
            zorder=11,
        )
        gib = y_at(celld, time.drop) / 1024**3
        prefix += f"drop {gib:.2f} GiB, "
        extra_keys[f"{modes[i]}/drop/gib"] = gib

        gib_m = calc_gib_min(celld, 0, time.drop)
        prefix += f"{gib_m:.2f} GiB*m"
        extra_keys[f"{modes[i]}/gib_m"] = gib_m

        print(f"{modes[i]}: {prefix}")

    return p, extra_keys


def visualize(
    modes: dict[str, Path],
    save_as: str | None = None,
    col_wrap=10,
    run="build",
    out=Path("out"),
) -> sns.FacetGrid:
    meta = json.load((list(modes.values())[0] / "meta.json").open())
    max_mem = meta["args"]["mem"] * 1024**3
    data, times = load_data(max_mem, modes)
    p, extra_keys = relplot(max_mem, data, times, col_wrap, run=run)
    if save_as:
        p.savefig(out / f"{save_as}.pdf")
        p.savefig(out / f"{save_as}.svg")
        dref_dataframe(save_as, out, ["mode", "measurement", "time"], data)
        with (out / f"{save_as}_extra.dref").open("w+") as f:
            dump_dref(f, save_as, extra_keys)
    return p


def overview(
    paths: dict[str, tuple[str, Path]],
    save_as: str | None = None,
    out=Path("out"),
) -> tuple[sns.FacetGrid, pd.DataFrame]:
    meta = json.load((list(paths.values())[0][1] / "meta.json").open())

    raw = {
        "mode": [],
        "cat": [],
        "gib_m": [],
        "time": [],
        "time_user": [],
        "time_system": [],
        "time_total": [],
    }

    max_mem = meta["args"]["mem"] * 1024**3
    for name, (cat, path) in paths.items():
        for i in range(6):
            data, times = load_mode(max_mem, name, path, i)
            if name == "Buddy" or name == "LLFree":
                data.loc[data["measurement"] == "VM memory", "bytes"] = 16 * 1024**3

            raw["mode"].append(name)
            raw["cat"].append(cat)
            raw["time"].append(times.build[0])
            raw["time_user"].append(times.cpu["user"] / 60)
            raw["time_system"].append(times.cpu["system"] / 60)
            raw["time_total"].append(times.cpu["system"] / 60)
            raw["gib_m"].append(calc_gib_min(data, 0, times.build[0]))

    data = pd.DataFrame(data=raw)
    data = data.melt(
        id_vars=["mode", "cat"],
        value_vars=["gib_m", "time", "time_user", "time_system"],
        value_name="measurement",
    )

    cats = data["cat"].unique()
    height_ratios = [len(data[data["cat"] == cat]["mode"].unique()) for cat in cats]

    p = sns.FacetGrid(
        data,
        col="variable",
        row="cat",
        height=2,
        aspect=1.5,
        sharex="col",
        sharey="row",
        gridspec_kws={"height_ratios": height_ratios},
    )

    def plot(data, **kwargs):
        palette = sns.palettes.color_palette("colorblind", as_cmap=True)
        row = list(data["cat"])[0]
        if row == "virtio-balloon":
            kwargs["palette"] = "Greens_d"
        elif row == "baseline":
            kwargs["palette"] = palette
        else:
            kwargs["palette"] = palette[3:]
        sns.barplot(**kwargs, data=data)

    p = p.map_dataframe(plot, y="mode", x="measurement", orient="y", hue="mode")
    p.set_titles(template="", col_template="", row_template="")
    p.set_ylabels("")

    p.figure.subplots_adjust(hspace=0.2)

    for [row, col], ax in p.axes_dict.items():
        if col == "time":
            ax.set_xlabel("Runtime [min]")
        elif col.startswith("time"):
            ax.set_xlabel(f"CPU {col[5].upper()}{col[6:]} [min]")
        else:
            ax.set_xlabel("Footprint [GiB·min]")
        ax.set_xlim(0, data[data["variable"] == col]["measurement"].max() * 1.3)

        if col == "gib_m":
            if row == "baseline":
                ax.set_ylabel(row, rotation=0, labelpad=10, ha="right", va="center")
            else:
                ax.set_ylabel(row)

        for c in ax.containers:
            ax.bar_label(
                c,
                fmt=lambda x: f"{x:.1f}",
                fontsize=12,
                padding=10,
                path_effects=[patheffects.withStroke(linewidth=3, foreground="white")],
            )

        labels = ax.get_yticklabels()
        for l in labels:
            if l.get_text() == "o=9 d=2000 c=32":
                l.set(fontweight="bold")

    if save_as:
        p.savefig(out / f"{save_as}.pdf", bbox_inches="tight")
        dref_dataframe(save_as, out, ["cat", "mode", "variable"], data)

    return p, data
