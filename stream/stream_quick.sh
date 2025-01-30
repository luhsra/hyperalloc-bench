#!/bin/bash
set -e
ROOT="$(dirname "$0")"
source $ROOT/../venv/bin/activate
cd $ROOT

QEMU_VI=/opt/ballooning/virtio-qemu-system
QEMU_LL=/opt/ballooning/llfree-qemu-system
QEMU_HU=/opt/ballooning/virtio-huge-qemu-system

KERNEL_BU=/opt/ballooning/buddy-bzImage
KERNEL_HU=/opt/ballooning/buddy-huge-bzImage
KERNEL_LL=/opt/ballooning/llfree-bzImage

ARGS="--cores 12 --stream-size 45000000 --bench-iters 1900 --port 5322 --qmp 5323 --bench-threads 1 4 12 --max-balloon 18" # "--spec"
# python stream.py --baseline --suffix "baseline-stream" --mode base-manual $ARGS
python stream.py --suffix "virtio-balloon-stream" --mode base-manual $ARGS
# python stream.py --suffix "virtio-balloon-huge-stream" --mode huge-manual $ARGS
# python stream.py --suffix "virtio-mem-stream" --mode virtio-mem-movable $ARGS
# python stream.py --vfio 4 --suffix "virtio-mem-vfio-stream" --mode virtio-mem-movable $ARGS
# python stream.py --suffix "llfree-stream" --mode llfree-manual $ARGS
# python stream.py --vfio 4 --suffix "llfree-vfio-stream" --mode llfree-manual $ARGS

ARGS="--cores 12 --port 5322 --qmp 5323 --bench-threads 1 4 12 --bench-iters 1096 --ftq --max-balloon 18" # "--spec"
# python stream.py --baseline --suffix "baseline-ftq" --mode base-manual $ARGS
python stream.py --suffix "virtio-balloon-ftq" --mode base-manual $ARGS
# python stream.py --suffix "virtio-balloon-huge-ftq" --mode huge-manual $ARGS
# python stream.py --suffix "virtio-mem-ftq" --mode virtio-mem-movable $ARGS
# python stream.py --vfio 4 --suffix "virtio-mem-vfio-ftq" --mode virtio-mem-movable $ARGS
# python stream.py --suffix "llfree-ftq" --mode llfree-manual $ARGS
# python stream.py --vfio 4 --suffix "llfree-vfio-ftq" --mode llfree-manual $ARGS
