from argparse import ArgumentParser, Action, Namespace
import asyncio
import shlex
from subprocess import CalledProcessError
from time import sleep, time
from typing import Any, Sequence
import csv

from utils import *
from psutil import Process
from qemu.qmp import QMPClient


DEFAULTS = {
    "base": {
        "qemu": "/opt/ballooning/virtio-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "huge": {
        "qemu": "/opt/ballooning/virtio-huge-qemu-system",
        "kernel": "/opt/ballooning/buddy-huge-bzImage",
    },
    "virtio-mem": {
        "qemu": "/opt/ballooning/virtio-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "llfree": {
        "qemu": "/opt/ballooning/llfree-qemu-system",
        "kernel": "/opt/ballooning/llfree-bzImage",
    },
}

async def set_balloon(qmp: QMPClient, mode: str, min_bytes: int, target_bytes: int) -> any:
    assert target_bytes >= min_bytes
    match mode:
        case "base-manual" | "huge-manual":
            await qmp.execute("balloon", {"value" : target_bytes})
        case "llfree-manual" | "llfree-manual-map":
            await qmp.execute("llfree-balloon", {"value" : target_bytes})
        case "virtio-mem-kernel" | "virtio-mem-movable":
            await qmp.execute("qom-set", {"path": "vm0",
                                    "property": "requested-size",
                                    "value" : target_bytes - min_bytes})
        case _: assert False, "Invalid Mode"


async def query_balloon(qmp: QMPClient, mode: str, min_bytes: int) -> int:
    match mode:
        case "base-manual" | "huge-manual":
            return (await qmp.execute("query-balloon"))["actual"]
        case "llfree-manual" | "llfree-manual-map":
            return (await qmp.execute("query-llfree-balloon"))["actual"]
        case "virtio-mem-kernel" | "virtio-mem-movable":
            return min_bytes + (await qmp.execute("qom-get", {"path": "vm0",
                                    "property": "size"}))
        case _: assert False, "Invalid Mode"


class ModeAction(Action):
    def __init__(self, option_strings: Sequence[str], dest: str,
                 nargs: int | str | None = None, **kwargs) -> None:
        assert nargs is None, "nargs not allowed"
        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(self, parser: ArgumentParser, namespace: Namespace,
                 values: str | Sequence[Any] | None,
                 option_string: str | None = None) -> None:
        assert isinstance(values, str)
        assert values in BALLOON_CFG.keys(), f"mode has to be on of {list(BALLOON_CFG.keys())}"

        kind = values.rsplit("-", maxsplit=1)[0]
        assert kind in DEFAULTS

        if namespace.qemu is None: namespace.qemu = DEFAULTS[kind]["qemu"]
        if namespace.kernel is None: namespace.kernel = DEFAULTS[kind]["kernel"]
        if namespace.suffix is None: namespace.suffix = values
        setattr(namespace, self.dest, values)


