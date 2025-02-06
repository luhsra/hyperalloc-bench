#!/usr/bin/env python3

from subprocess import check_output, check_call
from pathlib import Path
from time import sleep
from argparse import ArgumentParser

GROUPS = Path("/sys/kernel/iommu_groups")

# Show all groups and devices
def list_groups():
    for group in sorted(GROUPS.iterdir(), key=lambda p: int(p.name)):
        print(group.name)
        for device in sorted((group / "devices").iterdir()):
            print(" ", check_output(["lspci", "-nns", device.name], text=True).strip())

# Pass all devices from the group to VFIO
def pass_to_vfio(group: Path):
    devices = list(sorted((group / "devices").iterdir()))

    if len(devices) > 1:
        print("Group has more than one device. Select one to pass through or 'all'")
        for i, device in enumerate(devices):
            print(f"  {i}: {check_output(['lspci', '-nns', device.name], text=True).strip()}")
        response = input("Device: ").strip()
        if response != "all":
            selected = int(response)
            devices = [devices[selected]]

    for device in devices:
        (device / "driver/unbind").write_text(device.name)
        check_call(["modprobe", "vfio-pci"])
        (device / "driver_override").write_text("vfio-pci")
        Path("/sys/bus/pci/drivers_probe").write_text(device.name)

    sleep(1)

    # Give us access
    check_call(["chmod", "-R", "go+rw", "/dev/vfio"])

if __name__ == "__main__":
    parser = ArgumentParser(description="Rebind an IOMMU group to VFIO")
    parser.add_argument("-g", "--group", type=int,
                        help="ID of the IOMMU group to rebind")
    parser.add_argument("-l", "--list", action="store_true",
                        help="Just list the IOMMU groups")
    args = parser.parse_args()

    group = None
    if args.group is None:
        list_groups()
        if args.list:
            exit(0)

        selected = int(input("Group id: ").strip())
        group = GROUPS / str(selected)
    else:
        group = GROUPS / str(args.group)

    if group is None or not group.exists():
        print("Invalid group id")
        exit(1)

    pass_to_vfio(group)
