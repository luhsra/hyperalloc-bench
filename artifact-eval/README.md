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
  - Lower specifications should work, but the results may be less meaningful.
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
sudo chown /dev/kvm $USER
```

Start the image with:
```sh
./run.sh
```

Connect to the image with:
```sh
ssh -p2222 user@localhost
```

### Running the First Benchmark

Our paper contains five general benchmarks:
- `compiling`: Clang compilation with auto VM inflation
- `inflate`: Inflation/deflation latency
- `multivm`: Compiling clang on multiple concurrent VMs
- `stream`: STREAM memory bandwidth benchmark
- `ftq`: FTQ CPU work benchmark (also in the `stream` directory)

After connecting to the docker image, you can build and run the benchmarks with the `run.py` script.

The fastest benchmark is the `inflate` benchmark, which benchmarks latency of the VM inflation/deflation.
Start it with the following command:

```sh
# within the docker image (ssh)
cd hyperalloc-bench
source ./venv/bin/activate

./run.py bench-plot inflate --short
# (about 15m)
```

> We recommend disabling hyper-threading and turbo-boost for the benchmarks.

This command executes the benchmarks and generates the corresponding plots.
The results can be found in `~/hyperalloc-bench/artifact-eval/inflate` within the docker container.
The plots are directly contained in this directory.
The subdirectories contain the raw data and metadata, such as system, environment, and benchmark parameters.

The data from the paper is located in the `~/hyperalloc-bench/<benchmark>/latest` directories and the plots in `~/hyperalloc-bench/<benchmark>/out` (`<benchmark>` can be `compiling`, `inflate`, `multivm`, `stream`).
The `stream` directory also contains the `ftq` data.


## Detailed Instructions

This section contains detailed information on executing all the paper's evaluation benchmarks.

### Optional: Build the Artifacts

The docker image contains the following [Linux](https://github.com/luhsra/hyperalloc-linux) build targets:
- **linux-base**: Baseline Linux without modifications (used for virtio-balloon and virtio-mem).
- **linux-huge**: Linux with huge-pages for virtio-balloon-huge
- **linux-llfree**: Linux with the LLFree allocator and HyperAlloc

For [QEMU](https://github.com/luhsra/hyperalloc-qemu/) we have matching variants:
- **qemu-base**: Baseline QEMU without modifications (used for virtio-balloon and virtio-mem).
- **qemu-huge**: QEMU with huge-pages for virtio-balloon-huge
- **qemu-llfree**: QEMU with the LLFree allocator and HyperAlloc

For the [linux-alloc-bench](https://github.com/luhsra/linux-alloc-bench/) kernel module we have matching variants:
- **module-base**: Baseline QEMU without modifications (used for virtio-balloon and virtio-mem).
- **module-huge**: QEMU with huge-pages for virtio-balloon-huge
- **module-llfree**: QEMU with the LLFree allocator and HyperAlloc

To speedup the process, the image contains pre-built artifacts.
However, if desired, they can be rebuilt with the following command:

```sh
# cd hyperalloc-bench
# source ./venv/bin/activate

./run.py build
# (this builds three Linux kernels and QEMUs and usually about 1h)
```

The build artifacts are inside the build directories of `hyperalloc-linux`, `hyperalloc-qemu`, and `linux-alloc-bench`.


### Running the Benchmarks

These build targets are used for the following benchmark targets:

- `compiling`: Clang compilation with auto VM inflation
- `inflate`: Inflation/deflation latency
- `multivm`: Compiling clang on multiple concurrent VMs
- `stream`: STREAM memory bandwidth benchmark
- `ftq`: FTQ CPU work benchmark (also in the `stream` directory)

They can be executed with:

```sh
# cd hyperalloc-bench
# source ./venv/bin/activate

./run.py bench-plot all
# (about 30m)
```

- "all" can be replaced with a specific benchmark like "compiling".
- "bench-plot" can be replaced with "bench" or "plot" to only run the benchmarks or redraw the plots.

The results can be found in the `~/hyperalloc-bench/artifact-eval/<benchmark>` directory within the docker container.
The plots are directly contained in this directory.
The subdirectories contain the raw data and metadata, such as system, environment, and benchmark parameters.

The data from the paper is located in the `~/hyperalloc-bench/<benchmark>/latest` directories and the plots in `~/hyperalloc-bench/<benchmark>/out` (`<benchmark>` can be `compiling`, `inflate`, `multivm`, `stream`).
The `stream` directory also contains the `ftq` data.

### Exploring the Artifacts

This section might be helpful if you want to explore the contents of the docker container more easily.

The container has a running ssh server that allows you to create an `sshfs` mount.
This requires `sshfs` to be installed on your system.

```sh
# Mount the dockers home directory to your host machine
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
