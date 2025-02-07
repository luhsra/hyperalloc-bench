#!/usr/bin/env python3

from argparse import ArgumentParser
import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from pathlib import Path
import shutil
import itertools
import traceback
from typing import Any
import sys

from compiling import bench as compiling, plot as compiling_plot
from inflate import bench as inflate, plot as inflate_plot
from multivm import bench as mutlivm, plot as multivm_plot
from scripts.config import ROOT
from stream import bench as stream, plot as stream_plot


@dataclass
class Config:
    vfio: str | None
    fast: bool
    extra: bool
    stream_iters: int
    ftq_iters: int
    port: int
    qmp_port: int


class Benchmark:

    def __init__(
        self,
        name: str,
        function: Callable[[Sequence[str]], Coroutine],
        default: dict[str, Any],
        fast: dict[str, Any],
        args: list[str],
        modes: list[tuple[str, list[str]]],
        long_modes: list[tuple[str, list[str]]],
        plot: Callable[["Benchmark", Config], None],
    ):
        self.name = name
        self.function = function
        self.default = default
        self.fast = fast

        self.args = args
        self.modes = modes
        self.long_modes = long_modes

        self.plot_fn = plot

    async def run(self, config: Config):
        root = Path("artifact-eval") / self.name
        shutil.rmtree(root, ignore_errors=True)

        replacements = self.fast if config.fast else self.default
        replacements["vfio"] = config.vfio
        replacements["stream_iters"] = config.stream_iters
        replacements["ftq_iters"] = config.ftq_iters

        print(f"\n\x1b[94mRunning {self.name} bench\x1b[0m")
        base_args = self.args + [
            "--root",
            f"{root}",
            "--no-timestamp",
            "--port",
            f"{config.port}",
            "--qmp",
            f"{config.qmp_port}",
        ]

        async def run_mode(mode: str, extra_args: list[str]):
            try:
                args = base_args + extra_args + ["--mode", mode]
                if any([("{vfio}" in arg) for arg in args]) and config.vfio is None:
                    print(f"\n\x1b[94mSkipping {mode} because vfio is not set\x1b[0m")
                    return

                args = [arg.format(**replacements) for arg in args]
                filename = Path(self.function.__code__.co_filename).relative_to(ROOT)
                print(f"\n\x1b[94mRunning {mode}: {filename} {' '.join(args)}\x1b[0m")
                await self.function(args)
            except Exception as e:
                print(f"\x1b[91mFailed to run {mode}: {e}\x1b[0m")
                print(f"\x1b[91m{traceback.format_exc()}\x1b[0m")

        for mode, extra_args in self.modes:
            await run_mode(mode, extra_args)

        if config.extra:
            for mode, extra_args in self.long_modes:
                await run_mode(mode, extra_args)

        print(f"\n\x1b[94mFinished {self.name} bench\x1b[0m")

    def plot(self, config: Config):
        print(f"\n\x1b[94mPlotting {self.name}\x1b[0m")
        self.plot_fn(self, config)

    def root(self) -> Path:
        return Path("artifact-eval") / self.name


def inflate_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()
    vfio = config.vfio is not None
    inflate_plot.init()
    inflate_plot.visualize(
        [
            root / "base-manual",
            root / "huge-manual",
            root / "virtio-mem",
            *([root / "virtio-mem-vfio"] if vfio else []),
            root / "llfree-manual",
            *([root / "llfree-manual-vfio"] if vfio else []),
        ],
        [
            root / "base-manual-nofault",
            root / "huge-manual-nofault",
            root / "virtio-mem-nofault",
            *([root / "virtio-mem-vfio-nofault"] if vfio else []),
            root / "llfree-manual-nofault",
            *([root / "llfree-manual-vfio-nofault"] if vfio else []),
        ],
        save_as="inflate",
        out=root,
    )


def stream_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()

    vfio = config.vfio is not None
    drivers = [
        "virtio-balloon",
        "virtio-balloon-huge",
        *(["virtio-mem+VFIO"] if vfio else []),
        "virtio-mem",
        *(["HyperAlloc+VFIO"] if vfio else []),
        "HyperAlloc",
        "Baseline",
    ]

    stream_plot.init()
    stream, stream_meta = stream_plot.load_streams(root, drivers)
    stream_plot.visualize_stream(
        [
            "virtio-balloon",
            "virtio-balloon-huge",
            "virtio-mem",
            *(["virtio-mem+VFIO", "HyperAlloc+VFIO"] if vfio else []),
        ],
        stream,
        stream_meta,
        save_as="stream",
        out=root,
    )


