#!/bin/bash

export QEMU_LLFREE_BALLOON_INFLATE_LOG=/dev/null && \
export QEMU_LLFREE_BALLOON_DEFLATE_LOG=/dev/null && \
export QEMU_VIRTIO_BALLOON_INFLATE_LOG=/dev/null && \
export QEMU_VIRTIO_BALLOON_DEFLATE_LOG=/dev/null

source "../.venv/bin/activate"

timestamp=$(date +"%y%m%d-%H%M%S")

python stream.py --spec --output $timestamp"/virtio-balloon-stream" --qemu /opt/ballooning/virtio-qemu-system --kernel /opt/ballooning/buddy-bzImage --cores 12 --mode base-manual --stream-size 45000000 --bench-iters 1900 --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323
python stream.py --spec --output $timestamp"/virtio-balloon-huge-stream" --qemu /opt/ballooning/virtio-huge-qemu-system --kernel /opt/ballooning/buddy-huge-bzImage --cores 12 --mode huge-manual --stream-size 45000000 --bench-iters 1900 --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323
python stream.py --spec --output $timestamp"/virtio-mem-stream" --qemu /opt/ballooning/virtio-qemu-system --kernel /opt/ballooning/buddy-bzImage --cores 12 --mode virtio-mem-movable --stream-size 45000000 --bench-iters 1900 --bench-threads 1 2 4 8 10 12 --mem 2 --shrink-target 0 --max-balloon 18 --port 5322 --qmp 5323
python stream.py --spec --output $timestamp"/llfree-stream" --qemu /opt/ballooning/llfree-qemu-system --kernel /opt/ballooning/llfree-bzImage --cores 12 --mode llfree-manual --stream-size 45000000 --bench-iters 1900  --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323
python stream.py --vfio 4 --spec --output $timestamp"/llfree-vfio-stream" --qemu /opt/ballooning/llfree-qemu-system --kernel /opt/ballooning/llfree-bzImage --cores 12 --mode llfree-manual --stream-size 45000000 --bench-iters 1900  --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323

python stream.py --spec --ftq --output $timestamp"/virtio-balloon-ftq" --qemu /opt/ballooning/virtio-qemu-system --kernel /opt/ballooning/buddy-bzImage --cores 12 --mode base-manual --bench-iters 1096 --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323
python stream.py --spec --ftq --output $timestamp"/virtio-balloon-huge-ftq" --qemu /opt/ballooning/virtio-huge-qemu-system --kernel /opt/ballooning/buddy-huge-bzImage --cores 12 --mode huge-manual --bench-iters 1096 --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323
python stream.py --spec --ftq --output $timestamp"/virtio-mem-ftq" --qemu /opt/ballooning/virtio-qemu-system --kernel /opt/ballooning/buddy-bzImage --cores 12 --mode virtio-mem-movable --bench-iters 1096 --bench-threads 1 2 4 8 10 12 --mem 2 --shrink-target 0 --max-balloon 18 --port 5322 --qmp 5323
python stream.py --spec --ftq --output $timestamp"/llfree-ftq" --qemu /opt/ballooning/llfree-qemu-system --kernel /opt/ballooning/llfree-bzImage --cores 12 --mode llfree-manual --bench-iters 1096 --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323
python stream.py --spec --vfio 4 --ftq --output $timestamp"/llfree-vfio-ftq" --qemu /opt/ballooning/llfree-qemu-system --kernel /opt/ballooning/llfree-bzImage --cores 12 --mode llfree-manual --bench-iters 1096 --bench-threads 1 2 4 8 10 12 --port 5322 --qmp 5323