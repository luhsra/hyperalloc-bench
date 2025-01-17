from argparse import Action, ArgumentParser, Namespace
from asyncio import sleep
import asyncio
from collections.abc import Sequence
import json
from pathlib import Path
import shlex
from time import time
from subprocess import CalledProcessError, Popen, check_call
from typing import Any
from qemu.qmp import QMPClient

from psutil import Process

from measure import Measure
from vm_resize import VMResize
from utils import (
    BALLOON_CFG,
    SSHExec,
    non_block_read,
    qemu_vm,
    qemu_wait_startup,
    rm_ansi_escape,
    setup,
    timestamp,
)


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

        kind = values.split("-")[0]
        assert kind in DEFAULTS

        if namespace.qemu is None:
            namespace.qemu = DEFAULTS[kind]["qemu"]
        if namespace.kernel is None:
            namespace.kernel = DEFAULTS[kind]["kernel"]
        if namespace.suffix is None:
            namespace.suffix = values
        setattr(namespace, self.dest, values)


class SystemdSlice:
    def __init__(self, **args):
        self.properties = args

    def __enter__(self):
        ts = timestamp()
        self.slice = Path.home() / f".config/systemd/user/ballooning-{ts}.slice"
        self.slice.write_text(
            "\n".join(
                [
                    "[Unit]",
                    f"Description=HyperAlloc Slice {ts}",
                    "Before=slices.target",
                    "[Slice]",
                    *[f"{k}={v}" for k, v in self.properties.items()],
                ]
            )
        )
        check_call(["systemctl", "--user", "daemon-reload"])
        return self.slice

    def __exit__(self, exc_type, exc_value, traceback):
        self.slice.unlink()
        check_call(["systemctl", "--user", "daemon-reload"])


async def main():
    parser = ArgumentParser(
        description="Compiling linux in a vm while monitoring memory usage"
    )
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
    parser.add_argument(
        "--mode", choices=[*BALLOON_CFG.keys()], required=True, action=ModeAction
    )
    parser.add_argument("--target", choices=list(TARGET.keys()), required=True)
    parser.add_argument("--vfio", type=int, help="Bound VFIO group for passthrough.")
    parser.add_argument("--vmem-fraction", type=float, default=1 / 16)
    parser.add_argument("--vms", type=int, default=1)
    parser.add_argument("--high-mem", type=int)
    args, root = setup("multivm", parser, custom="vm")

    mem = args.mem * args.vms
    with SystemdSlice(
        MemoryMax=f"{mem}G", MemoryHigh=f"{args.high_mem or mem}G"
    ) as slice:
        print("Running slice", slice)

        for i in range(args.iter):
            vms = []
            for id in range(args.vms):
                dir = root / f"vm_{id}"
                dir.mkdir()
                vms.append(asyncio.create_task(boot_vm(args, dir, id, slice.name, i)))

            vms = await asyncio.gather(*vms)

            time_start = time()

            times = []
            async with asyncio.TaskGroup() as group:
                for id, vm in enumerate(vms):
                    dir = root / f"vm_{id}"
                    group.create_task(exec_vm(args, dir, id, vm, time_start, i))
            times.append(time() - time_start)

            (root / f"time_{i}.txt").write_text(json.dumps({"total": times}))


async def boot_vm(
    args: Namespace, root: Path, id: int, slice: str, i: int
) -> Popen[str]:
    qemu = None
    ssh = SSHExec(args.user, port=args.port + id)

    try:
        print(f"start vm {id}...")
        min_mem = round(args.mem / 8)
        extra_args = BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, min_mem)

        qemu = qemu_vm(
            args.qemu,
            args.port + id,
            args.kernel,
            args.cores,
            hda=args.img,
            qmp_port=args.qmp + id,
            extra_args=extra_args,
            vfio_group=args.vfio,
            slice=slice,
        )
        print(f"started {id}")
        if i == 0:
            (root / "cmd.sh").write_text(shlex.join(qemu.args))

        await qemu_wait_startup(qemu, root / f"boot_{i}.txt")

        if qemu.poll() is not None:
            raise Exception("Qemu crashed")

        if "clean" in TARGET[args.target]:
            await ssh.run(TARGET[args.target]["clean"])

    except Exception as e:
        (root / "exception.txt").write_text(str(e))
        if isinstance(e, CalledProcessError):
            with (root / f"error_{i}.txt").open("w+") as f:
                if e.stdout:
                    f.write(e.stdout)
                if e.stderr:
                    f.write(e.stderr)
        if qemu:
            (root / "error.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
            qemu.terminate()
        raise e

    return qemu


async def exec_vm(
    args: Namespace, root: Path, id: int, qemu: Popen[str], time_start: float, i: int
):
    # client = None
    try:
        # client = QMPClient("compile vm")
        # await client.connect(("127.0.0.1", args.qmp + id))
        # vm_resize = VMResize(
        #     client, "virtio-mem-movable", args.mem * 1024**3, min_mem * 1024**3
        # )

        if qemu.poll() is not None:
            raise Exception("Qemu crashed")

        print(f"Exec vm={id} i={i} c={args.cores}")

        ssh = SSHExec(args.user, port=args.port + id)
        mem_usage = (root / f"out_{i}.csv").open("w+")
        ps_proc = Process(qemu.pid)
        measure = Measure(i, ssh, ps_proc, root, mem_usage, args, time_start=time_start)
        await measure()

        # time slot for the next benchmark
        timeslot = time_start + (args.delay / args.vms * id) + args.delay

        build_start = []
        build_end = []
        clean_end = []
        for r in range(args.repeat):
            await measure.wait(sec=timeslot - time())
            timeslot += args.delay

            # Compilation
            build_start.append(measure.sec())
            print(f"start compile {id}: {build_start[-1]}")
            process = await ssh.process(TARGET[args.target]["build"])

            build_time = await measure.wait(process=process)
            if process.returncode != 0:
                raise CalledProcessError(
                    process.returncode,
                    TARGET[args.target]["build"],
                    await process.stdout.read(),
                )
            build_end.append(build_time)
            with (root / f"out_{i}.txt").open("ab+") as f:
                if process.stdout:
                    f.write(await process.stdout.read())

            # Optional clean command
            if "clean" in TARGET[args.target]:
                process = await ssh.process(TARGET[args.target]["clean"])
                clean_time = await measure.wait(process=process)
                if process.returncode != 0:
                    raise CalledProcessError(
                        process.returncode,
                        TARGET[args.target]["clean"],
                        await process.stdout.read(),
                    )
                clean_end.append(clean_time)
                with (root / f"out_{i}.txt").open("ab+") as f:
                    if process.stdout:
                        f.write(await process.stdout.read())

        await measure.wait(sec=timeslot - time())

        t_total, t_user, t_system = measure.times()

        (root / f"times_{i}.json").write_text(
            json.dumps(
                {
                    "start": build_start,
                    "build": build_end,
                    "clean": clean_end,
                    "cpu": {
                        "total": t_total,
                        "user": t_user,
                        "system": t_system,
                    },
                }
            )
        )

        with (root / f"out_{i}.txt").open("a+") as f:
            f.write(rm_ansi_escape(non_block_read(qemu.stdout)))

    except Exception as e:
        (root / "exception.txt").write_text(str(e))
        if isinstance(e, CalledProcessError):
            with (root / f"error_{i}.txt").open("w+") as f:
                if e.stdout:
                    f.write(e.stdout)
                if e.stderr:
                    f.write(e.stderr)
        (root / "error.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
        raise e
    finally:
        print("terminate...")
        # if client:
        #     await client.disconnect()
        qemu.terminate()
        await sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
