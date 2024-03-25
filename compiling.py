from argparse import ArgumentParser, Action, Namespace
import shlex
from subprocess import CalledProcessError
from time import sleep
from typing import Any, Sequence

from utils import *
from psutil import Process


DEFAULTS = {
    "base": {
        "qemu": "/opt/ballooning/virtio-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "huge": {
        "qemu": "/opt/ballooning/huge-qemu-system",
        "kernel": "/opt/ballooning/buddy-bzImage",
    },
    "llfree": {
        "qemu": "/opt/ballooning/llfree-qemu-system",
        "kernel": "/opt/ballooning/llfree-bzImage",
    },
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


def main():
    parser = ArgumentParser(
        description="Compiling linux in a vm while monitoring memory usage")
    parser.add_argument("--qemu")
    parser.add_argument("--kernel")
    parser.add_argument("--user", default="debian")
    parser.add_argument("--img", default="/opt/ballooning/debian.img")
    parser.add_argument("--port", type=int, default=5222)
    parser.add_argument("-m", "--mem", type=int, default=8)
    parser.add_argument("-c", "--cores", type=int, default=8)
    parser.add_argument("-i", "--iter", type=int, default=1)
    parser.add_argument("--frag", action="store_true")
    parser.add_argument("--post-delay", type=int, default=10)
    parser.add_argument("--mode", choices=list(BALLOON_CFG.keys()),
                        required=True, action=ModeAction)
    args, root = setup("compiling", parser, custom="vm")

    ssh = SSHExec(args.user, port=args.port)

    print("Running")

    try:
        print("start qemu...")
        qemu = qemu_vm(args.qemu, args.port, args.kernel, args.mem, args.cores, hda=args.img,
                       extra_args=BALLOON_CFG[args.mode](args.cores),
                       env={**os.environ, "QEMU_LLFREE_LOG": str(root / "llfree_log.txt")})
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

            def measure(sec: int, process: Popen[str] | None = None):
                small, huge = free_pages(ssh.output("cat /proc/buddyinfo"))
                meminfo = parse_meminfo(ssh.output("cat /proc/meminfo"))
                rss = ps_proc.memory_info().rss
                mem_usage.write(f"{rss},{small},{huge},{meminfo['Cached']}\n")

                if args.frag:
                    output = ssh.output("cat /proc/llfree_frag")
                    (root / f"frag_{i}_{sec}.txt").write_text(output)

                if process is not None:
                    with (root / f"out_{i}.txt").open("a+") as f:
                        f.write(rm_ansi_escape(non_block_read(process.stdout)))

            measure(0)
            process = ssh.background(f"make -C llfree-linux -j{args.cores}")

            sec = 1
            while process.poll() is None:
                measure(sec, process)
                sleep(1)
                sec += 1
            build_end = sec

            # After the compilation
            for s in range(sec, sec + args.post_delay):
                measure(s)
                sleep(1)
            sec += args.post_delay
            delay_end = sec

            process = ssh.background("make -C llfree-linux clean")
            for s in range(sec, sec + args.post_delay):
                measure(s)
                sleep(1)
            assert process.poll() is not None
            sec += args.post_delay
            clean_end = sec

            # Shrink page cache
            ssh.run(f"echo 1 | sudo tee /proc/sys/vm/drop_caches")
            for s in range(sec, sec + args.post_delay):
                measure(s)
                sleep(1)
            sec += args.post_delay
            shrink_end = sec

            (root / f"times_{i}.json").write_text(json.dumps({
                "build": build_end, "delay": delay_end,
                "clean": clean_end, "shrink": shrink_end
            }))

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
