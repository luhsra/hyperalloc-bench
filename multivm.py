from argparse import Action, ArgumentParser, Namespace
from asyncio import sleep
import asyncio
from collections.abc import Sequence
import json
from pathlib import Path
import shlex
import signal
from time import time
from subprocess import CalledProcessError, check_call
from typing import Any
from qemu.qmp import QMPClient

from psutil import Process

from measure import Measure
from vm_resize import VMResize
from utils import BALLOON_CFG, SSHExec, non_block_read, qemu_vm, qemu_wait_startup, rm_ansi_escape, setup


DEFAULTS = {
    "base": {
        "qemu": "/opt/ballooning/virtio-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "virtio": {
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

TARGET = {
    "linux": {
        "build": "make -C linux -j`nproc`",
        "clean": "make -C linux -j`nproc` clean",
    },
    "clang": {
        "build": "ninja -C llvm-project/build",
        "clean": "ninja -C llvm-project/build clean",
    },
    "blender": {
        "build": "cd cpu2017 && source shrc && ulimit -s 2097152 && runcpu --config=ballooning.cfg --tune=peak --copies=`nproc` --action=onlyrun 526.blender_r",
    },
    "write": {
        "build": "./write -t`nproc` -m8",
    }
}

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

        kind = values.split("-")[0]
        assert kind in DEFAULTS

        if namespace.qemu is None: namespace.qemu = DEFAULTS[kind]["qemu"]
        if namespace.kernel is None: namespace.kernel = DEFAULTS[kind]["kernel"]
        if namespace.suffix is None: namespace.suffix = values
        setattr(namespace, self.dest, values)


class SystemdSlice:
    def __init__(self, max_mem: int, high_mem: int):
        self.max_mem = max_mem
        self.high_mem = high_mem

    def __enter__(self):
        self.slice = Path.home() / f'.config/systemd/user/ballooning-{self.max_mem}.slice'
        self.slice.write_text(f'''
[Unit]
Description=HyperAlloc Slice {self.max_mem}G
Before=slices.target

[Slice]
MemoryHigh={self.high_mem}G
MemoryMax={self.max_mem}G
''')
        check_call(['systemctl', '--user', 'daemon-reload'])
        return self.slice

    def __exit__(self, exc_type, exc_value, traceback):
        self.slice.unlink()
        check_call(['systemctl', '--user', 'daemon-reload'])


async def main():
    parser = ArgumentParser(
        description="Compiling linux in a vm while monitoring memory usage")
    parser.add_argument("--vms", type=int, default=1)
    parser.add_argument("--high-mem", type=int, default=8)
    parser.add_argument("--qemu")
    parser.add_argument("--kernel")
    parser.add_argument("--user", default="debian")
    parser.add_argument("--img", default="/opt/ballooning/debian.img")
    parser.add_argument("--port", type=int, default=5222)
    parser.add_argument("--qmp", default=5122, type=int)
    parser.add_argument("-m", "--mem", type=int, default=8)
    parser.add_argument("-c", "--cores", type=int, default=8)
    parser.add_argument("-i", "--iter", type=int, default=1)
    parser.add_argument("-r", "--repeat", type=int, default=1)
    parser.add_argument("--frag", action="store_true")
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--mode", choices=list(BALLOON_CFG.keys()),
                        required=True, action=ModeAction)
    parser.add_argument("--target", choices=list(TARGET.keys()), required=True)
    parser.add_argument("--vfio", type=int,
                        help="IOMMU that should be passed into VM. This has to be bound to VFIO first!")
    parser.add_argument("--vmem-fraction", type=float, default=1/16)
    parser.add_argument("--fpr-delay", type=int, help="Delay between reports in ms")
    parser.add_argument("--fpr-capacity", type=int, help="Size of the fpr buffer")
    parser.add_argument("--fpr-order", type=int, help="Report granularity")
    args, root = setup("multivm", parser, custom="vm")

    with SystemdSlice(args.mem * args.vms, args.high_mem) as slice:
        print("Running slice", slice)
        time_start = time()
        vm_tasks = []
        for id in range(args.vms):
            vm_tasks.append(asyncio.create_task(exec_vm(args, root, id)))

        (root / "time.txt").write_text(json.dumps({
            "total": time() - time_start
        }))

        await asyncio.gather(*vm_tasks)

    # Wait for VMs to shutdown
    await sleep(3)


async def exec_vm(args: Namespace, root: Path, id: int):
    # FIXME: SSH login does not work on vm with port other than 5222 -> probably requires identification acceptance
    ssh = SSHExec(args.user, port=args.port + id)
    qemu = None

    root = root / f"vm_{id}"
    root.mkdir()

    try:
        for i in range(args.iter):
            print("start qemu...")
            min_mem = round(args.mem / 8)
            extra_args = BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, min_mem)

            qemu = qemu_vm(args.qemu, args.port + id, args.kernel, args.cores, hda=args.img, qmp_port=args.qmp + id,
                        extra_args=extra_args, vfio_group=args.vfio)
            ps_proc = Process(qemu.pid)

            print("started")
            if i == 0:
                (root / "cmd.sh").write_text(shlex.join(qemu.args))

            await qemu_wait_startup(qemu, root / f"boot_{i}.txt")

            client = QMPClient("compile vm")
            await client.connect(("127.0.0.1", args.qmp + id))
            vm_resize = VMResize(client, "virtio-mem-movable", args.mem * 1024**3, min_mem * 1024**3)

            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            print(f"Exec i={i} c={args.cores}")

            mem_usage = (root / f"out_{i}.csv").open("w+")

            if "clean" in TARGET[args.target]:
                ssh.run(TARGET[args.target]["clean"])


            measure = Measure(i, ssh, vm_resize, ps_proc, root, mem_usage, args)

            await measure()

            build_end = []
            delay_end = []

            for r in range(args.repeat):
                # Compilation
                print("start compile")
                process = ssh.background(TARGET[args.target]["build"])

                build_time = await measure.wait(condition=lambda: process.poll() is None, process=process)
                build_end.append(build_time)
                with (root / f"out_{i}.txt").open("a+") as f:
                    f.write(process.stdout.read())

                # Delay after the compilation
                delay_end.append(await measure.wait(sec=args.delay))

            t_total, t_user, t_system = measure.times()


            # Clean
            clean_end = None
            if "clean" in TARGET[args.target]:
                process = ssh.background(TARGET[args.target]["clean"])
                clean_end = await measure.wait(sec=args.delay)
                assert process.poll() is not None, "Clean has not terminated"

            (root / f"times_{i}.json").write_text(json.dumps({
                "build": build_end, "delay": delay_end,
                "clean": clean_end, "cpu": {
                    "total": t_total,
                    "user": t_user,
                    "system": t_system,
                }
            }))

            with (root / f"out_{i}.txt").open("a+") as f:
                f.write(rm_ansi_escape(non_block_read(qemu.stdout)))

            print("terminate...")
            await client.disconnect()
            qemu.terminate()

    except Exception as e:
        (root / "exception.txt").write_text(str(e))
        if isinstance(e, CalledProcessError):
            with (root / f"error_{i}.txt").open("w+") as f:
                if e.stdout: f.write(e.stdout)
                if e.stderr: f.write(e.stderr)
        if qemu:
            (root / "error.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
            qemu.terminate()
        raise e

if __name__ == "__main__":
    asyncio.run(main())
