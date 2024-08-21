import fcntl
import json
import os
import re
import psutil
from argparse import ArgumentParser, Namespace
from datetime import datetime
from itertools import chain
from pathlib import Path
from subprocess import Popen, PIPE, STDOUT, check_call, check_output
from time import sleep
from typing import IO, Any, Dict, List, Optional, Tuple

import pandas as pd

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def setup(name: str, parser: ArgumentParser, custom=None) -> Tuple[Namespace, Path]:
    """
    Setup the benchmark directory and save the system config and execution parameters.

    Args:
        name: Name of the benchmark
        parser: CLI Arguments to be parsed and saved
        custom: Any custom metadata that should be saved
    """
    parser.add_argument("--output", help="Name of the output directory")
    parser.add_argument(
        "--suffix", help="Suffix added to the name of the output directory")
    args = parser.parse_args()

    output = args.output if args.output else timestamp()
    root = Path(name) / (output + (f"-{args.suffix}" if args.suffix else ""))
    root.mkdir(parents=True, exist_ok=True)
    with (root / "meta.json").open("w+") as f:
        values = {
            "args": vars(args),
            "sys": sys_info(),
            "git": git_info(vars(args)),
        }
        if custom:
            values["custom"] = custom
        json.dump(values, f)
    return args, root


def timestamp() -> str:
    return datetime.now().strftime("%y%m%d-%H%M%S")


def rm_ansi_escape(input: str) -> str:
    return ANSI_ESCAPE.sub("", input)


def non_block_read(output: IO[str]) -> str:
    fd = output.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    try:
        out = output.read()
    except:
        out = ""

    fcntl.fcntl(fd, fcntl.F_SETFL, fl)
    return out


BALLOON_CFG = {
    "base-manual": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(cores, mem, False),
    "base-auto": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(cores, mem, True),
    "huge-manual": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(cores, mem, False),
    "huge-auto": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(cores, mem, True),
    "llfree-manual": lambda cores, mem, _min_mem, _init_mem: qemu_llfree_balloon_args(cores, mem, False),
    "llfree-auto": lambda cores, mem, _min_mem, _init_mem: qemu_llfree_balloon_args(cores, mem, True),
    "virtio-mem-kernel": lambda _cores, mem, min_mem, init_mem: qemu_virtio_mem_args(mem, min_mem, init_mem, True),
    "virtio-mem-movable": lambda _cores, mem, min_mem, init_mem: qemu_virtio_mem_args(mem, min_mem, init_mem, False),
}

DEFAULT_KERNEL_CMD = "root=/dev/sda3 console=ttyS0 nokaslr"
def qemu_llfree_balloon_args(cores: int, mem: int, auto: bool) -> List[str]:
    per_core_iothreads = [f"iothread{c}" for c in range(cores)]
    auto_mode_iothread = "auto-mode-iothread"
    device = {
        "driver": "virtio-llfree-balloon",
        "auto-mode": auto,
        "ioctl": False,
        "auto-mode-iothread": auto_mode_iothread,
        "iothread-vq-mapping": [{"iothread": t} for t in per_core_iothreads],
    }
    return [
        "-m", f"{mem}G",
        "-append", DEFAULT_KERNEL_CMD,
        "-object", f"iothread,id={auto_mode_iothread}",
        *chain(*[["-object", f"iothread,id={t}"] for t in per_core_iothreads]),
        "-device", json.dumps(device),
    ]

def vfio_args(iommu_group: int | None) -> List[str]:
    if iommu_group is None:
        return []
    assert (Path("/dev/vfio") / str(iommu_group)).exists(), "IOMMU Group is not bound to VFIO!"
    path = Path("/sys/kernel/iommu_groups") / str(iommu_group) / "devices"
    return list(chain(*[
        ["-device", json.dumps({
            "driver": "vfio-pci", "host": d.name
        })] for d in path.iterdir()
    ]))

def qemu_virtio_balloon_args(cores: int, mem: int, auto: bool) -> List[str]:
    return ["-m", f"{mem}G","-append", DEFAULT_KERNEL_CMD,"-device", json.dumps({"driver": "virtio-balloon", "free-page-reporting": auto})]

