#!/bin/bash

source ../venv/bin/activate

MODULE_LL=/srv/scratch/wrenger/linux-alloc-bench/build-llfree-vm/alloc.ko
MODULE_BU=/srv/scratch/wrenger/linux-alloc-bench/build-buddy-vm/alloc.ko
MODULE_HU=/srv/scratch/wrenger/linux-alloc-bench/build-buddy-huge/alloc.ko

ARGS="-m20 -c12 --shrink-target 2 -i10"
# python3 inflate.py --mode base-manual $ARGS --module $MODULE_BU
# python3 inflate.py --mode huge-manual $ARGS --module $MODULE_HU
# python3 inflate.py --mode virtio-mem-movable $ARGS --module $MODULE_BU
# python3 inflate.py --mode virtio-mem-movable $ARGS --vfio 4 --suffix virtio-mem-movable-vfio --module $MODULE_BU
python3 inflate.py --mode llfree-manual $ARGS --module $MODULE_LL
python3 inflate.py --mode llfree-manual $ARGS --vfio 4 --suffix llfree-manual-vfio --module $MODULE_LL

ARGS="-m20 -c12 --shrink-target 2 -i10 --nofault"
# python3 inflate.py --mode base-manual $ARGS --module $MODULE_BU
# python3 inflate.py --mode huge-manual $ARGS --module $MODULE_HU
# python3 inflate.py --mode virtio-mem-movable $ARGS --module $MODULE_BU
# python3 inflate.py --mode virtio-mem-movable $ARGS --vfio 4 --suffix virtio-mem-movable-vfio --module $MODULE_BU
# python3 inflate.py --mode llfree-manual $ARGS --module $MODULE_LL
# python3 inflate.py --mode llfree-manual $ARGS --vfio 4 --suffix llfree-manual-vfio --module $MODULE_LL
