from argparse import ArgumentParser
import asyncio
from collections.abc import Sequence
from pathlib import Path
import shlex
from subprocess import CalledProcessError
from asyncio import sleep
import csv

from psutil import Process
from qemu.qmp import QMPClient

from scripts.config import BALLOON_CFG, ModeAction
from scripts.qemu import qemu_vm, qemu_wait_startup
from scripts.utils import SSHExec, fmt_bytes, non_block_read, rm_ansi_escape, setup
from scripts.vm_resize import VMResize


async def main(argv: Sequence[str] | None = None):
    parser = ArgumentParser(
        description="Inflate and deflate the balloon, measuring the latency"
    )
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
    parser.add_argument(
        "--mode", choices=list(BALLOON_CFG.keys()), required=True, action=ModeAction
    )
    parser.add_argument("--nofault", action="store_true")
    parser.add_argument("--module")
    parser.add_argument("--vfio", type=int, help="Bound VFIO group for passthrough")
    args, root = setup(parser, argv)

    qemu = None
    qmp = None
    try:
        print("start qemu...")
        # make it a little smaller to have some headroom
        min_mem = args.shrink_target
        extra_args = BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, args.mem)
        qemu = qemu_vm(
            args.qemu,
            args.port,
            args.kernel,
            args.cores,
            hda=args.img,
            qmp_port=args.qmp,
            extra_args=extra_args,
            vfio_group=args.vfio,
        )
        ps_proc = Process(qemu.pid)

        (root / "cmd.sh").write_text(shlex.join(qemu.args))
        await qemu_wait_startup(qemu, root / "boot.txt")
        ssh = SSHExec(args.user, port=args.port)

        if not args.nofault and args.module:
            name = Path(args.module).name
            await ssh.upload(args.module, name)
            await ssh.run(f"sudo insmod {name}")

        qmp = QMPClient("STREAM machine")
        await qmp.connect(("127.0.0.1", args.qmp))

        max_bytes = args.mem * 1024**3
        min_bytes = min_mem * 1024**3
        resize = VMResize(qmp, args.mode, max_bytes, min_bytes, max_bytes)

        logfile = (root / "out.txt").open("w+")

        outfile = (root / "out.csv").open("w+")
        outfile.write("shrink,grow,touch,touch2\n")
        outfile.flush()

        print(f"Exec c={args.cores}")
        for i in range(args.iter):
            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            # Grow VM
            if not args.nofault:
                await ssh.run(f"./write -t{args.cores} -m{args.mem - 1}")

            await sleep(args.delay)

            target_bytes = args.shrink_target * 1024**3

            # Shrink / Inflate
            await resize.set(target_bytes)
            while (size := await resize.query()) > 1.01 * target_bytes:
                print("inflating", fmt_bytes(size))
                await sleep(1)
            await sleep(args.delay)

            print(
                "RSS:",
                fmt_bytes(ps_proc.memory_info().rss),
                "target:",
                fmt_bytes(target_bytes),
            )

            # Grow / Deflate
            await resize.set(max_bytes)
            while (size := await resize.query()) < 0.99 * max_bytes:
                print("deflating", fmt_bytes(size))
                await sleep(1)
            await sleep(args.delay)

            touch = 0
            touch2 = 0
            if not args.nofault and args.module:
                allocs = int(args.mem - 1) * 1024**3 // 4096
                await ssh.run(f"echo bulk 1 {allocs} 0 1 0 | sudo tee /proc/alloc/run")
                touch = (
                    parse_module_output(await ssh.output("sudo cat /proc/alloc/out"))
                    * allocs
                )
                await ssh.run(f"echo bulk 1 {allocs} 0 1 0 | sudo tee /proc/alloc/run")
                touch2 = (
                    parse_module_output(await ssh.output("sudo cat /proc/alloc/out"))
                    * allocs
                )

            output = rm_ansi_escape(non_block_read(qemu.stdout))
            logfile.write(output)
            logfile.flush()

            shrink, grow = parse_output(output, args.mode)
            outfile.write(f"{shrink},{grow},{touch},{touch2}\n")
            outfile.flush()

        logfile.write(rm_ansi_escape(non_block_read(qemu.stdout)))
    except Exception as e:
        print(e)
        errfile = (root / "error.txt").open("w+")
        if qemu:
            errfile.write(rm_ansi_escape(non_block_read(qemu.stdout)))
        if isinstance(e, CalledProcessError):
            if e.stdout:
                errfile.write(e.stdout)
            if e.stderr:
                errfile.write(e.stderr)
    finally:
        print("terminate...")
        if qmp:
            await qmp.disconnect()
        if qemu:
            qemu.terminate()
        await sleep(3)


def parse_module_output(output: str) -> int:
    print(output)
    reader = csv.DictReader(output.splitlines())
    return int(next(reader)["get_avg"])


def parse_write_output(output: str) -> int:
    reader = csv.DictReader(output.splitlines())
    return int(next(reader)["aavg"])


def parse_output(output: str, mode: str) -> tuple[int, int]:
    match mode:
        case "base-manual" | "huge-manual":
            return parse_output_with(
                output, " virtio_balloon_start ", " virtio_balloon_end "
            )
        case "llfree-manual":
            return parse_output_with(
                output, " llfree_balloon_start ", " llfree_balloon_end "
            )
        case "virtio-mem":
            return parse_output_with(
                output, " virtio_mem_config at ", " virtio_mem_end "
            )
        case _:
            assert False, "Invalid Mode"


def parse_output_with(
    output: str, start_marker: str, end_marker: str
) -> tuple[int, int]:
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
