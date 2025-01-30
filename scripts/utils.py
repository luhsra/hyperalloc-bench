import asyncio
from collections.abc import Callable, Iterable
import fcntl
import json
import os
import re
import psutil
from argparse import ArgumentParser, Namespace
from datetime import datetime
from itertools import chain
from pathlib import Path
from subprocess import CalledProcessError, Popen, PIPE, STDOUT, check_call, check_output
from asyncio import sleep
from typing import IO, Any

import pandas as pd

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def setup(name: str, parser: ArgumentParser, custom=None) -> tuple[Namespace, Path]:
    """
    Setup the benchmark directory and save the system config and execution parameters.

    Args:
        name: Name of the benchmark
        parser: CLI Arguments to be parsed and saved
        custom: Any custom metadata that should be saved
    """
    parser.add_argument("--output", help="Name of the output directory")
    parser.add_argument("--suffix", help="Suffix added to the output directory")
    args = parser.parse_args()

    output = args.output if args.output else timestamp()
    root = Path("results") / (output + (f"-{args.suffix}" if args.suffix else ""))
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


def non_block_read(output: IO[str] | None) -> str:
    if output is None:
        return ""

    fd = output.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    try:
        out = output.read()
    except:
        out = ""

    fcntl.fcntl(fd, fcntl.F_SETFL, fl)
    return out


def fmt_bytes(bytes: int) -> str:
    suffix = ["GiB", "MiB", "KiB"]
    for i, s in enumerate(suffix):
        fac = 1024 ** (len(suffix) - i)
        if bytes >= fac:
            return f"{bytes / fac:.2f} {s}"
    return f"{bytes} B"


BALLOON_CFG: dict[str, Callable[[int, int, int, int], list[str]]] = {
    "base-manual": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, False
    ),
    "base-auto": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, True
    ),
    "huge-manual": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, False
    ),
    "huge-auto": lambda cores, mem, _min_mem, _init_mem: qemu_virtio_balloon_args(
        cores, mem, True
    ),
    "llfree-manual": lambda cores, mem, _min_mem, _init_mem: qemu_llfree_balloon_args(
        cores, mem, False
    ),
    "llfree-auto": lambda cores, mem, _min_mem, _init_mem: qemu_llfree_balloon_args(
        cores, mem, True
    ),
    "virtio-mem-kernel": lambda _cores, mem, min_mem, init_mem: qemu_virtio_mem_args(
        mem, min_mem, init_mem, True
    ),
    "virtio-mem-movable": lambda _cores, mem, min_mem, init_mem: qemu_virtio_mem_args(
        mem, min_mem, init_mem, False
    ),
}


def qemu_llfree_balloon_args(cores: int, mem: int, auto: bool) -> list[str]:
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
        "-m",
        f"{mem}G",
        "-object",
        f"iothread,id={auto_mode_iothread}",
        *chain(*[["-object", f"iothread,id={t}"] for t in per_core_iothreads]),
        "-device",
        json.dumps(device),
    ]


def vfio_args(iommu_group: int | None) -> list[str]:
    if iommu_group is None:
        return []
    assert (
        Path("/dev/vfio") / str(iommu_group)
    ).exists(), "IOMMU Group is not bound to VFIO!"
    path = Path("/sys/kernel/iommu_groups") / str(iommu_group) / "devices"
    return list(
        chain(
            *[
                ["-device", json.dumps({"driver": "vfio-pci", "host": d.name})]
                for d in path.iterdir()
            ]
        )
    )


def qemu_virtio_balloon_args(cores: int, mem: int, auto: bool) -> list[str]:
    return [
        "-m",
        f"{mem}G",
        "-device",
        json.dumps({"driver": "virtio-balloon", "free-page-reporting": auto}),
    ]