async def main():
    parser = ArgumentParser(
        description="Inflate and deflate the balloon, measuring the latency")
    parser.add_argument("--qemu")
    parser.add_argument("--kernel")
    parser.add_argument("--user", default="debian")
    parser.add_argument("--img", default="/opt/ballooning/debian.img")
    parser.add_argument("--port", type=int, default=5222)
    parser.add_argument("--qmp", type=int, default=5023)
    parser.add_argument("-m", "--mem", type=int, default=8)
    parser.add_argument("-c", "--cores", type=int, default=8)
    parser.add_argument("-i", "--iter", type=int, default=1)
    parser.add_argument("--shrink-target", type=int, default=2)
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--mode", choices=list(BALLOON_CFG.keys()),
                        required=True, action=ModeAction)
    parser.add_argument("--nofault", action="store_true")
    parser.add_argument("--vfio", type=int)
    args, root = setup("inflate", parser, custom="vm")

    ssh = SSHExec(args.user, port=args.port)

    print("Running")

    try:
        print("start qemu...")
        env = {
            **os.environ,
            "QEMU_VIRTIO_BALLOON_INFLATE_LOG": str(root / "inf_log.txt"),
            "QEMU_VIRTIO_BALLOON_DEFLATE_LOG": str(root / "def_log.txt"),
            "QEMU_LLFREE_BALLOON_INFLATE_LOG": str(root / "inf_log.txt"),
            "QEMU_LLFREE_BALLOON_DEFLATE_LOG": str(root / "def_log.txt"),
        }
        # make it a little smaller to have some headroom
        min_mem = args.shrink_target // 2
        qemu = qemu_vm(args.qemu, args.port, args.kernel, args.cores, hda=args.img,
                       qmp_port=args.qmp,
                       extra_args=BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, args.mem),
                       env=env, vfio_group=args.vfio)
        ps_proc = Process(qemu.pid)

        (root / "cmd.sh").write_text(shlex.join(qemu.args))
        qemu_wait_startup(qemu, root / "boot.txt")

        qmp = QMPClient("STREAM machine")
        await qmp.connect(("127.0.0.1", args.qmp))

        print(f"Exec c={args.cores}")
        for i in range(args.iter):
            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            # Grow VM
            if not args.nofault:
                ssh.run(f"./write -t{args.cores} -m{args.mem - 1}")

            sleep(args.delay)

            mem = args.mem * 1024**3
            target = args.shrink_target * 1024**3
            min_bytes = min_mem * 1024**3

            # Shrink / Inflate
            await set_balloon(qmp, args.mode, min_bytes, target)

            # Wait until VM is smaller
            while (size := await query_balloon(qmp, args.mode, min_bytes)) > 1.01 * (target):
                print("inflating", size)
                sleep(1)
            sleep(args.delay)

            print("RSS:", ps_proc.memory_info().rss // 1024**2, "target:", target // 1024**2)

            # Grow / Deflate
            await set_balloon(qmp, args.mode, min_bytes, mem)
            while (size := await query_balloon(qmp, args.mode, min_bytes)) < 0.99 * mem:
                print("deflating", size)
                sleep(1)
            sleep(args.delay)

            touch = 0
            if not args.nofault:
                write_out = ssh.output(f"./write -t1 -m{args.mem - 1}")
                touch = parse_write_output(write_out) * 1000_000 # to ns

            output = rm_ansi_escape(non_block_read(qemu.stdout))
            (root / f"out_{i}.txt").write_text(output)

            shrink, grow = parse_output(output, args.mode)
            (root / f"out_{i}.csv").write_text(f"shrink,grow,touch\n{shrink},{grow},{touch}")


    except Exception as e:
        print(e)
        if isinstance(e, CalledProcessError):
            with (root / f"error_{i}.txt").open("w+") as f:
                if e.stdout: f.write(e.stdout)
                if e.stderr: f.write(e.stderr)

        (root / "error.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
        qemu.terminate()
        raise e

    (root / "out.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
    print("terminate...")
    qemu.terminate()
    sleep(3)


def parse_write_output(output: str) -> int:
    reader = csv.DictReader(output.splitlines())
    return int(next(reader)["aavg"])


def parse_output(output: str, mode: str) -> Tuple[int,int]:
    match mode:
        case "base-manual" | "huge-manual":
            return parse_output_with(output, " virtio_balloon_start ", " virtio_balloon_end ")
        case "llfree-manual":
            return parse_output_with(output, " llfree_balloon_start ", " llfree_balloon_end ")
        case "virtio-mem-kernel" | "virtio-mem-movable":
            return parse_output_with(output, " virtio_mem_config ", " virtio_mem_end ")
        case _: assert False, "Invalid Mode"


def parse_output_with(output: str, start_marker: str, end_marker: str) -> Tuple[int,int]:
    start = []
    end = []
    for line in output.splitlines():
        if start_marker in line:
            start.append(int(line.rsplit(" ", 2)[1]))
        if end_marker in line:
            end.append(int(line.rsplit(" ", 2)[1]))
    assert len(start) == 2 and len(end) == 2
    return end[0] - start[0], end[1] - start[1]



if __name__ == "__main__":
    asyncio.run(main())
