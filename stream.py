from argparse import ArgumentParser
import shlex
from subprocess import CalledProcessError
from time import sleep
from typing import *
from abc import ABC, abstractmethod

from utils import *
from psutil import Process
import asyncio
from time import time
from qemu.qmp import QMPClient

# Selected Spec benches an their respective memory consumption in MiB (1 copy)
SPEC_SUITE = {
    "502.gcc_r": 1338,
    "531.deepsjeng_r": 700,
    "557.xz_r": 726, #?
    "503.bwaves_r": 822,
    "507.cactuBSSN_r": 789,
    "526.blender_r": 590,
    "527.cam4_r": 861, #?
    "549.fotonik3d_r": 848,
    "554.roms_r": 842,
}

SET_BALLOON = {
    "base-manual": lambda target_size, qmp: qmp.execute("balloon", {"value" : target_size * 1024 * 1024 * 1024}),
    "huge-manual": lambda target_size, qmp: qmp.execute("balloon", {"value" : target_size * 1024 * 1024 * 1024}),
    "llfree-manual": lambda target_size, qmp: qmp.execute("llfree-balloon", {"value" : target_size * 1024 * 1024 * 1024}),
    "llfree-manual-map": lambda target_size, qmp: qmp.execute("llfree-balloon", {"value" : target_size * 1024 * 1024 * 1024}),
    "virtio-mem-kernel": lambda target_size, qmp: qmp.execute("qom-set", {"path": "vm0",
                                                                          "property": "requested-size",
                                                                          "value" : target_size * 1024 * 1024 * 1024}),
    "virtio-mem-movable": lambda target_size, qmp: qmp.execute("qom-set", {"path": "vm0",
                                                                        "property": "requested-size",
                                                                        "value" : target_size * 1024 * 1024 * 1024}),
}

STREAM_BENCH = {
    "copy": "-DCOPY",
    "scale": "-DSCALE",
    "add": "-DADD",
    "triad": "-DTRIAD",
}

class Bench(ABC):
    @abstractmethod
    def args(self, parser: ArgumentParser):
        pass

    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def run(self) -> Popen[str]:
        pass

    @abstractmethod
    def results(self):
        pass

class Stream(Bench):
    _ssh: SSHExec
    _iters: int
    _threads: int
    _size: int
    _bench: str
    _cores: int
    _HOME: str = "/home/debian/STREAM/"
    _handle = Popen[str]
    _results: Path

    def args(parser: ArgumentParser):
        parser.add_argument("--stream-bench", choices=list(STREAM_BENCH.keys()), default="copy")
        parser.add_argument("--stream-size", default=45000000, type=int)


    def __init__(self, ssh: SSHExec, args: Namespace, results: Path, threads: int) -> None:
        super().__init__()
        self._ssh = ssh
        self._iters = args.bench_iters * threads
        self._threads = threads
        self._size = args.stream_size
        self._bench = STREAM_BENCH[args.stream_bench]
        self._cores = args.cores
        self._results = results

    def setup(self):
        # Build STREAM
        print("Building stream")
        openmp = "-fopenmp"
        if self._threads < 2:
            openmp = ""

        self._ssh.run(f"gcc -O2 {openmp} -DSTREAM_ARRAY_SIZE={self._size} -DNTIMES={self._iters} {self._bench} {self._HOME}stream.c -o {self._HOME}stream.elf")

        # Clear remaining artifacts of previous runs
        self._ssh.run(f"rm -rf {self._HOME}*.csv")

    def run(self) -> Popen[str]:
        # Start STREAM and wait for some time to start shrinking the vm
        print("Starting STREAM")
        # Start assigning CPUs from 3 upwards, only use the lower two if needed
        assert self._cores >= 2, "At least 3 cores are required for proper measurements"
        cpu_max = self._cores - 1
        taskset = f"2-{cpu_max} 1 0"
        return self._ssh.background(f"cd {self._HOME}; export GOMP_CPU_AFFINITY=\"{taskset}\"; export OMP_NUM_THREADS={self._threads}; ./stream.elf")

    def results(self):
        # Collect results
        self._ssh.download(Path(self._HOME) / "*.csv", str(self._results))

