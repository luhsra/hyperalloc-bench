from argparse import ArgumentParser, Action, Namespace
import asyncio
import shlex
from subprocess import CalledProcessError
from time import sleep, time
from collections.abc import Callable, Sequence

from utils import *
from psutil import Process
import signal
from qemu.qmp import QMPClient
from vm_resize import VMResize


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
                        help="IOMMU that should be passed into VM. This has to be bound to VFIO first!")
    parser.add_argument("--vmem-fraction", type=float, default=1/16)
    parser.add_argument("--fpr-delay", type=int, help="Delay between reports in ms")
    parser.add_argument("--fpr-capacity", type=int, help="Size of the fpr buffer")
    parser.add_argument("--fpr-order", type=int, help="Report granularity")
    args, root = setup("compiling", parser, custom="vm")

    ssh = SSHExec(args.user, port=args.port)

    print("Running")
    i = 0

    qemu = None

    try:
        for i in range(args.iter):
            print("start qemu...")
            min_mem = round(args.mem / 8)
            extra_args = BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, min_mem)
            if (x := args.fpr_delay) is not None:
                extra_args += ["-append", f"page_reporting.page_reporting_delay={x}"]
            if (x := args.fpr_capacity) is not None:
                extra_args += ["-append", f"page_reporting.page_reporting_capacity={x}"]
            if (x := args.fpr_order) is not None:
                extra_args += ["-append", f"page_reporting.page_reporting_order={x}"]

            qemu = qemu_vm(args.qemu, args.port, args.kernel, args.cores, hda=args.img, qmp_port=args.qmp,
                        extra_args=extra_args, vfio_group=args.vfio)
            ps_proc = Process(qemu.pid)

            print("started")
            if i == 0:
                (root / "cmd.sh").write_text(shlex.join(qemu.args))

            qemu_wait_startup(qemu, root / f"boot_{i}.txt")

            # Check for the FPR configuration
            if (x := args.fpr_delay) is not None:
                assert x == int(ssh.output("cat /sys/module/page_reporting/parameters/page_reporting_delay").strip())
            if (x := args.fpr_capacity) is not None:
                assert x == int(ssh.output("cat /sys/module/page_reporting/parameters/page_reporting_capacity").strip())
            if args.mode == "base-auto":
                order = x if (x := args.fpr_order) is not None else 9
                assert order == int(ssh.output("cat /sys/module/page_reporting/parameters/page_reporting_order").strip
                ())

            client = QMPClient("compile vm")
            await client.connect(("127.0.0.1", args.qmp))
            vm_resize = VMResize(client, "virtio-mem-movable", args.mem * 1024**3, min_mem * 1024**3)

            if qemu.poll() is not None:
                raise Exception("Qemu crashed")

            print(f"Exec i={i} c={args.cores}")

            mem_usage = (root / f"out_{i}.csv").open("w+")

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

            measure = Messure(i, ssh, vm_resize, ps_proc, root, mem_usage, args)

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

            # Signal perf to dump it's trace
            if args.perf:
                perf.send_signal(signal.SIGINT)

            # Clean
            clean_end = None
            if "clean" in TARGET[args.target]:
                process = ssh.background(TARGET[args.target]["clean"])
                clean_end = await measure.wait(sec=args.delay)
                assert process.poll() is not None, "Clean has not terminated"

            # drop page cache
            ssh.run(f"echo 1 | sudo tee /proc/sys/vm/drop_caches")
            drop_end = await measure.wait(sec=args.delay)

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

            with (root / f"out_{i}.txt").open("a+") as f:
                f.write(rm_ansi_escape(non_block_read(qemu.stdout)))

            print("terminate...")
            await client.disconnect()
            qemu.terminate()
            sleep(3)

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


class Messure:
    def __init__(self, i: int, ssh: SSHExec, vm_resize: VMResize, ps_proc: Process,
                    root: Path, mem_usage: IO[str], args: Namespace) -> None:
        self.i = i
        self.ssh = ssh
        self.vm_resize = vm_resize
        self.ps_proc = ps_proc
        self.root = root
        self.mem_usage = mem_usage
        self.args = args

        # A bit of memory is reserved for kernel stuff
        zoneinfo = self.ssh.output("cat /proc/zoneinfo")
        self._reserved_mem = (parse_zoneinfo(zoneinfo, "present ") - parse_zoneinfo(zoneinfo, "managed ")) * 2**12
        self.mem_usage.write("time,rss,small,huge,cached,total\n")

        times = self.ps_proc.cpu_times()
        self._times_user = times.user
        self._times_system = times.system
        self._time = time()

    async def __call__(self, process: Popen[str] | None = None):
        sec = self.sec()

        small, huge = free_pages(self.ssh.output("cat /proc/buddyinfo", timeout=10))
        meminfo = parse_meminfo(self.ssh.output("cat /proc/meminfo", timeout=10))
        total = meminfo["MemTotal"] + self._reserved_mem
        rss = self.ps_proc.memory_info().rss
        self.mem_usage.write(f"{sec:.2f},{rss},{small},{huge},{meminfo['Cached']},{total}\n")

        if self.args.frag:
            output = self.ssh.output("cat /proc/llfree_frag")
            (self.root / f"frag_{self.i}_{sec:.2f}.txt").write_text(output)

        if process is not None:
            with (self.root / f"out_{self.i}.txt").open("a+") as f:
                f.write(rm_ansi_escape(non_block_read(process.stdout)))

        # resize vm
        if self.args.mode.startswith("virtio-mem-"):
            # Follow free huge pages
            free = int(huge * 2**(12+9) * 0.9) # 10% above allocated pages
            # Step size, amount of mem that is plugged/unplugged
            step = round(self.vm_resize.max * self.args.vmem_fraction)
            if free < step/2: # grow faster
                await self.vm_resize.set(self.vm_resize.size + 2*step)
            elif free < step:
                await self.vm_resize.set(self.vm_resize.size + step)
            elif free > 2*step:
                await self.vm_resize.set(self.vm_resize.size - step)

    def sec(self) -> float:
        return time() - self._time

    async def wait(self, sec: float | None = None,
             condition: Callable[[], bool] | None = None,
             process: Popen[str] | None = None) -> float:
        if sec is not None:
            wait_end = self.sec() + sec
            while self.sec() < wait_end:
                await self(process)
                sleep(1)
        elif condition is not None:
            while condition():
                await self(process)
                sleep(1)
        return self.sec()

    def times(self) -> tuple[float, float, float]:
        """Returns (total, user, system) times in s"""
        times = self.ps_proc.cpu_times()
        return (
            time() - self._time,
            times.user - self._times_user,
            times.system - self._times_system,
        )


if __name__ == "__main__":
    asyncio.run(main())
