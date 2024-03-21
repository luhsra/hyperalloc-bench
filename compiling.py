from argparse import ArgumentParser
from pathlib import Path
import shlex
from subprocess import CalledProcessError
from time import sleep
from typing import Tuple

from utils import *
from psutil import Process


def main():
    parser = ArgumentParser(
        description="Compiling linux in a vm while monitoring memory usage")
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--user", default="debian")
    parser.add_argument("--img", default="resources/hda.qcow2")
    parser.add_argument("--port", default=5222, type=int)
    parser.add_argument("-m", "--mem", default=32, type=int)
    parser.add_argument("-c", "--cores", type=int, default=8)
    parser.add_argument("-i", "--iter", type=int, default=1)
    parser.add_argument("--frag", action="store_true")
    args, root = setup("compiling", parser, custom="vm")

    ssh = SSHExec(args.user, port=args.port)

    print("Running")

    try:
        print("start qemu...")
        qemu = qemu_vm(args.qemu, args.port, args.kernel, args.mem, args.cores, hda=args.img)
        ps_proc = Process(qemu.pid)

        print("started")
        (root / "cmd.sh").write_text(shlex.join(qemu.args))
        (root / "boot.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))

        # ssh.run(f"echo 200 | sudo tee /proc/sys/vm/vfs_cache_pressure")

        for i in range(args.iter):
            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            print(f"Exec i={i} c={args.cores}")

            mem_usage = (root / f"out_{i}.csv").open("w+")
            mem_usage.write("rss,small,huge,cached\n")

            ssh.run("make -C llfree-linux clean")
            if args.frag:
                output = ssh.output("cat /proc/llfree_frag")
                (root / f"frag_{i}_s.txt").write_text(output)

            process = ssh.background(f"make -C llfree-linux -j{args.cores}")

            sec = 0
            while process.poll() is None:
                buddyinfo = ssh.output("cat /proc/buddyinfo")
                small, huge = free_pages(buddyinfo)
                meminfo = ssh.output("cat /proc/meminfo")
                cached = mem_cached(meminfo)
                rss = ps_proc.memory_info().rss
                mem_usage.write(f"{rss},{small},{huge},{cached}\n")

                if args.frag:
                    output = ssh.output("cat /proc/llfree_frag")
                    (root / f"frag_{i}_{sec}.txt").write_text(output)

                with (root / f"out_{i}.txt").open("a+") as f:
                    f.write(rm_ansi_escape(non_block_read(process.stdout)))

                sleep(1)
                sec += 1

            ssh.run("make -C llfree-linux clean")

            with (root / f"out_{i}.txt").open("a+") as f:
                f.write(rm_ansi_escape(process.stdout.read()))

            if args.frag:
                output = ssh.output("cat /proc/llfree_frag")
                (root / f"frag_{i}_e.txt").write_text(output)

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
    main()
