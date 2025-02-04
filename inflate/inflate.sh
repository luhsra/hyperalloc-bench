#!/bin/bash
set -e
ROOT="$(dirname "$0")"
source $ROOT/../venv/bin/activate
cd $ROOT

MODULE_LL=../../linux-alloc-bench/build-llfree-vm/alloc.ko
MODULE_BU=../../linux-alloc-bench/build-buddy-vm/alloc.ko
MODULE_HU=../../linux-alloc-bench/build-buddy-huge/alloc.ko

ARGS="-m20 -c12 --shrink-target 2 -i1"
python3 bench.py --mode base-manual $ARGS --module $MODULE_BU
# python3 bench.py --mode huge-manual $ARGS --module $MODULE_HU
# python3 bench.py --mode virtio-mem-movable $ARGS --module $MODULE_BU
# python3 bench.py --mode virtio-mem-movable $ARGS --vfio 4 --suffix virtio-mem-movable-vfio --module $MODULE_BU
# python3 bench.py --mode llfree-manual $ARGS --module $MODULE_LL
# python3 bench.py --mode llfree-manual $ARGS --vfio 4 --suffix llfree-manual-vfio --module $MODULE_LL

ARGS="-m20 -c12 --shrink-target 2 -i10 --nofault"
# python3 bench.py --mode base-manual $ARGS --module $MODULE_BU
# python3 bench.py --mode huge-manual $ARGS --module $MODULE_HU
# python3 bench.py --mode virtio-mem-movable $ARGS --module $MODULE_BU
# python3 bench.py --mode virtio-mem-movable $ARGS --vfio 4 --suffix virtio-mem-movable-vfio --module $MODULE_BU
# python3 bench.py --mode llfree-manual $ARGS --module $MODULE_LL
# python3 bench.py --mode llfree-manual $ARGS --vfio 4 --suffix llfree-manual-vfio --module $MODULE_LL
