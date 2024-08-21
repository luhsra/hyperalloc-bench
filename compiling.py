from argparse import ArgumentParser, Action, Namespace
import asyncio
import shlex
from subprocess import CalledProcessError
from time import sleep, time
from typing import Any, Sequence

from utils import *
from psutil import Process
import signal
from qemu.qmp import QMPClient

# virtio-mem: Time between plug/unplug requests
PLUGGING_FREQ = 5
# virtio-mem: Amount of memory that is plugged/unplugged in one step
PLUGGING_FRACTION = 1/32


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


async def main():
    parser = ArgumentParser(
        description="Compiling linux in a vm while monitoring memory usage")
    parser.add_argument("--qemu")
    parser.add_argument("--kernel")
    parser.add_argument("--user", default="debian")
    parser.add_argument("--img", default="/opt/ballooning/debian.img")
    parser.add_argument("--port", type=int, default=5222)
    parser.add_argument("--qmp", default=5023, type=int)
    parser.add_argument("-m", "--mem", type=int, default=8)
    parser.add_argument("-c", "--cores", type=int, default=8)
    parser.add_argument("-i", "--iter", type=int, default=1)
    parser.add_argument("-r", "--repeat", type=int, default=1)
    parser.add_argument("--frag", action="store_true")
    parser.add_argument("--perf", action="store_true")
    parser.add_argument("--delay", type=int, default=10)
    parser.add_argument("--mode", choices=list(BALLOON_CFG.keys()),
                        required=True, action=ModeAction)
    parser.add_argument("--target", choices=list(TARGET.keys()), required=True)
    parser.add_argument("--vfio", type=int,
                        help="IOMMU that shoud be passed into VM. This has to be bound to VFIO first!")
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
        min_mem = round(args.mem / 8)
        qemu = qemu_vm(args.qemu, args.port, args.kernel, args.cores, hda=args.img, qmp_port=args.qmp,
                       extra_args=BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, min_mem),
                       env=env, vfio_group=args.vfio)
        ps_proc = Process(qemu.pid)

        print("started")
        (root / "cmd.sh").write_text(shlex.join(qemu.args))

        qemu_wait_startup(qemu, root / "boot.txt")

        client = QMPClient("compile vm")
        await client.connect(("127.0.0.1", args.qmp))
        qmp = QMPWrap(client, args.mem * 1024**3, min_mem * 1024**3)

        for i in range(args.iter):
            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            print(f"Exec i={i} c={args.cores}")

            mem_usage = (root / f"out_{i}.csv").open("w+")
            mem_usage.write("rss,small,huge,cached,total\n")

            if "clean" in TARGET[args.target]:
                ssh.run(TARGET[args.target]["clean"])

            # Start profiling
            if args.perf:
                perf_file = open(root / f"{i}_perfstats.json", "w+")
                # The filter for the kvm_exit event ensures that perf only counts exits that are ept violations
                # This does only work for intel though, AMD uses different values/formats
                # For more info on filters, see: https://www.kernel.org/doc/html/latest/trace/events.html#event-filtering
                # NOTE: The --filter arg is not documented for perf stat, but does seem to work anyways. Not sure if this is a bug...
                perf = Popen(shlex.split(f"perf stat -e \"kvm:kvm_exit\" --filter \"exit_reason==48\" -e \"dTLB-loads,dTLB-load-misses,dTLB-stores,dTLB-store-misses\" -j -p {qemu.pid}"), stderr=perf_file)

            measure = Messure(i, ssh, qmp, ps_proc, root, mem_usage, args)

            await measure(0)

            sec = 1

            build_end = []
            delay_end = []

            for r in range(args.repeat):
                # Compilation
                process = ssh.background(TARGET[args.target]["build"])

                while process.poll() is None:
                    await measure(sec, process)
                    sleep(1)
                    sec += 1
                build_end.append(sec)
                with (root / f"out_{i}.txt").open("a+") as f:
                    f.write(process.stdout.read())

                # Delay after the compilation
                for s in range(sec, sec + args.delay):
                    await measure(s)
                    sleep(1)
                sec += args.delay
                delay_end.append(sec)

            t_total, t_user, t_system = measure.times()

            # Signal perf to dump it's trace
            if args.perf:
                perf.send_signal(signal.SIGINT)

            # Clean
            clean_end = None
            if "clean" in TARGET[args.target]:
                process = ssh.background(TARGET[args.target]["clean"])
                for s in range(sec, sec + args.delay):
                    await measure(s)
                    sleep(1)
                assert process.poll() is not None
                sec += args.delay
                clean_end = sec

            # drop page cache
            ssh.run(f"echo 1 | sudo tee /proc/sys/vm/drop_caches")
            for s in range(sec, sec + args.delay):
                await measure(s)
                sleep(1)
            sec += args.delay
            drop_end = sec

            (root / f"times_{i}.json").write_text(json.dumps({
                "build": build_end, "delay": delay_end,
                "clean": clean_end, "drop": drop_end, "cpu": {
                    "total": t_total,
                    "user": t_user,
                    "system": t_system,
                }
            }))

            if args.perf:
                # Make sure perf finished writing the profile
                while perf.poll() is None:
                    sleep(1)


    except Exception as e:
        print(e)
        if isinstance(e, CalledProcessError):
            with (root / f"error_{i}.txt").open("w+") as f:
                if e.stdout: f.write(e.stdout)
                if e.stderr: f.write(e.stderr)
        try:
            (root / "error.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
            qemu.terminate()
        except UnboundLocalError: pass
        raise e

    (root / "out.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
    print("terminate...")
    qemu.terminate()
    sleep(3)


class QMPWrap:
    def __init__(self, qmp: QMPClient, max: int, min: int) -> None:
        self.qmp = qmp
        self.min = round(min)
        self.max = round(max)
        self.size = min

    async def set_target_size(self, target_size: int):
        if target_size >= self.max and self.size == self.max: return
        if target_size <= self.min and self.size == self.min: return

        self.size = max(self.min, min(self.max, round(target_size)))
        print("resize", self.size)
        await self.qmp.execute("qom-set", {
            "path": "vm0",
            "property": "requested-size",
            "value" : (((self.size - self.min) + 2**21 - 1) // 2**21) * 2**21
        })


class Messure:
    def __init__(self, i: int, ssh: SSHExec, qmp: QMPWrap, ps_proc: Process,
                    root: Path, mem_usage: IO[str], args: Namespace) -> None:
        self.i = i
        self.ssh = ssh
        self.qmp = qmp
        self.ps_proc = ps_proc
        self.root = root
        self.mem_usage = mem_usage
        self.args = args

    async def __call__(self, sec: int, process: Popen[str] | None = None):
        if sec == 0:
            times = self.ps_proc.cpu_times()
            self._times_user = times.user
            self._times_system = times.system
            self._time = time()

        small, huge = free_pages(self.ssh.output("cat /proc/buddyinfo"))
        meminfo = parse_meminfo(self.ssh.output("cat /proc/meminfo"))
        rss = self.ps_proc.memory_info().rss
        self.mem_usage.write(f"{rss},{small},{huge},{meminfo['Cached']},{meminfo['MemTotal']}\n")

        if self.args.frag:
            output = self.ssh.output("cat /proc/llfree_frag")
            (self.root / f"frag_{self.i}_{sec}.txt").write_text(output)

        if process is not None:
            with (self.root / f"out_{self.i}.txt").open("a+") as f:
                f.write(rm_ansi_escape(non_block_read(process.stdout)))

        # resize vm
        if self.args.mode.startswith("virtio-mem-") and sec % PLUGGING_FREQ == 0:
            # Follow free huge pages
            free = huge * 2**(12+9)
            # Step size, amount of mem that is plugged/unplugged
            step = round(self.qmp.max * PLUGGING_FRACTION)
            if free < step/2: # grow faster
                await self.qmp.set_target_size(self.qmp.size + 2*step)
            elif free < step:
                await self.qmp.set_target_size(self.qmp.size + step)
            elif free > 2*step:
                await self.qmp.set_target_size(self.qmp.size - step)

    def times(self) -> Tuple[float, float, float]:
        """Returns (total, user, system) times in s"""
        times = self.ps_proc.cpu_times()
        return (
            time() - self._time,
            times.user - self._times_user,
            times.system - self._times_system,
        )


if __name__ == "__main__":
    asyncio.run(main())