def ftq_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()
    vfio = config.vfio is not None
    drivers = [
        "virtio-balloon",
        "virtio-balloon-huge",
        *(["virtio-mem+VFIO"] if vfio else []),
        "virtio-mem",
        *(["HyperAlloc+VFIO"] if vfio else []),
        "HyperAlloc",
        "Baseline",
    ]
    stream_plot.init()
    ftq, ftq_meta = stream_plot.load_ftqs(root, drivers)
    stream_plot.visualize_ftq(
        [
            "virtio-balloon",
            "virtio-balloon-huge",
            "virtio-mem",
            *(["virtio-mem+VFIO", "HyperAlloc+VFIO"] if vfio else []),
        ],
        ftq,
        ftq_meta,
        save_as="ftq",
        out=root,
    )


def compiling_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()
    replacements = bench.fast if config.fast else bench.default
    target = replacements["target"]

    compiling_plot.init()
    compiling_plot.visualize(
        {
            "Buddy": root / f"{target}-base-manual",
            "LLFree": root / f"{target}-llfree-manual",
        },
        f"{target}-baseline",
        out=root,
    )
    compiling_plot.visualize(
        {
            "virtio-balloon": root / f"{target}-base-auto",
            "HyperAlloc": root / f"{target}-llfree-auto",
        },
        f"{target}-auto",
        out=root,
    )
    if config.vfio is not None:
        compiling_plot.visualize(
            {
                "virtio-mem+VFIO": root / f"{target}-virtio-mem-vfio",
                "HyperAlloc+VFIO": root / f"{target}-llfree-auto-vfio",
            },
            f"{target}-auto-vfio",
            out=root,
        )

    extra_runs = {}
    if config.extra:
        extra_runs = {
            f"o={o} d={d} c={c}": (
                "virtio-balloon",
                root / f"{target}-base-auto-o{o}-d{d}-c{c}",
            )
            for o, d, c in itertools.product([9, 0], [2000, 100], [32, 512])
        }
    else:
        extra_runs = {
            "o=9 d=2000 c=32": ("virtio-balloon", root / f"{target}-base-auto")
        }

    paths = {
        "Buddy": ("baseline", root / f"{target}-base-manual"),
        "LLFree": ("baseline", root / f"{target}-llfree-manual"),
        **extra_runs,
        "virtio-mem": ("", root / f"{target}-virtio-mem"),
        "virtio-mem+VFIO": ("", root / f"{target}-virtio-mem-vfio"),
        "HyperAlloc": ("", root / f"{target}-llfree-auto"),
        "HyperAlloc+VFIO": ("", root / f"{target}-llfree-auto-vfio"),
    }
    if not config.vfio:
        paths.pop("virtio-mem+VFIO")
        paths.pop("HyperAlloc+VFIO")
    compiling_plot.overview(
        paths,
        f"{target}",
        out=root,
    )

def blender_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()
    replacements = bench.fast if config.fast else bench.default
    target = replacements["target"]
    compiling_plot.visualize(
        {
            "Baseline": root / f"{target}-base-auto",
            "HyperAlloc": root / f"{target}-llfree-auto",
        },
        save_as=f"{target}",
        out=root,
    )


def multivm_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()
    replacements = bench.fast if config.fast else bench.default
    target = replacements["target"]
    multivm_plot.visualize(
        {
            "Baseline": root / f"{target}-base-manual",
            "virtio-balloon": root / f"{target}-base-auto",
            "HyperAlloc": root / f"{target}-llfree-auto",
        },
        save_as=f"{target}",
        out=root,
    )
    multivm_plot.visualize(
        {
            "Baseline": root / f"{target}-base-manual-s",
            "virtio-balloon": root / f"{target}-base-auto-s",
            "HyperAlloc": root / f"{target}-llfree-auto-s",
        },
        save_as=f"{target}-s",
        out=root,
    )


