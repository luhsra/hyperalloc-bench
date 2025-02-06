from argparse import Namespace
import asyncio
from asyncio import Task, sleep
from collections.abc import Callable, Coroutine
from math import nan
from pathlib import Path
from subprocess import CalledProcessError, Popen
from time import time
from psutil import Process
import sys

sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils import (
    SSHExec,
    free_pages,
    non_block_read,
    parse_meminfo,
    parse_zoneinfo,
    rm_ansi_escape,
)


class Measure:
    def __init__(
        self,
        root: Path,
        i: int,
        ssh: SSHExec,
        ps_proc: Process,
        args: Namespace,
        time_start: float | None = None,
        callback: Callable[[float, float], Coroutine] | None = None,
    ) -> None:
        self.i = i
        self.ssh = ssh
        self.root = root
        self.args = args
        self.callback = callback
        self.ps_proc = ps_proc

        # A bit of memory is reserved for kernel stuff
        self._reserved_mem = None
        with (self.root / f"out_{self.i}.csv").open("a+") as mem_usage:
            mem_usage.write("time,rss,small,huge,cached,total\n")

        times = self.ps_proc.cpu_times()
        self._times_user = times.user
        self._times_system = times.system
        self._time = time_start or time()
        self._vm_stats_task: Task[tuple[float, float, float, float]] | None = None
        self._callback_task: Task | None = None
        self._errors = 0

    async def __call__(
        self, process: Popen[str] | asyncio.subprocess.Process | None = None
    ):
        if self._reserved_mem == None:
            z = await self.ssh.output("cat /proc/zoneinfo")
            self._reserved_mem = (
                parse_zoneinfo(z, "present ") - parse_zoneinfo(z, "managed ")
            ) * 2**12

        small, huge, cached, total = nan, nan, nan, nan
        if self._vm_stats_task is None:
            self._vm_stats_task = asyncio.create_task(self.vm_stats())
        done, _ = await asyncio.wait({self._vm_stats_task}, timeout=1)
        if self._vm_stats_task in done:
            small, huge, cached, total = await self._vm_stats_task
            self._vm_stats_task = None

        sec = self.sec()
        rss = self.ps_proc.memory_info().rss
        with (self.root / f"out_{self.i}.csv").open("a+") as mem_usage:
            mem_usage.write(f"{sec:.2f},{rss},{small},{huge},{cached},{total}\n")

        if self.args.frag:
            output = await self.ssh.output("cat /proc/llfree_frag")
            (self.root / f"frag_{self.i}_{sec:.2f}.txt").write_text(output)

        if process is not None:
            with (self.root / f"out_{self.i}.txt").open("a+") as f:
                if isinstance(process, Popen):
                    f.write(rm_ansi_escape(non_block_read(process.stdout)))
                elif isinstance(process, asyncio.subprocess.Process) and process.stdout:
                    try:
                        async with asyncio.timeout(0.5):
                            out = await process.stdout.read(4096)
                            f.write(rm_ansi_escape(out.decode(errors="replace")))
                    except asyncio.TimeoutError:
                        pass

        if self.callback is not None:
            await self.callback(small, huge)

    async def vm_stats(self) -> tuple[float, float, float, float]:
        try:
            small, huge = free_pages(
                await self.ssh.output("cat /proc/buddyinfo", timeout=30)
            )
            meminfo = parse_meminfo(
                await self.ssh.output("cat /proc/meminfo", timeout=30)
            )
            total = meminfo["MemTotal"] + (self._reserved_mem or 0)
            cached = meminfo["Cached"]
            self._errors = 0
            return small, huge, total, cached
        except CalledProcessError as e:
            print("VM Stats Error")
            assert self.ps_proc.is_running()
            self._errors += 1
            if self._errors > 5:
                print("Too many errors!")
                raise e
            return nan, nan, nan, nan
        except asyncio.TimeoutError as e:
            print("VM Stats Timeout")
            assert self.ps_proc.is_running()
            self._errors += 1
            if self._errors > 5:
                print("Too many errors!")
                raise e
            return nan, nan, nan, nan

    def sec(self) -> float:
        return time() - self._time

    async def wait(
        self,
        sec: float | None = None,
        task: Task | None = None,
        condition: Callable[[], bool] | None = None,
        process: Popen[str] | asyncio.subprocess.Process | None = None,
    ) -> float:
        if isinstance(process, asyncio.subprocess.Process):
            task = asyncio.create_task(process.wait())

        if task is not None:
            while not task.done():
                await self(process)
                await sleep(1)
        elif sec is not None:
            wait_end = self.sec() + sec
            while self.sec() < wait_end:
                await self(process)
                await sleep(1)
        elif condition is not None:
            while condition():
                await self(process)
                await sleep(1)
        return self.sec()

    def times(self) -> tuple[float, float, float]:
        """Returns (total, user, system) times in s"""
        times = self.ps_proc.cpu_times()
        return (
            time() - self._time,
            times.user - self._times_user,
            times.system - self._times_system,
        )
