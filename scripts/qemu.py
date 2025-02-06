from asyncio import sleep
from itertools import chain
import json
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen
import psutil
import sys

sys.path.append(str(Path(__file__).parent.parent))
from scripts.utils import non_block_read, rm_ansi_escape


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
    vfio_device: str | None = None,
    vfio_group: int | None = None,
    slice: str | None = None,
    core_start: int = 0,
) -> Popen[str]:
    """Start a vm with the given configuration."""
    assert cores > 0 and cores % sockets == 0

    logical = psutil.cpu_count(logical=True)
    physical = psutil.cpu_count(logical=False)
    assert logical is not None and physical is not None
    assert cores <= logical
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
        *vfio_dev_arg(vfio_device),
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
    step = 1
    if logical > physical:
        print("\033[31mWARNING: SMT detected, results might be less accurate!\033[0m")
        if (core_start + cores) <= physical:
            step = 2
            print("  \033[33mPinning on physical cores!\033[0m")
        else:
            print("  \033[33mPinning on logical cores!\033[0m")
    assert (core_start + cores * step) <= logical, "Not enough cores"

    cpu_set = [x * step for x in range(core_start, core_start + cores)]

    q = psutil.Process(process.pid)
    q.cpu_affinity(cpu_set)

    return process


def vfio_dev_arg(dev: str | None) -> list[str]:
    if not dev:
        return []
    if len(dev) < 12:
        dev = f"0000:{dev}"
    return ["-device", json.dumps({"driver": "vfio-pci", "host": dev})]


def vfio_args(iommu_group: int | None) -> list[str]:
    if iommu_group is None:
        return []
    assert (
        Path("/dev/vfio") / str(iommu_group)
    ).exists(), "IOMMU Group is not bound to VFIO!"
    path = Path("/sys/kernel/iommu_groups") / str(iommu_group) / "devices"
    return list(chain(*[vfio_dev_arg(d) for d in path.iterdir()]))


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
