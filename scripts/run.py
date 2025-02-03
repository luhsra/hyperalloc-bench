from argparse import ArgumentParser
import asyncio
from collections.abc import Callable, Coroutine
import json
from pathlib import Path
import shutil
import itertools

from compiling import compiling, plot as compiling_plot
from inflate import inflate
from multivm import multivm
from stream import stream


class Benchmark:
    def __init__(
        self,
        name: str,
        function: Callable[[list[str]], Coroutine],
        args: list[str],
        modes: dict[str, list[str]],
        long_modes: dict[str, list[str]],
        plot: Callable[["Benchmark", bool], None],
    ):
        self.name = name
        self.args = args
        self.modes = modes
        self.function = function
        self.plot = plot

    async def run(self, vfio: int | None, long: bool = False):
        root = Path("artifact-eval") / self.name
        shutil.rmtree(root, ignore_errors=True)

        print(f"Running {self.name} bench")
        for mode, extra_args in self.modes.items():
            args = self.args + extra_args + [f"--root {root}", "--no-timestamp"]
            if vfio is None and "{vfio}" in args:
                print(f"Skipping {mode} because vfio is not set")
                continue

            print("Running", mode)
            args = [str(vfio) if arg == "{vfio}" else arg for arg in args]
            await self.function(args)
            await asyncio.sleep(1)

        print(f"Plotting {self.name} bench")

        self.plot(self, long)

        print(f"Finished {self.name} bench")

    def root(self) -> Path:
        return Path("artifact-eval") / self.name


def compiling_plot_fn(bench: Benchmark, long: bool = False):
    root = bench.root()
    compiling_plot.init()
    compiling_plot.visualize(
        {
            "Buddy": root / "clang-base-manual",
            "LLFree": root / "clang-llfree-manual",
        },
        "clang-baseline",
        out=Path("artifact-eval"),
    )
    compiling_plot.visualize(
        {
            "virtio-balloon": root / "clang-base-auto",
            "HyperAlloc": root / "clang-llfree-auto",
        },
        "clang-auto",
        out=Path("artifact-eval"),
    )
    compiling_plot.visualize(
        {
            "virtio-mem+VFIO": root / "clang-virtio-mem-vfio",
            "HyperAlloc+VFIO": root / "clang-llfree-auto-vfio",
        },
        "clang-auto-vfio",
        out=Path("artifact-eval"),
    )

    long_runs = {}
    if long:
        long_runs = {
            "o=9 d=2000 c=32": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o9-d2000-c32"),
            ),
            "o=9 d=2000 c=512": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o9-d2000-c512"),
            ),
            "o=9 d=100 c=32": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o9-d100-c32"),
            ),
            "o=9 d=100 c=512": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o9-d100-c512"),
            ),
            "o=0 d=2000 c=32": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o0-d2000-c32"),
            ),
            "o=0 d=2000 c=512": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o0-d2000-c512"),
            ),
            "o=0 d=100 c=32": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o0-d100-c32"),
            ),
            "o=0 d=100 c=512": (
                "virtio-balloon",
                Path("latest/clang-base-auto-o0-d100-c512"),
            ),
        }

    compiling_plot.overview(
        {
            "Buddy": ("baseline", Path("latest/clang-base-manual")),
            "LLFree": ("baseline", Path("latest/clang-llfree-manual")),
            **long_runs,
            "virtio-mem": ("", Path("latest/clang-virtio-mem")),
            "virtio-mem+VFIO": ("", Path("latest/clang-virtio-mem-vfio")),
            "HyperAlloc": ("", Path("latest/clang-llfree-auto")),
            "HyperAlloc+VFIO": ("", Path("latest/clang-llfree-auto-vfio")),
        },
        "clang",
        out=Path("artifact-eval"),
    )


def inflate_plot_fn(bench: Benchmark, long: bool = False):
    pass


def multivm_plot_fn(bench: Benchmark, long: bool = False):
    pass


def stream_plot_fn(bench: Benchmark, long: bool = False):
    pass


def ftq_plot_fn(bench: Benchmark, long: bool = False):
    pass


