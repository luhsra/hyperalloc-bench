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

ARGS="--cores 12 --stream-size 45000000 --bench-iters 1900 --port 5322 --qmp 5323 --bench-threads 1 4 12" # "--spec"
# python stream.py --baseline --suffix "baseline-stream" --qemu $QEMU_VI --kernel $KERNEL_BU --mode base-manual $ARGS
# python stream.py --suffix "virtio-balloon-stream" --qemu $QEMU_VI --kernel $KERNEL_BU --mode base-manual $ARGS
# python stream.py --suffix "virtio-balloon-huge-stream" --qemu $QEMU_HU --kernel $KERNEL_HU --mode huge-manual $ARGS
# python stream.py --suffix "virtio-mem-stream" --qemu $QEMU_VI --kernel $KERNEL_BU --mode virtio-mem-movable $ARGS --shrink-target 0 --max-balloon 18
# python stream.py --vfio 4 --suffix "virtio-mem-vfio-stream" --qemu $QEMU_VI --kernel $KERNEL_BU --mode virtio-mem-movable $ARGS --shrink-target 0 --max-balloon 18
# python stream.py --suffix "llfree-stream" --qemu $QEMU_LL --kernel $KERNEL_LL --mode llfree-manual $ARGS
# python stream.py --vfio 4 --suffix "llfree-vfio-stream" --qemu $QEMU_LL --kernel $KERNEL_LL --mode llfree-manual $ARGS

ARGS="--cores 12 --port 5322 --qmp 5323 --bench-threads 1 4 12 --bench-iters 1096 --ftq" # "--spec"
python stream.py --baseline --suffix "baseline-ftq" --qemu $QEMU_VI --kernel $KERNEL_BU --mode base-manual $ARGS
# python stream.py --suffix "virtio-balloon-ftq" --qemu $QEMU_VI --kernel $KERNEL_BU --mode base-manual $ARGS
# python stream.py --suffix "virtio-balloon-huge-ftq" --qemu $QEMU_HU --kernel $KERNEL_HU --mode huge-manual $ARGS
# python stream.py --suffix "virtio-mem-ftq" --qemu $QEMU_VI --kernel $KERNEL_BU --mode virtio-mem-movable $ARGS --shrink-target 0 --max-balloon 18
# python stream.py --vfio 4 --suffix "virtio-mem-vfio-ftq" --qemu $QEMU_VI --kernel $KERNEL_BU --mode virtio-mem-movable $ARGS --shrink-target 0 --max-balloon 18
# python stream.py --suffix "llfree-ftq" --qemu $QEMU_LL --kernel $KERNEL_LL --mode llfree-manual $ARGS
# python stream.py --vfio 4 --suffix "llfree-vfio-ftq" --qemu $QEMU_LL --kernel $KERNEL_LL --mode llfree-manual $ARGS
