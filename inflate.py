from argparse import ArgumentParser, Action, Namespace
import asyncio
import shlex
from subprocess import CalledProcessError
from time import sleep, time
from typing import Any, Sequence

from utils import *
from psutil import Process
from qemu.qmp import QMPClient


DEFAULTS = {
    "base": {
        "qemu": "/opt/ballooning/virtio-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "virtio-mem": {
        "qemu": "/opt/ballooning/virtio-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "huge": {
        "qemu": "/opt/ballooning/virtio-huge-qemu-system",
        "kernel": "/opt/ballooning/buddy-huge-bzImage",
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
        qemu = qemu_vm(args.qemu, args.port, args.kernel, args.cores, hda=args.img,
                       extra_args=BALLOON_CFG[args.mode](args.cores, args.mem, 0, args.mem - args.shrink_target),
                       env=env)
        ps_proc = Process(qemu.pid)

        qmp = QMPClient("STREAM machine")
        await qmp.connect(("127.0.0.1", args.qmp))

        print("started")
        (root / "cmd.sh").write_text(shlex.join(qemu.args))
        (root / "boot.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))

        print(f"Exec c={args.cores}")
        for i in range(args.iter):
            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            # Grow VM
            ssh.run(f"./write -t{args.cores} -m{int((args.mem - 1) * 0.9)}")

            mem = args.mem * 1024**3
            target = args.shrink_target * 1024**3

            # Shrink / Inflate
            await set_balloon(qmp, args.mode, target, target)

            # Wait until VM is smaller
            while (size := await query_balloon(qmp, args.mode, target)) > 1.01 * (target):
                print("inflating", size)
                sleep(1)
            # Wait a little longer
            sleep(args.delay)

            print("RSS:", ps_proc.memory_info().rss // 1024**2, "target:", target // 1024**2)

            # Grow / Deflate
            await set_balloon(qmp, args.mode, target, args.mem * 1024**3)
            while (size := await query_balloon(qmp, args.mode, target)) < 0.99 * (args.mem * 1024**3):
                print("deflating", size)
                sleep(1)
            sleep(args.delay) # just hope that this is long enough (deflate is usually quite fast)

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


if __name__ == "__main__":
    asyncio.run(main())