BENCHMARKS = [
    Benchmark(
        "compiling",
        compiling.main,
        args=["--target clang", "-m16", "-c12", "--delay 200"],
        modes={
            "base-manual": [],
            "base-auto": [],
            "huge-auto": [],
            "llfree-manual": [],
            "llfree-auto": [],
            "llfree-auto": ["--suffix llfree-auto-vfio", "--vfio", "{vfio}"],
            "virtio-mem": [],
            "virtio-mem": ["--suffix virtio-mem-vfio", "--vfio", "{vfio}"],
        },
        long_modes={
            "base-auto": [
                f"--suffix clang-base-auto-o{o}-d{d}-c{c}",
                f"--fpr-order {o}",
                f"--fpr-delay {d}",
                f"--fpr-capacity {c}",
            ]
            for o, d, c in itertools.product([0, 9], [100, 2000], [32, 512])
        },
        plot=compiling_plot_fn,
    ),
    Benchmark(
        "inflate",
        inflate.main,
        args=["-m20", "-c12", "--shrink-target 2", "-i1"],
        modes={
            "base-manual": [],
            "huge-manual": [],
            "llfree-manual": [],
            "llfree-manual": ["--suffix llfree-auto-vfio", "--vfio", "{vfio}"],
            "virtio-mem": [],
            "virtio-mem": ["--suffix virtio-mem-vfio", "--vfio", "{vfio}"],
            # nofault
            "base-manual": ["--suffix base-manual-nofault", "--nofault"],
            "huge-manual": ["--suffix huge-manual-nofault", "--nofault"],
            "llfree-manual": ["--suffix llfree-manual-nofault", "--nofault"],
            "llfree-manual": [
                "--suffix",
                "llfree-manual-vfio-nofault",
                "--vfio",
                "{vfio}",
                "--nofault",
            ],
            "virtio-mem": ["--suffix virtio-mem-nofault", "--nofault"],
            "virtio-mem": [
                "--suffix",
                "virtio-mem-vfio-nofault",
                "--vfio",
                "{vfio}",
                "--nofault",
            ],
        },
        long_modes={},
        plot=inflate_plot_fn,
    ),
    Benchmark(
        "multivm",
        multivm.main,
        args=[
            "--target clang",
            "-m16",
            "-c8",
            "--delay 7200",
            "--repeat 3",
            "--vms 3",
        ],
        modes={
            "base-manual": [],
            "huge-manual": [],
            "llfree-manual": [],
            "base-manual": ["--suffix clang-base-manual-s", "--simultaneous"],
            "huge-manual": ["--suffix clang-base-manual-s", "--simultaneous"],
            "llfree-manual": ["--suffix clang-base-manual-s", "--simultaneous"],
        },
        long_modes={},
        plot=multivm_plot_fn,
    ),
    Benchmark(
        "stream",
        stream.main,
        args=[
            "-c12",
            "-m20",
            "--stream-size 45000000",
            "--bench-iters 1900",
            "--bench-threads 1 4 12",
            "--max-balloon 18",
        ],
        modes={
            "base-manual": ["--suffix baseline-stream", "--baseline"],
            "base-manual": ["--suffix virtio-balloon-stream"],
            "huge-manual": ["--suffix virtio-balloon-huge-stream"],
            "virtio-mem": ["--suffix virtio-mem-stream"],
            "virtio-mem": ["--suffix virtio-mem-vfio-stream", "--vfio", "{vfio}"],
            "llfree-manual": ["--suffix llfree-stream"],
            "llfree-manual": ["--suffix llfree-vfio-stream", "--vfio", "{vfio}"],
        },
        long_modes={},
        plot=stream_plot_fn,
    ),
    Benchmark(
        "ftq",
        stream.main,
        args=[
            "--ftq",
            "-c12",
            "-m20",
            "--bench-threads 1 4 12",
            "--bench-iters 1096",
            "--max-balloon 18",
        ],
        modes={
            "base-manual": ["--suffix baseline-stream", "--baseline"],
            "base-manual": ["--suffix virtio-balloon-stream"],
            "huge-manual": ["--suffix virtio-balloon-huge-stream"],
            "virtio-mem": ["--suffix virtio-mem-stream"],
            "virtio-mem": ["--suffix virtio-mem-vfio-stream", "--vfio", "{vfio}"],
            "llfree-manual": ["--suffix llfree-stream"],
            "llfree-manual": ["--suffix llfree-vfio-stream", "--vfio", "{vfio}"],
        },
        long_modes={},
        plot=ftq_plot_fn,
    ),
]


async def main():
    parser = ArgumentParser(description="Benchmark Runner")
    benchmarks = {benchmark.name: benchmark for benchmark in BENCHMARKS}
    parser.add_argument("benchmark", nargs="+", choices=benchmarks)
    parser.add_argument("--vfio", action="store_true")
    args = parser.parse_args()

    for benchmark in BENCHMARKS:
        if benchmark.name in args.benchmark:
            await benchmark.run(args.vfio)


if __name__ == "__main__":
    asyncio.run(main())
