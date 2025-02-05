# Artifact Evaluation

This document provides instructions for the artifact evaluation of the [EuroSys'25](https://sysartifacts.github.io/eurosys2025/call).

The artifact contains the necessary tools and resources required to evaluate our HyperAlloc VM reclamation.
It is packaged as a Docker image to simplify the evaluation and includes the different benchmarks from the paper, designed to stress the allocator in various scenarios.
It allows others to reproduce our experimental results from the paper.
Additionally, this artifact also contains the raw data used for the paper's figures.

As the artifact is packaged in a Docker image, the only prerequisites for the evaluation are:

- A Linux-based system (for KVM).
  - We have tested this on Debian 12 with Linux 6.1 and 6.2.
- At least 12 physical cores and 32GB RAM (more is better).
  - The multi-VM benchmarks require 24 physical cores and 48GB RAM.
- Hyperthreading and TurboBoost should be disabled for more stable results.
- A properly installed and running Docker daemon.
- For the VFIO benchmarks, we also need an IOMMU group that can be passed into a VM.


## Getting Started Instructions

This section aims to help you check the basic functionality of the artifact within a short time frame.
This includes pulling and starting the Docker image, and running the fastest of our benchmarks.

### Obtaining and Starting the Docker Image

Our Docker image is hosted on GitHub and can be pulled using the commands below.

To build the image run:
```sh
# Pull the docker image (only once)
docker pull ghcr.io/luhsra/hyperalloc_ae:latest
# (about 10min)
```

We want to use KVM inside the docker container.
Verify that you have the read/write permissions to `/dev/kvm` or else:
```sh
sudo chown $USER /dev/kvm
```

Start the image with:
```sh
./run.sh --device /dev/vfio/vfio --device /dev/vfio/<group> --ulimit memlock=53687091200:53687091200
```

> The `--device` and `--ulimit` parameters can be omitted if you want to skip the VFIO benchmarks.

Connect to the image with:
```sh
ssh -p2222 user@localhost
```

### Running a Fast Benchmark

After connecting to the container, you can execute a the "inflate" benchmark, which takes about 20min.

```sh
# (inside the container)
cd hyperalloc-bench
source venv/bin/activate

./run.py bench-plot -c inflate --fast
# (about 20min)
```

The results of this benchmark (raw data and plots) can be found in `~/hyperalloc-bench/artifact-eval/inflate`.
You can mount the container's content using sshfs with the [sshfs.sh](artifact-eval/sshfs.sh) script to access them.

```sh
# (outside the docker container)
./sshfs.sh
```


## Detailed Instructions

### VFIO and Device Passthrough

There are a few benchmarks that require device passthrough.
If you do not have a system supporting device passthrough, you can skip this step and the benchmarks by omitting the `--vfio <group>` argument for the `run.py` runner below.

As the device is not directly used (we only measure the general overheads of device passthrough), it does not matter what device it is.
For our measurements, we passed an Ethernet controller into the VMs.

Generally, you have to bind an IOMMU group from the HOST to VFIO and pass it into the docker container.
From there it is passed into the respective VMs.

The [/scripts/bind_vfio.py](/scripts/bind_vfio.py) script can bind IOMMU groups to VFIO (tested on Debian 12, Linux 6.1).
Executing it (outside the docker container), shows you all IOMMU groups and their corresponding devices.
You can then enter a group number to bind it to VFIO.
It should then be visible under `/dev/vfio/<group>`.

> If the script shows you no devices, ensure that the IOMMU on the host is enabled.
> For Intel systems this might require an additional kernel commandline parameter (`intel_iommu=on`), which you can add to your `/etc/default/grub` `GRUB_CMDLINE_LINUX_DEFAULT` config, for example.
>
> If this script fails for other reasons, you might have to do this [manually](https://www.kernel.org/doc/html/latest/driver-api/vfio.html#vfio-usage-example) for your respective Linux version.

The next step is to give the docker container access to the `/dev/vfio/<group>` device in the next section.


### Optional: Build the Artifacts

> The container contains pre-built artifact. So you can skip this step.

The docker image contains the following [Linux](https://github.com/luhsra/hyperalloc-linux) configs:
- Baseline Linux without modifications (used for virtio-balloon and virtio-mem).
- Linux with huge-pages for virtio-balloon-huge
- Linux with the LLFree allocator and HyperAlloc

The [linux-alloc-bench](https://github.com/luhsra/linux-alloc-bench/) kernel module is also built for the three configs.

For [QEMU](https://github.com/luhsra/hyperalloc-qemu/) we also have:
- Baseline QEMU without modifications (used for virtio-balloon and virtio-mem).
- QEMU with huge-pages for virtio-balloon-huge
- QEMU with the LLFree allocator and HyperAlloc

The following command builds all artifacts:

```sh
# (inside the container)
# cd hyperalloc-bench
# source venv/bin/activate

./run.py build
# (this builds three Linux kernels and QEMUs and usually takes about 1h)
```

The build artifacts are inside the build directories of `hyperalloc-linux`, `hyperalloc-qemu`, and `linux-alloc-bench`.


### Running the Benchmarks

These build targets are used for the following benchmark targets:

- `compiling`: Clang compilation with auto VM inflation (about 6h and +8h with `--extra`)
- `inflate`: Inflation/deflation latency (about 30min)
- `multivm`: Compiling clang on multiple concurrent VMs (about 10h)
- `stream`: STREAM memory bandwidth benchmark (about 30min)
- `ftq`: FTQ CPU work benchmark (about 30min)

They can be executed with:

```sh
# (inside the container)
# cd hyperalloc-bench
# source venv/bin/activate

./run.py bench-plot -b all --vfio <group>
# (sum of all benchmark times)
```

> For testing purposes, we would recommend executing the benchmarks with the `--fast` parameter first, which uses the [`write`](https://github.com/luhsra/llfree-rs/blob/main/bench/src/bin/write.rs) micro-benchmark instead of the hour-long clang compilation as workloads.

- `bench-plot` can be replaced with `bench` or `plot` to only run the benchmarks or redraw the plots.
- `all` can be replaced with a specific benchmark like `compiling`.
- If you want to run the additional `compile` benchmarks that evaluate the virtio-balloon parameters, add the `--extra` argument. This extends the runtime by about 8h.
- The VFIO `<group>` has to be the one passed into the docker container. You can omit this if you want to skip the VFIO benchmarks.


The results can be found in the `~/hyperalloc-bench/artifact-eval/<benchmark>` directory within the docker container.
The plots are directly contained in this directory.
The subdirectories contain the raw data and metadata, such as system, environment, and benchmark parameters.

The data from the paper is located in the `~/hyperalloc-bench/<benchmark>/latest` directories and the plots in `~/hyperalloc-bench/<benchmark>/out` (`<benchmark>` can be `compiling`, `inflate`, `multivm`, `stream`).
The `stream` directory also contains the `ftq` data.


## Exploring the Artifacts

This section might be helpful if you want to explore the contents of the docker container more easily.

The container has a running ssh server that allows you to create an `sshfs` mount.
This requires `sshfs` to be installed on your system.

```sh
# Mount the dockers home directory to your host machine
# (outside the docker container)
./sshfs.sh
```

Now, you can explore the `llfree_ae` directory with your file manager.
The home directory contains the following subdirectories:

- [hyperalloc-bench](https://github.com/luhsra/hyperalloc-bench): Collection of benchmark scripts for HyperAlloc.
  - `compiling`: Contains the clang auto reclamation benchmark.
  - `inflate`: Contains the inflate/deflate latency benchmark.
  - `multivm`: Contains the multi-VM benchmarks.
  - `stream`: Contains the STREAM and FTQ benchmarks.
- [hyperalloc-qemu](https://github.com/luhsra/hyperalloc-qemu): The QEMU with integrated HyperAlloc.
- [hyperalloc-linux](https://github.com/luhsra/hyperalloc-linux): The Linux Kernel with integrated HyperAlloc.
- [hyperalloc-stream](https://github.com/luhsra/hyperalloc-stream): The STREAM memory bandwidth benchmark.
- [hyperalloc-ftq](https://github.com/luhsra/hyperalloc-ftq): The FTQ CPU work benchmark.
- [linux-alloc-bench](https://github.com/luhsra/linux-alloc-bench): Kernel module for benchmarking the page allocator.


## Disk Image

The disk image used for the VMs is based on the [debian-12-nocloud-amd64.qcow2](https://www.debian.org/distrib/) cloud image.
It contains the `hyperalloc-stream`, `hyperalloc-ftq`, and [clang 16.0.0](https://releases.llvm.org/).
Additionally, it contains the pre-build [write](https://github.com/luhsra/llfree-rs/blob/main/bench/src/bin/write.rs) benchmark from the `llfree-rs` repository.
