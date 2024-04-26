from argparse import ArgumentParser, Action, Namespace
import shlex
from subprocess import CalledProcessError
from time import sleep
from typing import Any, Sequence

from utils import *
from psutil import Process
import signal


DEFAULTS = {
    "base": {
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
        "build": "make -C llfree-linux -j`nproc`",
        "clean": "make -C llfree-linux -j`nproc` clean",
    },
    "clang": {
        "build": "ninja -C llvm-project/build",
        "clean": "ninja -C llvm-project/build clean",
    },
    "blender": {
        "build": "cd cpu2017 && source shrc && ulimit -s 2097152 && runcpu --config=ballooning.cfg --tune=peak --copies=`nproc` --action=onlyrun 526.blender_r",
        "clean": "echo nop",
    },
    "write": {
        "build": "./write -t`nproc` -m8",
        "clean": "echo nop",
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
    parser.add_argument("-r", "--repeat", type=int, default=1)
    parser.add_argument("--frag", action="store_true")
    parser.add_argument("--perf", action="store_true")
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--mode", choices=list(BALLOON_CFG.keys()),
                        required=True, action=ModeAction)
    parser.add_argument("--target", choices=list(TARGET.keys()))
    args, root = setup("compiling", parser, custom="vm")

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
                       extra_args=BALLOON_CFG[args.mode](args.cores, args.mem, 0, args.mem),
                       env=env)
        ps_proc = Process(qemu.pid)

        print("started")
        (root / "cmd.sh").write_text(shlex.join(qemu.args))
        (root / "boot.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))

        for i in range(args.iter):
            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            print(f"Exec i={i} c={args.cores}")

            mem_usage = (root / f"out_{i}.csv").open("w+")
            mem_usage.write("rss,small,huge,cached\n")

            ssh.run(TARGET[args.target]["clean"])

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

            # Start profiling
            if args.perf:
                perf_file = root / f"{i}.perf.guest"
                perf = Popen(shlex.split(f"perf kvm stat record -p {qemu.pid} -o {perf_file}"), stderr=STDOUT)

            measure(0)

            sec = 1

            build_end = []
            delay_end = []

            for r in range(args.repeat):
                # Compilation
                process = ssh.background(TARGET[args.target]["build"])

                while process.poll() is None:
                    measure(sec, process)
                    sleep(1)
                    sec += 1
                build_end.append(sec)
                with (root / f"out_{i}.txt").open("a+") as f:
                    f.write(process.stdout.read())

                # Delay after the compilation
                for s in range(sec, sec + args.delay):
                    measure(s)
                    sleep(1)
                sec += args.delay
                delay_end.append(sec)

            # Signal perf to dump it's trace
            if args.perf:
                perf.send_signal(signal.SIGINT)

            # Clean
            process = ssh.background(TARGET[args.target]["clean"])
            for s in range(sec, sec + args.delay):
                measure(s)
                sleep(1)
            assert process.poll() is not None
            sec += args.delay
            clean_end = sec

            # Shrink page cache
            ssh.run(f"echo 1 | sudo tee /proc/sys/vm/drop_caches")
            for s in range(sec, sec + args.delay):
                measure(s)
                sleep(1)
            sec += args.delay
            shrink_end = sec

            (root / f"times_{i}.json").write_text(json.dumps({
                "build": build_end, "delay": delay_end,
                "clean": clean_end, "shrink": shrink_end
            }))

            if args.perf:
                # Make sure perf finished writing the profile
                while perf.poll() is None:
                    sleep(1)

                # `perf report` write to stderr for some reason, so we can't use `check_output()`
                with open(root / f"{i}_perfstats.txt", "w+") as f:
                    perf_stats = Popen(shlex.split(f"perf kvm -i {perf_file} stat report --event=vmexit"), stderr=f)
                while perf_stats.poll() is None:
                    continue

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