BENCHMARKS = [
    Benchmark(
        "inflate",
        inflate.main,
        default={"iter": 5},
        fast={"iter": 2},
        args=["-m20", "-c12", "--shrink-target", "2", "-i{iter}"],
        modes=[
            ("base-manual", []),
            ("huge-manual", []),
            ("llfree-manual", []),
            ("llfree-manual", ["--suffix", "llfree-manual-vfio", "--vfio-dev", "{vfio}"]),
            ("virtio-mem", []),
            ("virtio-mem", ["--suffix", "virtio-mem-vfio", "--vfio-dev", "{vfio}"]),
            # nofault
            ("base-manual", ["--suffix", "base-manual-nofault", "--nofault"]),
            ("huge-manual", ["--suffix", "huge-manual-nofault", "--nofault"]),
            ("llfree-manual", ["--suffix", "llfree-manual-nofault", "--nofault"]),
            (
                "llfree-manual",
                [
                    "--suffix",
                    "llfree-manual-vfio-nofault",
                    "--vfio-dev",
                    "{vfio}",
                    "--nofault",
                ],
            ),
            ("virtio-mem", ["--suffix", "virtio-mem-nofault", "--nofault"]),
            (
                "virtio-mem",
                [
                    "--suffix",
                    "virtio-mem-vfio-nofault",
                    "--vfio-dev",
                    "{vfio}",
                    "--nofault",
                ],
            ),
        ],
        long_modes=[],
        plot=inflate_plot_fn,
    ),
    Benchmark(
        "stream",
        stream.main,
        default={},
        fast={},
        args=[
            "-c12",
            "-m20",
            "--stream-size",
            "45000000",
            "--bench-iters",
            "{stream_iters}",
            "--bench-threads",
            "1",
            "4",
            "12",
            "--max-balloon",
            "18",
        ],
        modes=[
            ("base-manual", ["--suffix", "baseline-stream", "--baseline"]),
            ("base-manual", ["--suffix", "virtio-balloon-stream"]),
            ("huge-manual", ["--suffix", "virtio-balloon-huge-stream"]),
            ("virtio-mem", ["--suffix", "virtio-mem-stream"]),
            ("virtio-mem", ["--suffix", "virtio-mem-vfio-stream", "--vfio-dev", "{vfio}"]),
            ("llfree-manual", ["--suffix", "llfree-stream"]),
            ("llfree-manual", ["--suffix", "llfree-vfio-stream", "--vfio-dev", "{vfio}"]),
        ],
        long_modes=[],
        plot=stream_plot_fn,
    ),
    Benchmark(
        "ftq",
        stream.main,
        default={},
        fast={},
        args=[
            "--ftq",
            "-c12",
            "-m20",
            "--bench-threads",
            "1",
            "4",
            "12",
            "--bench-iters",
            "{ftq_iters}",
            "--max-balloon",
            "18",
        ],
        modes=[
            ("base-manual", ["--suffix", "baseline-ftq", "--baseline"]),
            ("base-manual", ["--suffix", "virtio-balloon-ftq"]),
            ("huge-manual", ["--suffix", "virtio-balloon-huge-ftq"]),
            ("virtio-mem", ["--suffix", "virtio-mem-ftq"]),
            ("virtio-mem", ["--suffix", "virtio-mem-vfio-ftq", "--vfio-dev", "{vfio}"]),
            ("llfree-manual", ["--suffix", "llfree-ftq"]),
            ("llfree-manual", ["--suffix", "llfree-vfio-ftq", "--vfio-dev", "{vfio}"]),
        ],
        long_modes=[],
        plot=ftq_plot_fn,
    ),
    Benchmark(
        "compiling",
        compiling.main,
        default={"target": "clang", "delay": 200, "mem": 16},
        fast={"target": "write", "delay": 10, "mem": 12},
        args=["--target", "{target}", "-m{mem}", "-c12", "--delay", "{delay}"],
        modes=[
            ("base-manual", []),
            ("base-auto", []),
            ("llfree-manual", []),
            ("llfree-auto", []),
            (
                "llfree-auto",
                ["--suffix", "{target}-llfree-auto-vfio", "--vfio-dev", "{vfio}"],
            ),
            ("virtio-mem", []),
            (
                "virtio-mem",
                ["--suffix", "{target}-virtio-mem-vfio", "--vfio-dev", "{vfio}"],
            ),
        ],
        long_modes=[
            (
                "base-auto",
                [
                    "--suffix",
                    f"{{target}}-base-auto-o{o}-d{d}-c{c}",
                    "--fpr-order",
                    f"{o}",
                    "--fpr-delay",
                    f"{d}",
                    "--fpr-capacity",
                    f"{c}",
                ],
            )
            for o, d, c in itertools.product([0, 9], [100, 2000], [32, 512])
        ],
        plot=compiling_plot_fn,
    ),
    Benchmark(
        "blender",
        compiling.main,
        default={"target": "blender", "delay": 240, "mem": 16},
        fast={"target": "write", "delay": 10, "mem": 12},
        args=["--target", "{target}", "-m{mem}", "-c12", "--delay", "{delay}", "--repeat", "3"],
        modes=[
            ("base-auto", []),
            ("llfree-auto", []),
        ],
        long_modes=[],
        plot=blender_plot_fn,
    ),
    Benchmark(
        "multivm",
        mutlivm.main,
        default={"target": "clang", "delay": 7200, "mem": 16},
        fast={"target": "write", "delay": 30, "mem": 10},
        args=[
            "--target",
            "{target}",
            "-m{mem}",
            "-c8",
            "--delay",
            "{delay}",
            "--repeat",
            "3",
            "--vms",
            "3",
        ],
        modes=[
            ("base-manual", []),
            ("base-auto", []),
            ("llfree-auto", []),
            ("base-manual", ["--suffix", "{target}-base-manual-s", "--simultaneous"]),
            ("base-auto", ["--suffix", "{target}-base-auto-s", "--simultaneous"]),
            ("llfree-auto", ["--suffix", "{target}-llfree-auto-s", "--simultaneous"]),
        ],
        long_modes=[],
        plot=multivm_plot_fn,
    ),
]


