from argparse import Action, ArgumentParser, Namespace
from collections.abc import Callable, Sequence
from itertools import chain
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent

DEFAULTS = {
    "base": {
        "qemu": ROOT.parent / "hyperalloc-qemu/build-virt/qemu-system-x86_64",
        "kernel": ROOT.parent / "hyperalloc-linux/build-buddy-vm/arch/x86/boot/bzImage",
        "module": ROOT.parent / "linux-alloc-bench/build-buddy-vm/alloc.ko",
    },
    "huge": {
        "qemu": ROOT.parent / "hyperalloc-qemu/build-huge/qemu-system-x86_64",
        "kernel": ROOT.parent
        / "hyperalloc-linux/build-buddy-huge/arch/x86/boot/bzImage",
        "module": ROOT.parent / "linux-alloc-bench/build-buddy-huge/alloc.ko",
    },
    "virtio-mem": {
        "qemu": ROOT.parent / "hyperalloc-qemu/build-virt/qemu-system-x86_64",
        "kernel": ROOT.parent / "hyperalloc-linux/build-buddy-vm/arch/x86/boot/bzImage",
        "module": ROOT.parent / "linux-alloc-bench/build-buddy-vm/alloc.ko",
    },
    "llfree": {
        "qemu": ROOT.parent / "hyperalloc-qemu/build/qemu-system-x86_64",
        "kernel": ROOT.parent
        / "hyperalloc-linux/build-llfree-vm/arch/x86/boot/bzImage",
        "module": ROOT.parent / "linux-alloc-bench/build-llfree-vm/alloc.ko",
    },
}


class ModeAction(Action):
    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        nargs: int | str | None = None,
        **kwargs,
    ) -> None:
        assert nargs is None, "nargs not allowed"
        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(
        self,
        parser: ArgumentParser,
        namespace: Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        assert isinstance(values, str)
        assert (
            values in BALLOON_CFG.keys()
        ), f"mode has to be on of {list(BALLOON_CFG.keys())}"

        kind = values.split("-")[0] if values != "virtio-mem" else values
        assert kind in DEFAULTS, f"Unknown mode: {kind}"

        if namespace.qemu is None:
            namespace.qemu = str(DEFAULTS[kind]["qemu"])
        if namespace.kernel is None:
            namespace.kernel = str(DEFAULTS[kind]["kernel"])
        if "module" in namespace and namespace.module is None:
            namespace.module = str(DEFAULTS[kind]["module"])
        setattr(namespace, self.dest, values)


BALLOON_CFG: dict[str, Callable[[int, int, int, int], list[str]]] = {
    "base-manual": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, False
    ),
    "base-auto": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, True
    ),
    "huge-manual": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, False
    ),
    "huge-auto": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, True
    ),
    "llfree-manual": lambda cores, mem, _min_mem, _init_mem: qemu_llfree_balloon_args(
        cores, mem, False
    ),
    "llfree-auto": lambda cores, mem, _min_mem, _init_mem: qemu_llfree_balloon_args(
        cores, mem, True
    ),
    "virtio-mem": lambda _cores, mem, min_mem, init_mem: qemu_virtio_mem_args(
        mem, min_mem, init_mem
    ),
}


def qemu_llfree_balloon_args(cores: int, mem: int, auto: bool) -> list[str]:
    per_core_iothreads = [f"iothread{c}" for c in range(cores)]
    auto_mode_iothread = "auto-mode-iothread"
    device = {
        "driver": "virtio-llfree-balloon",
        "auto-mode": auto,
        "auto-mode-iothread": auto_mode_iothread,
        "iothread-vq-mapping": [{"iothread": t} for t in per_core_iothreads],
    }
    return [
        "-m",
        f"{mem}G",
        "-object",
        f"iothread,id={auto_mode_iothread}",
        *chain(*[["-object", f"iothread,id={t}"] for t in per_core_iothreads]),
        "-device",
        json.dumps(device),
    ]


def qemu_virtio_balloon_args(cores: int, mem: int, auto: bool) -> list[str]:
    return [
        "-m",
        f"{mem}G",
        "-device",
        json.dumps({"driver": "virtio-balloon", "free-page-reporting": auto}),
    ]


def qemu_virtio_mem_args(mem: int, min_mem: int, init_mem: int) -> list[str]:
    default_state = "online_movable"
    vmem_size = round(mem - min_mem)
    req_size = round(init_mem - min_mem)
    return [
        # fmt: off
        "-m", f"{min_mem}G,maxmem={mem}G",
        "-append", f"memhp_default_state={default_state}",
        "-machine", "pc",
        "-object", f"memory-backend-ram,id=vmem0,size={vmem_size}G,prealloc=off,reserve=off",
        "-device", f"virtio-mem-pci,id=vm0,memdev=vmem0,node=0,requested-size={req_size}G,prealloc=off"
    ]
