import pandas as pd
import seaborn as sns
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import colors
import matplotlib.collections
from typing import Any
import math
import json
import matplotlib
import sys

sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils import dref_dataframe, dref_dataframe_multi


DRIVER_MAP = {
    "virtio-balloon": "virtio-balloon",
    "virtio-balloon-huge": "virtio-balloon-huge",
    "virtio-mem+VFIO": "virtio-mem-vfio",
    "virtio-mem": "virtio-mem",
    "HyperAlloc+VFIO": "llfree-vfio",
    "HyperAlloc": "llfree",
    "Baseline": "baseline",
}


def init():
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42

    sns.set_style("whitegrid")
    # sns.set_context("poster", font_scale=0.75)
    sns.set_context("poster", font_scale=1.3)
    sns.set_palette("colorblind6")


def calc_stats(
    data: pd.DataFrame, cores: list[int], data_col: str, drivers: list[str]
) -> pd.DataFrame:
    rows = []
    for c in cores:
        core_data = data.loc[data["Cores"] == c]
        for d in drivers:
            driver_data = core_data.loc[core_data["Driver"] == d]
            std = driver_data[data_col].std()
            mean = driver_data[data_col].mean()
            rows.append({"Cores": c, "Driver": d, "Mean": mean, "Std": std})

    return pd.DataFrame(rows)


def render_plt(fig, name: str, path: Path = Path("stream")):
    fig.savefig(path / f"{name}.pdf", bbox_inches="tight", dpi=100)


def load_stream_csv(p: Path, cores: int, driver: str) -> pd.DataFrame:
    folder = DRIVER_MAP[driver]
    data = pd.read_csv(p / f"{folder}-stream" / str(cores) / "Copy.csv")
    times = data["IterTime"]
    t_sum = 0.0
    for i in range(0, len(times)):
        t_sum += times[i]
        times[i] = t_sum

    data["Bandwidth"] /= 1000.0
    return data.assign(Cores=cores, Driver=driver)


def load_streams(
    p: Path, drivers: list[str], max_t: float = 140.0
) -> tuple[pd.DataFrame, dict[str, Any]]:
    meta = json.load((p / f"{DRIVER_MAP['Baseline']}-stream" / "meta.json").open())
    cores = meta["args"]["bench_threads"]
    frames = []
    for c in cores:
        base = load_stream_csv(p, c, "virtio-balloon")
        retained_samples = next(
            (i for i, t in enumerate(base["IterTime"]) if t >= max_t),
            len(base["IterTime"]),
        )
        frames.append(base.head(retained_samples))
        for d in drivers:
            frames.append(load_stream_csv(p, c, d).head(retained_samples))

    return pd.concat(frames), meta


def visualize_stream(
    drivers: list[str],
    stream: pd.DataFrame,
    stream_meta: dict[str, Any],
    save_as: str | None = None,
    out: Path = Path("out"),
) -> tuple[sns.FacetGrid, pd.DataFrame]:
    col_ord = stream_meta["args"]["bench_threads"]
    order = drivers

    p = sns.FacetGrid(
        stream, col="Cores", col_order=col_ord, sharey=False, height=6.5, aspect=1
    )
    p.map_dataframe(
        sns.scatterplot,
        x="IterTime",
        y="Bandwidth",
        hue="Driver",
        hue_order=order,
        s=30.0,
        linewidth=0,
    )
    p.set_titles(col_template="{col_name} thread(s)")
    p.add_legend(
        frameon=True,
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.293, 0.04),
        markerscale=3,
    )

    p.set(ylabel="Bandwith [GB/s]")
    p.set(xlabel="Runtime [s]")
    p.set(ylim=(0, None))
    p.set(xlim=(0, 140))
    for ax in p.axes_dict.values():
        ax.axvline(
            stream_meta["args"]["post_delay"], color="red", alpha=0.4, zorder=0.9
        )
        ax.text(
            stream_meta["args"]["post_delay"] + 2,
            ax.viewLim.max[1] * 0.02,
            "Shrink",
            color="red",
            alpha=0.6,
            size=24,
        )
        ax.axvline(
            stream_meta["args"]["deflate_delay"], color="blue", alpha=0.4, zorder=0.9
        )
        ax.text(
            stream_meta["args"]["deflate_delay"] + 2,
            ax.viewLim.max[1] * 0.02,
            "Grow",
            color="blue",
            alpha=0.6,
            size=24,
        )

    for key, ax in p.axes_dict.items():
        if key != 1:
            ax.set_ylabel("")
        for c in ax.get_children():
            if isinstance(c, matplotlib.collections.PathCollection):
                c.set_rasterized(True)

    if save_as:
        p.savefig(out / f"{save_as}.pdf", bbox_inches="tight", dpi=100)
        p.savefig(out / f"{save_as}.svg", bbox_inches="tight", dpi=100)
        dref_dataframe(save_as, out, ["Driver", "Cores", "IterTime"], stream)

    return p, stream


