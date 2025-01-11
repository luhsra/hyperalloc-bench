from argparse import Namespace
import asyncio
from asyncio import Task, sleep
from collections.abc import Callable
from pathlib import Path
from subprocess import CalledProcessError, Popen
from time import time
from typing import IO, Any
from psutil import Process
from vm_resize import VMResize
from utils import (
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
        i: int,
        ssh: SSHExec,
        ps_proc: Process,
        root: Path,
        mem_usage: IO[str],
        args: Namespace,
        vm_resize: VMResize | None = None,
    ) -> None:
        self.i = i
        self.ssh = ssh
        self.vm_resize = vm_resize
        self.ps_proc = ps_proc
        self.root = root
        self.mem_usage = mem_usage
        self.args = args

        # A bit of memory is reserved for kernel stuff
        self._reserved_mem = None
        self.mem_usage.write("time,rss,small,huge,cached,total\n")
        self.mem_usage.flush()

        times = self.ps_proc.cpu_times()
        self._times_user = times.user
        self._times_system = times.system
        self._time = time()
        self._vm_stats_task: Task[tuple[int, int, int, int]] | None = None

    async def __call__(
        self, process: Popen[str] | asyncio.subprocess.Process | None = None
    ):
        sec = self.sec()

        if self._reserved_mem == None:
            zoneinfo = await self.ssh.output("cat /proc/zoneinfo")
            self._reserved_mem = (
                parse_zoneinfo(zoneinfo, "present ")
                - parse_zoneinfo(zoneinfo, "managed ")
            ) * 2**12

        small, huge, cached, total = 0, 0, 0, 0
        if self._vm_stats_task is None:
            self._vm_stats_task = asyncio.create_task(self.vm_stats())
        done, _ = await asyncio.wait({self._vm_stats_task}, timeout=0.5)
        if self._vm_stats_task in done:
            small, huge, cached, total = await self._vm_stats_task
            self._vm_stats_task = None

        rss = self.ps_proc.memory_info().rss
        self.mem_usage.write(f"{sec:.2f},{rss},{small},{huge},{cached},{total}\n")
        self.mem_usage.flush()

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
                            f.write(rm_ansi_escape(out.decode()))
                    except asyncio.TimeoutError:
                        pass

        # resize vm
        if self.vm_resize is not None and self.args.mode.startswith("virtio-mem-"):
            # Follow free huge pages
            free = int(huge * 2 ** (12 + 9) * 0.9)  # 10% above huge pages
            # free = small * 2**12 * 0.9 # 10% above small pages
            # Step size, amount of mem that is plugged/unplugged
            step = round(self.vm_resize.max * self.args.vmem_fraction)
            if free < step / 2:  # grow faster
                await self.vm_resize.set(self.vm_resize.size + 2 * step)
            elif free < step:
                await self.vm_resize.set(self.vm_resize.size + step)
            elif free > 2 * step:
                await self.vm_resize.set(self.vm_resize.size - step)

    async def vm_stats(self) -> tuple[int, int, int, int]:
        try:
            small, huge = free_pages(await self.ssh.output("cat /proc/buddyinfo"))
            meminfo = parse_meminfo(await self.ssh.output("cat /proc/meminfo"))
            total = meminfo["MemTotal"] + (self._reserved_mem or 0)
            cached = meminfo["Cached"]
            return small, huge, total, cached
        except CalledProcessError as e:
            print("VM Stats Error:", e)
            return 0, 0, 0, 0

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
