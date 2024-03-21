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


def qemu_llfree_balloon_args(cores: int, auto: bool, guest_triggered: bool) -> List[str]:
    per_core_iothreads = [f"iothread{c}" for c in range(cores)]
    auto_mode_iothread = "auto-mode-iothread"
    api_mode_iothread = "api-triggered-mode-iothread"
    device = {
        "driver": "virtio-llfree-balloon",
        "auto-mode": auto,
        "guest-triggered-deflate": auto and guest_triggered,
        "allocating-deflate": auto and guest_triggered,
        "auto-mode-iothread": auto_mode_iothread,
        "api-triggered-mode-iothread": api_mode_iothread,
        "iothread-vq-mapping": [{"iothread": t} for t in per_core_iothreads],
    }
    return [
        "-object", f"iothread,id={auto_mode_iothread}",
        "-object", f"iothread,id={api_mode_iothread}",
        *chain(*[["-object", f"iothread,id={t}"] for t in per_core_iothreads]),
        "-device", json.dumps(device)
    ]

def qemu_virtio_balloon_args(cores: int, auto: bool) -> List[str]:
    return ["-device", json.dumps({"driver": "virtio-balloon", "free-page-reporting": auto})]


def qemu_vm(
    qemu: str | Path = "qemu-system-x86_64",
    port: int = 5022,
    kernel: str = "bzImage",
    mem: int = 8,
    cores: int = 8,
    sockets: int = 1,
    delay: int = 15,
    hda: str = "resources/hda.qcow2",
    kvm: bool = True,
    extra_args: Optional[List[str]] = None
) -> Popen[str]:
    """
    Start a vm with the given configuration.
    """
    assert cores > 0 and cores % sockets == 0
    assert cores <= psutil.cpu_count()
    assert mem > 0 and mem % sockets == 0
    assert Path(hda).exists()

    # every nth cpu
    def cpus(i) -> str:
        return ",".join([
            f"cpus={c}" for c in range(i, cores, sockets)
        ])

    max_mem = mem + sockets
    slots = sockets
    if not extra_args:
        extra_args = []

    args = [
        qemu,
        "-m", f"{mem}G,slots={slots},maxmem={max_mem}G",
        "-smp", f"{cores},sockets={sockets},maxcpus={cores}",
        "-hda", hda,
        "-machine", "pc,accel=kvm,nvdimm=on",
        "-serial", "mon:stdio",
        "-nographic",
        "-kernel", kernel,
        "-append", "root=/dev/sda1 console=ttyS0 nokaslr",
        "-nic", f"user,hostfwd=tcp:127.0.0.1:{port}-:22",
        "-no-reboot",
        "--cpu", "host,-rdtscp",
        *chain(*[["-numa", f"node,{cpus(i)},nodeid={i},memdev=m{i}"]
                 for i in range(sockets)]),
        *chain(*[["-object", f"memory-backend-ram,size={mem // sockets}G,id=m{i}"]
                 for i in range(sockets)]),
        *extra_args,
    ]

    if kvm:
        args.append("-enable-kvm")

    process = Popen(args, stdout=PIPE, stderr=STDOUT, text=True)

    # wait for startup
    sleep(delay)

    return process


class SSHExec:
    """
    Executing shell commands over ssh.
    """

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


def mem_cached(meminfo: str) -> int:
    """Returns the amount of cached memory in bytes"""
    for line in meminfo.splitlines():
        if line.startswith("Cached:"):
            return int(line.split()[1]) * 1024
    raise Exception("invalid meminfo")


def sys_info() -> dict:
    return {
        "uname": check_output(["uname", "-a"], text=True),
        "lscpu": json.loads(check_output(["lscpu", "--json"]))["lscpu"],
        "meminfo": mem_info(),
    }


def mem_info() -> dict:
    rows = {"MemTotal", "MemFree", "MemAvailable"}
    out = {}
    for row in open("/proc/meminfo"):
        try:
            [key, value] = list(map(lambda v: v.strip(), row.split(":")))
            if key in rows:
                out[key] = value
        except:
            pass
    return out


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