# ------------------------------------------------------------------------------
# FTQ
# ------------------------------------------------------------------------------


def sum_ftqs_batched(path: Path, cores: int, driver: str, samples: int) -> pd.DataFrame:
    folder = DRIVER_MAP[driver]
    p = path / f"{folder}-ftq" / str(cores)
    out = pd.DataFrame()
    counts = list(map(lambda s: int(s), (p / "counts.dat").read_text().splitlines()))
    times = list(map(lambda s: int(s), (p / "times.dat").read_text().splitlines()))
    for i in range(0, cores):
        data = pd.DataFrame()
        data["Times"] = times[(samples*i):(samples*(i+1))]
        data["Counts"] = counts[(samples*i):(samples*(i+1))]
        if i == 0:
            out = data
        else:
            out["Counts"] += data["Counts"]
    start_cycle = out["Times"][0]
    out["Times"] -= start_cycle
    return out.tail(-1).assign(Cores=cores, Driver=driver)


def load_ftqs(p: Path, drivers: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    meta = json.load((p / f"{DRIVER_MAP['Baseline']}-ftq" / "meta.json").open())
    cores = meta["args"]["bench_threads"]
    frames = []
    for c in cores:
        for d in drivers:
            frames.append(sum_ftqs_batched(p, c, d, 1096))

    return pd.concat(frames), meta


def visualize_ftq(
    drivers: list[str],
    ftq: pd.DataFrame,
    ftq_meta: dict[str, Any],
    save_as: str | None = None,
    out: Path = Path("out"),
):
    col_ord = ftq_meta["args"]["bench_threads"]
    order = drivers

    data = ftq.copy()
    data["Counts"] /= 1e6
    p = sns.FacetGrid(data, col="Cores", col_order=col_ord, sharey=False, height=6.5, aspect=1)
    p.map_dataframe(sns.scatterplot, x="Times", y="Counts", hue="Driver",
                    hue_order=order, s=30.0, linewidth=0)
    p.set_titles(col_template="{col_name} thread(s)")
    p.add_legend(frameon=True, ncol=3, loc="upper center", bbox_to_anchor=(0.293, 0.04), markerscale=3)
    p.set(ylabel="Work [e6]")
    p.set(xlabel="Cycles")
    p.set(ylim=(0, None))
    p.set(xlim=(0, ftq["Times"].max()))
    for ax in p.axes_dict.values():
        cpu_freq = 2.1e9
        post_delay = ftq_meta["args"]["post_delay"] * cpu_freq
        ax.axvline(post_delay, color="red", alpha=0.4, zorder=0.9)
        ax.text(post_delay + 2 * cpu_freq, ax.viewLim.max[1] * 0.02,
                "Shrink", color="red", alpha=0.6, size=24)
        inflate_delay = ftq_meta["args"]["deflate_delay"] * cpu_freq
        ax.axvline(inflate_delay, color="blue", alpha=0.4, zorder=0.9)
        ax.text(inflate_delay + 2 * cpu_freq, ax.viewLim.max[1] * 0.02,
                "Grow", color="blue", alpha=0.6, size=24)

    for key, ax in p.axes_dict.items():
        if key != 1: ax.set_ylabel("")
        for c in ax.get_children():
            if isinstance(c, matplotlib.collections.PathCollection):
                c.set_rasterized(True)

    if save_as:
        p.savefig(out / f"{save_as}.pdf", bbox_inches="tight", dpi=100)
        p.savefig(out / f"{save_as}.svg", bbox_inches="tight", dpi=100)
        dref_dataframe(save_as, out, ["Driver", "Cores", "Times"], ftq)
