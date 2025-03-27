import warnings

warnings.filterwarnings("ignore")

import math
import pandas as pd
import seaborn as sns
from pathlib import Path
from matplotlib import patheffects
import json
import matplotlib
import sys

sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils import dref_dataframe

def init():
    sns.set_style("whitegrid")
    sns.set_context("poster", font_scale=0.75)
    sns.set_palette("colorblind6")
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["ps.fonttype"] = 42


def parse_logs(path: Path) -> pd.DataFrame:
    try:
        meta = json.load((path / f"meta.json").open())
        data = pd.read_csv(path / "out.csv")
        data["iter"] = data.index
        data["shrink"] = (data["shrink"] / 1e9) / meta["args"]["mem"]
        data["grow"] = (data["grow"] / 1e9) / meta["args"]["mem"]
        if "touch" in data.columns:
            data["touch"] = (data["touch"] / 1e9) / (meta["args"]["mem"] - 1)
        if "touch" in data.columns:
            data["touch2"] = (data["touch2"] / 1e9) / (meta["args"]["mem"] - 1)
    except Exception as e:
        print(f"Error parsing {path}: {e}")
        data = pd.DataFrame({
            "mode": [path.stem],
            "iter": [1],
            "shrink": [math.nan],
            "grow": [math.nan],
            "touch": [math.nan],
            "touch2": [math.nan],
        })

    match path.stem:
        case n if "base-manual" in n:
            mode = "virtio-balloon"
        case n if "huge-manual" in n:
            mode = "virtio-balloon-huge"
        case n if "virtio-mem" in n:
            mode = "virtio-mem+VFIO" if "vfio" in n else "virtio-mem"
        case n if "llfree-manual-vfio" in n:
            mode = "HyperAlloc+VFIO"
        case n if "llfree-manual" in n:
            mode = "HyperAlloc"
        case m:
            mode = m
    data["mode"] = mode
    return pd.DataFrame(data)


def visualize(
    touched: list[Path],
    untouched: list[Path],
    save_as: str | None = None,
    out: Path = Path("out"),
    titles: bool = True,
    height: float = 3,
    aspect: float = 3,
    hide: list[str] = []
):
    # Touched
    data = pd.concat([parse_logs(p) for p in touched])
    if data["iter"].max() > 0:
        data = data[data["iter"] > 0]
    data["install"] = data["touch"] + data["grow"]
    max_access = (1 / data["touch2"]).max()

    pgd = data.melt(id_vars=["mode", "iter"], value_vars=["shrink", "grow", "touch", "install"],
                    var_name="op", value_name="time")
    pgd["time"] = 1 / pgd["time"]

    # Untouched
    if untouched:
        data = pd.concat([parse_logs(p) for p in untouched])
        if data["iter"].max() > 0:
            data = data[data["iter"] > 0]

        pgd1 = data.melt(id_vars=["mode", "iter"], value_vars=["shrink", "grow"],
                        var_name="op", value_name="time")
        pgd1["time"] = 1 / pgd1["time"]
        pgd1 = pgd1[pgd1["op"] == "shrink"]
        pgd1["op"] = "Reclaim Untouched"

        pgd = pd.concat([pgd, pgd1])

    # Both
    pgd.loc[pgd["op"] == "shrink", "op"] = "Reclaim"
    pgd.loc[pgd["op"] == "grow", "op"] = "Return"
    pgd.loc[pgd["op"] == "install", "op"] = "Return + Install"
    pgd.loc[pgd["op"] == "touch", "op"] = "Install"
    print(pgd["op"].unique())

    print(pgd["time"].max())
    order = ["", " ", "virtio-balloon","virtio-balloon-huge","virtio-mem","virtio-mem+VFIO","HyperAlloc","HyperAlloc+VFIO"]
    order = [o for o in order if o in pgd["mode"].unique()]
    row_order = ["Reclaim", "Reclaim Untouched", "Return", "Return + Install"]
    row_order = [o for o in row_order if o in pgd["op"].unique()]

    p = sns.FacetGrid(pgd, row="op", margin_titles=titles,
                    row_order=row_order, aspect=aspect, height=height, sharex=False)

    p.map_dataframe(sns.barplot, y="mode", hue="mode", hue_order=order,
                    palette="colorblind6", x="time", dodge=False)
    p.set(ylabel=None)
    if height == 3:
        p.figure.subplots_adjust(hspace=1)

    def mem_fmt(x: float) -> str:
        x *= 1024**3
        sizes = ["TiB", "GiB", "MiB", "KiB"]
        for i, suffix in enumerate(sizes):
            mul = 1024 ** (len(sizes) - i)
            if x > mul: return f"{x/mul:.1f} {suffix}/s"
        return f"{x:.2} B/s"

    if titles:
        p.set_titles(row_template="{row_name}", xytext=(1.08, 0.5))
    else:
        p.set_titles(row_template="")

    for key, ax in p.axes_dict.items():
        if key != "Return + Install":
            ax.set(xlim=(1e-1, 1e5))
            ax.set_xscale("log", base=10)
            ax.set(xlabel="Speed [GiB/s] - logarithmic")
        else:
            xmax = pgd[pgd["op"] == "Return + Install"]["time"].max() * 1.3
            ax.set(xlim=(0, xmax))
            ax.set(xlabel="Speed [GiB/s] - linear")

        ax.grid(True, which="minor", linewidth=1)
        for c in ax.containers:
            ax.bar_label(c, fmt=mem_fmt, fontsize=12, padding=10,
                        path_effects=[patheffects.withStroke(linewidth=5, foreground='white')])

        if key in hide:
            ax.clear()
            ax.set_axis_off()


    if save_as:
        p.figure.savefig(out / f"{save_as}.pdf", bbox_inches="tight")
        p.figure.savefig(out / f"{save_as}.svg", bbox_inches="tight")
        dref_dataframe(save_as, out, ["mode", "op"], pgd[["mode", "op", "time"]])
        (out / f"{save_as}.dref").open("a").write(f"\\drefset{{{save_as}/max_access}}{{{max_access}}}")