class FTQ(Bench):
    _ssh: SSHExec
    _iters: int
    _threads: int
    _sampling_interval: int
    _HOME: str = "/home/debian/ftqV110/ftq/"
    _handle = Popen[str]
    _results: Path

    def args(parser: ArgumentParser):
        parser.add_argument("--ftq-interval", default=28, type=int)

    def __init__(self, ssh: SSHExec, args: Namespace, results: Path, threads: int) -> None:
        super().__init__()
        self._ssh = ssh
        self._iters = args.bench_iters
        self._threads = threads
        self._sampling_interval = args.ftq_interval
        self._bench = STREAM_BENCH[args.stream_bench]
        self._cores = args.cores
        self._results = results

    def setup(self):
        # Build the matching version of FTQ
        # Threaded FTQ does not accept `-t 1` -.-
        print("Building FTQ")
        if self._threads < 2:
            self._ssh.run(f"cd {self._HOME}; make ftq")
        else:
            self._ssh.run(f"cd {self._HOME}; make t_ftq")

        # Clear remaining artifacts of previous runs
        self._ssh.run(f"rm -rf {self._HOME}*.dat")

    def run(self) -> Popen[str]:
        print("Starting FTQ")
        if self._threads < 2:
            return self._ssh.background(f"cd {self._HOME}; ./ftq -n {self._iters} -i {self._sampling_interval}")
        else:
            return self._ssh.background(f"cd {self._HOME}; ./t_ftq -t {self._threads} -n {self._iters} -i {self._sampling_interval}")

    def results(self):
        self._ssh.download(Path(self._HOME) / "*.dat", str(self._results))

def build_taskset(cpus: Iterable[int]) -> int:
    set = 0
    for cpu in cpus:
        set |= 2 ** cpu

    return set

def gen_spec(ssh: SSHExec, root: Path, max_mem:int, time_per_bench:float):
    """
    Generates a scipt that runs the spec suite given a max memory consumption [GiB] and a time per bench [s]

    Expects that the benchmark directories are set up and all the binaries are already build
    e.g. with `runcpu --config=ballooning --action=setup <benches>`
    """
    #print(" ".join(SPEC_SUITE.keys()))
    #exit()
    # NOTE: We need to run their setup script (shrc) everytime to set up the environment
    #       We also need to increase the stacksize by A LOT. Some of the fortran programs will overflow the stack otherwise (e.g. bwaves).
    script = "cd cpu2017\nsource shrc\nulimit -s 2097152\n"
    for (bench, mem) in SPEC_SUITE.items():
        copies = (max_mem * 1024) // mem
        # Run the bench as a background process and sleep for the required ammount of time
        script += f"runcpu --config=ballooning.cfg --copies={copies} --action=onlyrun {bench} &\n"
        script += f"sleep {time_per_bench}s\n"
        # There seems to be no way to kill a spec run besides nuking the whole process group. Tools like htop and timeout will NOT kill all processes.
        script += "kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')\n"
        script += "sleep 10s\n"
    s_path = root / "run_spec.sh"
    s_path.write_text(script)
    ssh.upload(s_path, "~")
    # Clear the run directories after each run as they are MASSIVE
    ssh.run("rm -Rf ~/cpu2017/benchspec/C*/*/run")

