# HyperAlloc Benchmarks

This repository contains the benchmarks and results for the HyperAlloc memory reclamation approach.

## Publication

HyperAlloc: Efficient VM Memory De/Inflation via Hypervisor-Shared Page-Frame Allocators
Lars Wrenger, Kenny Albes, Marco Wurps, Christian Dietrich, Daniel Lohmann
In: Proceedings of the 20th European Conference on Computer Systems (EuroSys 2025); ACM

## Benchmark Data & Visualization

The benchmarks have been developed and tested on Linux 6.1 (Debian 12) for host and guest, and QEMU 8.2.50.
Even though they should be mostly compatible with other Linux versions, VFIO might work slightly different.

Setup `venv` and install dependencies:

```sh
python3 -m venv venv
source ./venv/bin/activate
pip3 install -e .
```

Run a benchmark:

```sh
sudo -E ./max_power.sh python compiling/compiling.py --mode <mode> --img <path/to/disk.qcow2> -c 8 -m 8
```

The `mode` specifies the paths to the guest kernel and QEMU to be used. You can manually overwrite them with the `--kernel` and `--qemu` arguments.
The benchmark `mode` can be one of the following:
- `base-manual`: Unmodified QEMU and guest with manual virtio-balloon
- `base-auto`: Unmodified QEMU and guest with enabled free-page-reporting
- `huge-manual`: Modified QEMU and guest which use huge pages instead of base pages for ballooning
- `virtio-mem-movable`: Unmodified QEMU and guest with enabled virtio-mem, that adds movable memory
- `llfree-manual`: Modified QEMU and guest with integrated LLFree and manual reclamation.
- `llfree-auto`: Modified QEMU and guest with integrated LLFree and auto reclamation.

The disk image is expected to contain a debian 12 with a password-less "debian" user.
Also the compile and multivm benchmarks expect a checked out [clang 16.0.0](https://releases.llvm.org/) repository at `~/clang`.
The stream and ftq benchmarks require the [STREAM]() and [ftq]() repos at `~/STREAM` and `~/ftq`.


## VFIO

Some benchmarks require VFIO devices.
We would recommend using networks cards.
For binding device groups to VFIO use `bind_vfio.py`, which lists all available groups and allows you to choose one.

```sh
sudo python3 bind_vfio.py
```

> This only works if your system supports IOMMUs and for Intel, the IOMMUs have to be activated via the kernel commandline `intel_iommu=on`.

Then the vfio-group can be given to the benchmark, which then passes it through to the VMs.

```sh
sudo -E ./max_power.sh python compiling.py ... --vfio <group-number>
```