def qemu_virtio_mem_args(mem: int, min_mem: int, init_mem: int, kernel: bool) -> List[str]:
    default_state = "online_kernel" if kernel else "online_movable"
    vmem_size = round(mem - min_mem)
    req_size = round(init_mem - min_mem)
    return [
        "-m", f"{min_mem}G,maxmem={mem}G",
        "-append", f"{DEFAULT_KERNEL_CMD} memhp_default_state={default_state}",
        "-machine", "pc",
        "-object", f"memory-backend-ram,id=vmem0,size={vmem_size}G,prealloc=off,reserve=off",
        "-device", f"virtio-mem-pci,id=vm0,memdev=vmem0,node=0,requested-size={req_size}G,prealloc=off"
    ]


def qemu_vm(
    qemu: str | Path = "qemu-system-x86_64",
    port: int = 5022,
    kernel: str = "bzImage",
    cores: int = 8,
    sockets: int = 1,
    hda: str = "resources/hda.qcow2",
    kvm: bool = True,
    qmp_port: int = 5023,
    extra_args: List[str] | None = None,
    env: Dict[str, str] | None = None,
    vfio_group: int | None = None
) -> Popen[str]:
    """Start a vm with the given configuration."""
    assert cores > 0 and cores % sockets == 0
    assert cores <= psutil.cpu_count()
    assert Path(hda).exists()

    assert sockets == 1, "not supported"

    if not extra_args:
        extra_args = []

    args = [
        qemu,
        #"-m", f"{mem}G",
        "-smp", f"{cores}",
        "-hda", hda,
        "-serial", "mon:stdio",
        "-nographic",
        "-kernel", kernel,
        "-qmp", f"tcp:localhost:{qmp_port},server=on,wait=off",
        "-nic", f"user,hostfwd=tcp:127.0.0.1:{port}-:22",
        "-no-reboot",
        "--cpu", "host",
        *extra_args,
        *vfio_args(vfio_group)
    ]

    if kvm:
        args.append("-enable-kvm")

    process = Popen(args, stdout=PIPE, stderr=STDOUT, text=True, env=env)

    # Pin qemu to a cpuset on one numa node with one core per vcpu
    CORES_NODE = psutil.cpu_count(logical=False) // 2
    cpu_set = list(map(lambda x: x * 2, range(0, min(cores, CORES_NODE))))
    if cores > CORES_NODE:
        cpu_set += list(map(lambda x: x * 2 + 1, list(range(0, cores - CORES_NODE))))

    q = psutil.Process(process.pid)
    q.cpu_affinity(cpu_set)

    return process


def qemu_wait_startup(qemu: Popen[str], logfile: Path):
    count = 0
    while True:
        sleep(3)
        assert qemu.poll() is None
        text = non_block_read(qemu.stdout)
        if len(text) == 0:
            # no changes in the past seconds
            # we either finished or paniced
            if count > 2:
                break
            count += 1
        else:
            count = 0
        with logfile.open("a+") as f:
            f.write(rm_ansi_escape(text))


class SSHExec:
    """Executing shell commands over ssh."""

    def __init__(self, user: str, host: str = "localhost", port: int = 22) -> None:
        self.user = user
        self.host = host
        self.port = port

    def _ssh(self) -> List[str]:
        return ["ssh", "-o StrictHostKeyChecking=no",
                f"{self.user}@{self.host}", f"-p {self.port}"]

    def run(self, cmd: str, timeout: Optional[float] = None, args: Optional[List[str]] = None):
        """Run cmd and wait for its termination"""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        check_call(ssh_args, timeout=timeout)

    def output(self, cmd: str, timeout: Optional[float] = None, args: Optional[List[str]] = None) -> str:
        """Run cmd and capture its output"""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        return check_output(ssh_args, text=True, stderr=STDOUT, timeout=timeout)

    def background(self, cmd: str, args: Optional[List[str]] = None) -> Popen[str]:
        """Run cmd in the background."""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        return Popen(ssh_args, stdout=PIPE, stderr=STDOUT, text=True)

    def upload(self, file: Path, target: str):
        """Upload a file over ssh."""
        check_call(
            ["scp", "-o StrictHostKeyChecking=no", f"-P{self.port}",
             file, f"{self.user}@{self.host}:{target}"], timeout=30)

    def download(self, source: Path, dest: Path):
        """Download a file over ssh."""
        check_call(
            ["scp", "-o StrictHostKeyChecking=no", f"-P{self.port}",
                f"{self.user}@{self.host}:{source}", dest], timeout=30)