def qemu_virtio_mem_args(
    mem: int, min_mem: int, init_mem: int, kernel: bool
) -> list[str]:
    default_state = "online_kernel" if kernel else "online_movable"
    vmem_size = round(mem - min_mem)
    req_size = round(init_mem - min_mem)
    return [
        # fmt: off
        "-m", f"{min_mem}G,maxmem={mem}G",
        "-append", f"memhp_default_state={default_state}",
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
    extra_args: list[str] | None = None,
    env: dict[str, str] | None = None,
    vfio_group: int | None = None,
    slice: str | None = None,
    core_start: int = 0,
) -> Popen[str]:
    """Start a vm with the given configuration."""
    assert cores > 0 and cores % sockets == 0
    assert cores <= psutil.cpu_count()
    assert Path(hda).exists()

    assert sockets == 1, "not supported"

    if not extra_args:
        extra_args = []

    base_args = [
        # fmt: off
        qemu,
        #"-m", f"{mem}G",
        "-smp", f"{cores}",
        "-hda", hda,
        "-snapshot",
        "-serial", "mon:stdio",
        "-nographic",
        "-kernel", kernel,
        "-append", "root=/dev/sda3 console=ttyS0 nokaslr",
        "-qmp", f"tcp:localhost:{qmp_port},server=on,wait=off",
        "-nic", f"user,hostfwd=tcp:127.0.0.1:{port}-:22",
        "-no-reboot",
        "--cpu", "host",
        *extra_args,
        *vfio_args(vfio_group),
    ]

    if slice:
        base_args = ["systemd-run", "--user", "--slice", slice, "--scope", *base_args]

    # Combine `-append`
    args = []
    cmdline = []
    is_append = False
    for arg in base_args:
        if is_append:
            cmdline.append(arg)
        elif arg != "-append":
            args.append(arg)
        is_append = arg == "-append"
    args += ["-append", " ".join(cmdline)]

    if kvm:
        args.append("-enable-kvm")

    process = Popen(args, stdout=PIPE, stderr=STDOUT, text=True, env=env)

    # Pin qemu to a cpuset on one numa node with one core per vcpu
    logical = psutil.cpu_count(logical=True)
    physical = psutil.cpu_count(logical=False)
    step = 1
    if logical > physical:
        print("\033[31mWARNING: SMT detected!\033[0m")
        step = 2
    assert cores <= physical, "Not enough cores"

    cpu_set = [x * step for x in range(core_start, core_start + cores)]

    q = psutil.Process(process.pid)
    q.cpu_affinity(cpu_set)

    return process


async def qemu_wait_startup(qemu: Popen[str], logfile: Path):
    count = 0
    while True:
        await sleep(3)
        assert qemu.poll() is None
        text = non_block_read(s) if (s := qemu.stdout) else ""
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

    def _ssh(self) -> list[str]:
        return [
            "ssh",
            "-o NoHostAuthenticationForLocalhost=yes",
            f"{self.user}@{self.host}",
            f"-p {self.port}",
        ]

    async def run(
        self, cmd: str, timeout: float | None = None, args: list[str] | None = None
    ):
        """Run cmd and wait for its termination"""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        async with asyncio.timeout(timeout):
            process = await asyncio.create_subprocess_exec(*ssh_args)
            if (ret := await process.wait()) != 0:
                raise CalledProcessError(ret, ssh_args)

    async def output(
        self, cmd: str, timeout: float | None = None, args: list[str] | None = None
    ) -> str:
        """Run cmd and capture its output"""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        async with asyncio.timeout(timeout):
            process = await asyncio.create_subprocess_exec(
                *ssh_args, stdout=PIPE, stderr=STDOUT
            )
            stdout, _ = await process.communicate()
            if process.returncode != 0:
                raise CalledProcessError(process.returncode, ssh_args, stdout.decode(errors="replace"))
            return stdout.decode(errors="replace")

    async def process(
        self, cmd: str, args: list[str] | None = None
    ) -> asyncio.subprocess.Process:
        """Run cmd and return the process"""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        return await asyncio.create_subprocess_exec(
            *ssh_args, stdout=PIPE, stderr=STDOUT
        )

    # Deprecated: Use coroutines instead
    def background(self, cmd: str, args: list[str] | None = None) -> Popen[str]:
        """Run cmd in the background."""
        if not args:
            args = []
        ssh_args = [*self._ssh(), *args, cmd]
        return Popen(ssh_args, stdout=PIPE, stderr=STDOUT, text=True)

    async def upload(self, source: Path, dest: str):
        """Upload a file over ssh."""
        async with asyncio.timeout(30):
            ssh_args = [
                # fmt: off
                "scp", "-o NoHostAuthenticationForLocalhost=yes", f"-P{self.port}",
                source, f"{self.user}@{self.host}:{dest}",
            ]
            process = await asyncio.create_subprocess_exec(*ssh_args)
            if (ret := await process.wait()) != 0:
                raise CalledProcessError(ret, ssh_args)

    async def download(self, source: Path, dest: Path):
        """Download a file over ssh."""
        async with asyncio.timeout(30):
            ssh_args = [
                # fmt: off
                "scp", "-o NoHostAuthenticationForLocalhost=yes", f"-P{self.port}",
                f"{self.user}@{self.host}:{source}", dest,
            ]
            process = await asyncio.create_subprocess_exec(*ssh_args)
            if (ret := await process.wait()) != 0:
                raise CalledProcessError(ret, ssh_args)