async def build():
    parent = Path(__file__).parent.parent

    async def run(cmd: str, cwd: Path):
        print(f"\n\x1b[94mRunning: {cmd}\n - CWD={cwd}\x1b[0m")
        cwd.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_shell(cmd, cwd=cwd)
        ret = await process.wait()
        assert ret == 0, f"Failed with {ret}"

    await run("make LLVM=-16 -j`nproc` O=build-buddy-vm", cwd=parent / "hyperalloc-linux")
    await run("make LLVM=-16 -j`nproc` O=build-buddy-huge", cwd=parent / "hyperalloc-linux")
    await run("make LLVM=-16 -j`nproc` O=build-llfree-vm", cwd=parent / "hyperalloc-linux")

    await run("./build.sh", cwd=parent / "linux-alloc-bench")

    await run(
        "CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp && ninja",
        cwd=parent / "hyperalloc-qemu/build-virt",
    )
    await run(
        "CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-balloon-huge && ninja",
        cwd=parent / "hyperalloc-qemu/build-huge",
    )
    await run(
        "CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-llfree && ninja",
        cwd=parent / "hyperalloc-qemu/build",
    )


async def main():
    parser = ArgumentParser(description="Benchmark Runner")
    benchmarks = {benchmark.name: benchmark for benchmark in BENCHMARKS}
    parser.add_argument("step", choices=["build", "bench", "plot", "bench-plot"],
                        help="The step to run")
    parser.add_argument("-b", "--bench", choices=["all", *benchmarks], default="all",
                        help="The benchmark to execute or 'all'")
    parser.add_argument("--vfio-dev", help="A device from a bound VFIO group for passthrough")
    parser.add_argument("--fast", action="store_true",
                        help="Use a reduced set of parameters for testing")
    parser.add_argument("--extra", action="store_true",
        help="Run the additional compile benchmarks that evaluate virtio-balloon's parameters")
    parser.add_argument("--port", type=int, default=5300, help="SSH port of the VMs")
    parser.add_argument("--qmp-port", type=int, default=5400, help="QMP port of the VMs")
    parser.add_argument("--stream-iters", type=int, default=1900, help="Number of stream iterations")
    parser.add_argument("--ftq-iters", type=int, default=1096, help="Number of stream iterations")
    args = parser.parse_args()

    config = Config(
        args.vfio_dev, args.fast, args.extra,
        args.stream_iters, args.ftq_iters,
        args.port, args.qmp_port
    )

    if args.step == "build":
        await build()

    for benchmark in BENCHMARKS:
        if (args.bench == "all" and benchmark.name != "blender") or args.bench == benchmark.name:
            try:
                if args.step in ["bench-plot", "bench"]:
                    await benchmark.run(config)
                if args.step in ["bench-plot", "plot"]:
                    benchmark.plot(config)
            except Exception as e:
                print(f"\x1b[91mFailed to run {benchmark.name}: {e}\x1b[0m")
                print(f"\x1b[91m{traceback.format_exc()}\x1b[0m")


if __name__ == "__main__":
    asyncio.run(main())