def free_pages(buddyinfo: str) -> Tuple[int, int]:
    """Calculates the number of free small and huge pages from the buddy allocator state."""
    small = 0
    huge = 0
    for line in buddyinfo.splitlines():
        orders = line.split()[4:]
        for order, free in enumerate(orders):
            small += int(free) << order
            if order >= 9:
                huge += int(free) << (order - 9)
    return small, huge


def parse_meminfo(meminfo: str) -> Dict[str, int]:
    """Parses linux meminfo to a dict"""
    def parse_line(line: str) -> Tuple[str, int]:
        [k, v] = map(str.strip, line.split(":"))
        v = (int(v[:-3]) * 1024) if v.endswith(" kB") else int(v)
        return k, v

    return dict(map(parse_line, meminfo.strip().splitlines()))


def parse_zoneinfo(zoneinfo: str, key: str) -> int:
    res = 0
    for line in zoneinfo.splitlines():
        if (i := line.find(key)) >= 0:
            res += int(line[i + len(key) + 1:].strip())
    return res


def sys_info() -> dict:
    return {
        "uname": check_output(["uname", "-a"], text=True),
        "lscpu": json.loads(check_output(["lscpu", "--json"]))["lscpu"],
        "meminfo": mem_info(),
        "time": timestamp(),
    }


def mem_info() -> dict:
    meminfo = parse_meminfo(Path("/proc/meminfo").read_text())
    whitelist = {"MemTotal", "MemFree", "MemAvailable"}
    return { k: v for k, v in meminfo.items() if k in whitelist }


def git_info(args: Dict[str, Any]) -> Dict[str, Any]:
    def git_hash(path: Path) -> Dict[str, str]:
        if not path.exists():
            return {}

        path = path.resolve()
        if not path.is_dir():
            path = path.parent

        output = {"commit": "-", "remote": "-"}
        try:
            output["commit"] = check_output(
                ["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
        except Exception:
            pass
        try:
            output["remote"] = check_output(
                ["git", "remote", "get-url", "origin"], cwd=path, text=True).strip()
        except Exception:
            pass
        return output

    output = {"main": git_hash(Path(__file__))}
    for arg in args.values():
        if isinstance(arg, str):
            if hash := git_hash(Path(arg)):
                output[arg] = hash
    return output


def dump_dref(file: IO, prefix: str, data: Dict[str | int, Any]):
    for key, value in data.items():
        if isinstance(value, dict):
            dump_dref(file, f"{prefix}/{key}", value)
        elif isinstance(value, list):
            dump_dref(file, f"{prefix}/{key}", dict(enumerate(data)))
        else:
            file.write(f"\\drefset{{{prefix}/{key}}}{{{value}}}\n")


def dref_dataframe(name: str, dir: Path, groupby: List[str], data: pd.DataFrame):
    out = {}
    data = data.dropna(axis=0).groupby(groupby).mean(numeric_only=True)
    for index, row in data.iterrows():
        out["/".join(map(str, index))] = row.values[0]
    with (dir / f"{name}.dref").open("w+") as f:
        dump_dref(f, name, out)

def dref_dataframe_multi(name: str, dir: Path, groupby: List[str], vars: List[str], data: pd.DataFrame):
    out = {}
    for var in vars:
        ignored_cols = vars.copy()
        ignored_cols.remove(var)
        d = data[data.columns.difference(ignored_cols)].dropna(axis=0).groupby(groupby).mean(numeric_only=True)
        for index, row in d.iterrows():
            out["/".join(map(str, index)) + f"/{var}"] = row.values[0]

    with (dir / f"{name}.dref").open("w+") as f:
        dump_dref(f, name, out)