def free_pages(buddyinfo: str) -> tuple[int, int]:
    """Calculates the number of free small and huge pages from the buddy allocator state."""
    try:
        small = 0
        huge = 0
        for line in buddyinfo.splitlines():
            orders = line.split()[4:]
            for order, free in enumerate(orders):
                small += int(free) << order
                if order >= 9:
                    huge += int(free) << (order - 9)
        return small, huge
    except Exception as e:
        print(f"Invalid buddyinfo: '{buddyinfo}'")
        raise e


def parse_meminfo(meminfo: str) -> dict[str, int]:
    """Parses linux meminfo to a dict"""

    def parse_line(line: str) -> tuple[str, int]:
        [k, v] = map(str.strip, line.split(":"))
        v = (int(v[:-3]) * 1024) if v.endswith(" kB") else int(v)
        return k, v

    try:
        return dict(map(parse_line, meminfo.strip().splitlines()))
    except Exception as e:
        print(f"Invalid meminfo: '{meminfo}'")
        raise e


def parse_zoneinfo(zoneinfo: str, key: str) -> int:
    res = 0
    for line in zoneinfo.splitlines():
        if (i := line.find(key)) >= 0:
            res += int(line[i + len(key) + 1 :].strip())
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
    whitelist = {"MemTotal", "MemFree", "MemAvailable", "Cached"}
    return {k: v for k, v in meminfo.items() if k in whitelist}


def git_info(args: dict[str, object]) -> dict[str, Any]:
    def git_hash(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}

        path = path.resolve()
        if not path.is_dir():
            path = path.parent

        output = {"commit": "-", "remote": "-"}
        try:
            output["commit"] = check_output(
                ["git", "rev-parse", "HEAD"], cwd=path, text=True
            ).strip()
        except Exception:
            pass
        try:
            output["remote"] = check_output(
                ["git", "remote", "get-url", "origin"], cwd=path, text=True
            ).strip()
        except Exception:
            pass
        return output

    output = {"main": git_hash(Path(__file__))}
    for arg in args.values():
        if isinstance(arg, str):
            if hash := git_hash(Path(arg)):
                output[arg] = hash
    return output


def dump_dref(file: IO, prefix: str, data: dict[str | int | float, Any]):
    for key, value in data.items():
        if isinstance(value, dict):
            dump_dref(file, f"{prefix}/{key}", value)
        elif isinstance(value, list) or isinstance(value, tuple):
            dump_dref(file, f"{prefix}/{key}", dict(enumerate(data)))
        else:
            file.write(f"\\drefset{{{prefix}/{key}}}{{{value}}}\n")


def dref_dataframe(name: str, dir: Path, groupby: list[str], data: pd.DataFrame):
    out = {}
    data = data.dropna(axis=0).groupby(groupby).mean(numeric_only=True)
    for index, row in data.iterrows():
        if isinstance(index, Iterable):
            index = "/".join(map(str, index))
        out[f"{index}"] = row.values[0]

    with (dir / f"{name}.dref").open("w+") as f:
        dump_dref(f, name, out)


def dref_dataframe_multi(
    name: str, dir: Path, groupby: list[str], vars: list[str], data: pd.DataFrame
):
    out = {}
    for var in vars:
        ignored_cols = vars.copy()
        ignored_cols.remove(var)
        d = (
            data[data.columns.difference(ignored_cols)]
            .dropna(axis=0)
            .groupby(groupby)
            .mean(numeric_only=True)
        )
        for index, row in d.iterrows():
            if isinstance(index, Iterable):
                index = "/".join(map(str, index))
            out[f"{index}" + f"/{var}"] = row.values[0]

    with (dir / f"{name}.dref").open("w+") as f:
        dump_dref(f, name, out)
