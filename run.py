#!/usr/bin/env python3

from argparse import ArgumentParser
import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from pathlib import Path
import shutil
import itertools
from typing import Any
import sys

from compiling import bench as compiling, plot as compiling_plot
from inflate import bench as inflate, plot as inflate_plot
from multivm import bench as mutlivm, plot as multivm_plot
from scripts.config import ROOT
from stream import bench as stream, plot as stream_plot


@dataclass
class Config:
    vfio: int | None
    fast: bool
    long: bool
    specs: bool


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

        print(f"\n\x1b[94mRunning {self.name} bench\x1b[0m")
        base_args = self.args + ["--root", f"{root}", "--no-timestamp"]

        async def run_mode(mode: str, extra_args: list[str]):
            args = base_args + extra_args + ["--mode", mode]
            if any([("{vfio}" in arg) for arg in args]) and config.vfio is None:
                print(f"\n\x1b[94mSkipping {mode} because vfio is not set\x1b[0m")
                return

            args = [arg.format(**replacements) for arg in args]
            filename = Path(self.function.__code__.co_filename).relative_to(ROOT)
            print(
                f"\n\x1b[94mRunning {mode}: {filename} {' '.join(args)}\x1b[0m"
            )
            await self.function(args)

        for mode, extra_args in self.modes:
            await run_mode(mode, extra_args)

        if config.long:
            for mode, extra_args in self.long_modes:
                await run_mode(mode, extra_args)

        print(f"\n\x1b[94mFinished {self.name} bench\x1b[0m")

    def plot(self, config: Config):
        print(f"\n\x1b[94mPlotting {self.name}\x1b[0m")
        self.plot_fn(self, config)

    def root(self) -> Path:
        return Path("artifact-eval") / self.name


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

    long_runs = {}
    if config.long:
        long_runs = {
            f"o={o} d={d} c={c}": (
                "virtio-balloon",
                root / f"{target}-base-auto-o{o}-d{d}-c{c}",
            )
            for o, d, c in itertools.product([9, 0], [2000, 100], [32, 512])
        }

    paths = {
        "Buddy": ("baseline", root / f"{target}-base-manual"),
        "LLFree": ("baseline", root / f"{target}-llfree-manual"),
        **long_runs,
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


def inflate_plot_fn(bench: Benchmark, config: Config):
    root = bench.root()
    vfio = config.vfio is not None
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

    stream, stream_meta = stream_plot.load_streams(root, drivers)
    stream_plot.init()
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
    ftq, ftq_meta = stream_plot.load_ftqs(root, drivers)
    stream_plot.init()
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


BENCHMARKS = [
    Benchmark(
        "compiling",
        compiling.main,
        default={"target": "clang", "delay": 200, "mem": 16},
        fast={"target": "write", "delay": 10, "mem": 12},
        args=["--target", "{target}", "-m{mem}", "-c12", "--delay", "{delay}"],
        modes=[
            ("base-manual", []),
            ("base-auto", []),
            ("huge-auto", []),
            ("llfree-manual", []),
            ("llfree-auto", []),
            (
                "llfree-auto",
                ["--suffix", "{target}-llfree-auto-vfio", "--vfio", "{vfio}"],
            ),
            ("virtio-mem", []),
            (
                "virtio-mem",
                ["--suffix", "{target}-virtio-mem-vfio", "--vfio", "{vfio}"],
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
        "inflate",
        inflate.main,
        default={"iter": 10},
        fast={"iter": 3},
        args=["-m20", "-c12", "--shrink-target", "2", "-i{iter}"],
        modes=[
            ("base-manual", []),
            ("huge-manual", []),
            ("llfree-manual", []),
            ("llfree-manual", ["--suffix", "llfree-auto-vfio", "--vfio", "{vfio}"]),
            ("virtio-mem", []),
            ("virtio-mem", ["--suffix", "virtio-mem-vfio", "--vfio", "{vfio}"]),
            # nofault
            ("base-manual", ["--suffix", "base-manual-nofault", "--nofault"]),
            ("huge-manual", ["--suffix", "huge-manual-nofault", "--nofault"]),
            ("llfree-manual", ["--suffix", "llfree-manual-nofault", "--nofault"]),
            (
                "llfree-manual",
                [
                    "--suffix",
                    "llfree-manual-vfio-nofault",
                    "--vfio",
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
                    "--vfio",
                    "{vfio}",
                    "--nofault",
                ],
            ),
        ],
        long_modes=[],
        plot=inflate_plot_fn,
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
            "1900",
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
            ("virtio-mem", ["--suffix", "virtio-mem-vfio-stream", "--vfio", "{vfio}"]),
            ("llfree-manual", ["--suffix", "llfree-stream"]),
            ("llfree-manual", ["--suffix", "llfree-vfio-stream", "--vfio", "{vfio}"]),
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
            "1096",
            "--max-balloon",
            "18",
        ],
        modes=[
            ("base-manual", ["--suffix", "baseline-stream", "--baseline"]),
            ("base-manual", ["--suffix", "virtio-balloon-stream"]),
            ("huge-manual", ["--suffix", "virtio-balloon-huge-stream"]),
            ("virtio-mem", ["--suffix", "virtio-mem-stream"]),
            ("virtio-mem", ["--suffix", "virtio-mem-vfio-stream", "--vfio", "{vfio}"]),
            ("llfree-manual", ["--suffix", "llfree-stream"]),
            ("llfree-manual", ["--suffix", "llfree-vfio-stream", "--vfio", "{vfio}"]),
        ],
        long_modes=[],
        plot=ftq_plot_fn,
    ),
]


async def build():
    parent = Path(__file__).parent.parent

    async def run(cmd, cwd):
        print(f"\n\x1b[94mRunning: {cmd}\n - CWD={cwd}\x1b[0m")
        process = await asyncio.create_subprocess_shell(cmd, cwd=cwd)
        ret = await process.wait()
        assert ret == 0, f"Failed with {ret}"

    await run(
        "make LLVM=-16 -j`nproc` O=build-buddy-vm", cwd=parent / "hyperalloc-linux"
    )
    await run(
        "make LLVM=-16 -j`nproc` O=build-buddy-huge", cwd=parent / "hyperalloc-linux"
    )
    await run(
        "make LLVM=-16 -j`nproc` O=build-llfree-vm", cwd=parent / "hyperalloc-linux"
    )

    await run("./build.sh", cwd=parent / "linux-alloc-bench")

    await run(
        "CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-trace-backends=simple && ninja",
        cwd=parent / "hyperalloc-qemu/build-virt",
    )
    await run(
        "CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-balloon-huge --enable-trace-backends=simple && ninja",
        cwd=parent / "hyperalloc-qemu/build-huge",
    )
    await run(
        "CC=clang-16 ../configure --enable-debug --target-list=x86_64-softmmu --enable-slirp --enable-llfree --enable-trace-backends=simple && ninja",
        cwd=parent / "hyperalloc-qemu/build",
    )


async def main():
    parser = ArgumentParser(description="Benchmark Runner")
    benchmarks = {benchmark.name: benchmark for benchmark in BENCHMARKS}
    parser.add_argument("step", choices=["build", "bench", "plot", "bench-plot"])
    parser.add_argument("-b", "--bench", choices=["all", *benchmarks], default="all")
    parser.add_argument("--vfio", type=int)
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--long", action="store_true")
    parser.add_argument("--specs", action="store_true")
    args = parser.parse_args()

    config = Config(args.vfio, args.fast, args.long, args.specs)

    if args.step == "build":
        await build()

    for benchmark in BENCHMARKS:
        if args.bench == "all" or args.bench == benchmark.name:
            if args.step in ["bench-plot", "bench"]:
                await benchmark.run(config)
            if args.step in ["bench-plot", "plot"]:
                benchmark.plot(config)


if __name__ == "__main__":
    asyncio.run(main())
