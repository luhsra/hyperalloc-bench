# HyperAlloc Benchmarks

This repository contains the benchmarks and results for the HyperAlloc memory reclamation approach.

## Publication

HyperAlloc: Efficient VM Memory De/Inflation via Hypervisor-Shared Page-Frame Allocators
Lars Wrenger, Kenny Albes, Marco Wurps, Christian Dietrich, Daniel Lohmann
In: Proceedings of the 20th European Conference on Computer Systems (EuroSys 2025); ACM

## Benchmark Data & Visualization

Setup `venv` and dependencies:

```sh
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

Run benchmark:

```sh
sudo -E ./max_power.sh python compiling.py --qemu <path/to/qemu> --kernel <path/to/bzImage> --img <path/to/disk.qcow2> -c 8 -m 8 --suffix demo
```

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
