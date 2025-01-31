import asyncio
from collections.abc import Iterable, Sequence
import fcntl
import json
import os
import re
from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from subprocess import CalledProcessError, Popen, PIPE, STDOUT, check_output
from typing import IO, Any

import pandas as pd

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def setup(
    parser: ArgumentParser, argv: Sequence[str] | None = None, custom=None
) -> tuple[Namespace, Path]:
    """
    Setup the benchmark directory and save the system config and execution parameters.

    Args:
        name: Name of the benchmark
        parser: CLI Arguments to be parsed and saved
        custom: Any custom metadata that should be saved
    """
    parser.add_argument("--output", help="Name of the output directory")
    parser.add_argument("--suffix", help="Suffix added to the output directory")
    args = parser.parse_args(argv)

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
                raise CalledProcessError(
                    process.returncode, ssh_args, stdout.decode(errors="replace")
                )
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