async def main():
    parser = ArgumentParser(
        description="Running the stream benchmark while shrinking the vm after a memory-intensive workload")
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--kernel", required=True)
    parser.add_argument("--user", default="debian")
    parser.add_argument("--img", default="/opt/ballooning/debian.img")
    parser.add_argument("--port", default=5222, type=int)
    parser.add_argument("--qmp", default=5023, type=int)
    parser.add_argument("-m", "--mem", default=20, type=int)
    parser.add_argument("-c", "--cores", type=int, default=12)
    parser.add_argument("--mode", choices=list(BALLOON_CFG.keys()), required=True)
    parser.add_argument('--spec', action="store_true")
    parser.add_argument("--bench-iters", type=int, default=400) # per core
    parser.add_argument("--bench-threads", type=int, nargs='+')
    parser.add_argument('--ftq', action="store_true")
    parser.add_argument('--baseline', action="store_true")
    parser.add_argument("--workload-mem", type=int, default=19)
    parser.add_argument("--workload-time", type=int, default=180) # only for spec
    parser.add_argument("--initial-balloon", type=int, default=0)
    parser.add_argument("--max-balloon", type=int, default=20)
    parser.add_argument("--shrink-target", type=int, default=2)
    parser.add_argument("--post-delay", default=20, type=int)
    parser.add_argument("--deflate-delay", default=90, type=int)
    parser.add_argument("--vfio", type=int, help="IOMMU that shoud be passed into VM. This has to be bound to VFIO first!")
    Stream.args(parser)
    FTQ.args(parser)
    args, root = setup("stream", parser, custom="vm")

    for bench_threads in args.bench_threads:
        res_dir = root / f"{bench_threads}"
        res_dir.mkdir(exist_ok=True)


        print(f"----------Running with {bench_threads}/{args.cores}----------")
        try:
            print("Starting qemu...")
            min_mem = args.mem - args.max_balloon
            init_mem = args.mem - args.initial_balloon
            qemu = qemu_vm(args.qemu, args.port, args.kernel, args.cores, hda=args.img, qmp_port=args.qmp,
                        extra_args=BALLOON_CFG[args.mode](args.cores, args.mem, min_mem, init_mem),
                        env={**os.environ, "QEMU_LLFREE_LOG": str(res_dir / "llfree_log.txt")}, vfio_group=args.vfio)
            qemu_wait_startup(qemu, root / "boot.txt")
            ps_proc = Process(qemu.pid)

            qmp = QMPClient("STREAM machine")
            await qmp.connect(("127.0.0.1", args.qmp))

            print("Started")
            (res_dir / "cmd.sh").write_text(shlex.join(qemu.args))
            ssh = SSHExec(args.user, port=args.port)
            if args.spec:
                gen_spec(ssh, root, args.workload_mem, args.workload_time)

            bench: Bench = FTQ(ssh, args, res_dir, bench_threads) if args.ftq else Stream(ssh, args, res_dir, bench_threads)
            bench.setup()

            # Consume memory to blow up the vm
            if args.spec:
                ssh.run("bash run_spec.sh")
            else:
                print("Allocating")
                ssh.run(f"./write -m {args.workload_mem} -t {args.cores}")

            print(await qmp.execute("query-memory-devices"))
            print(await qmp.execute("x-query-numa"))

            # Chill a bit before running bench
            sleep(5)

            # Start bench and wait for some time to start shrinking the vm
            bench_handle = bench.run()
            bench_start_time = time()
            sleep(args.post_delay)
            if not args.baseline:
                res = await SET_BALLOON[args.mode](args.shrink_target, qmp)
                print(f"Balloon returned {res}")

                # Deflate balloon again
                sleep(args.deflate_delay - (time() - bench_start_time))
                if bench_handle.poll() is not None:
                    print("Warning: Bench was done before deflation started")
                await SET_BALLOON[args.mode](18, qmp)
                print("Deflating balloon again")


            # Wait for bench to be done
            while bench_handle.poll() is None:
                sleep(1)
            print(f"Bench exited with {bench_handle.returncode}.")

            # Collect results
            bench.results()

            # Cleanup
            print("Terminating...")
            await qmp.disconnect()
            ssh.run("sudo shutdown 0")
            sleep(15)
        except Exception as e:
            print(e)
            if isinstance(e, CalledProcessError):
                with (res_dir / f"error.txt").open("w+") as f:
                    if e.stdout: f.write(e.stdout)
                    if e.stderr: f.write(e.stderr)

            (res_dir / "error.txt").write_text(rm_ansi_escape(non_block_read(qemu.stdout)))
            qemu.terminate()
            raise e



asyncio.run(main())
