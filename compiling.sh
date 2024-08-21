#!/bin/bash

source ../venv/bin/activate

# Write

# python3 compiling.py --mode base-auto --target write -m12 -c12 --delay 10
# python3 compiling.py --mode huge-auto --target write -m12 -c12 --delay 10
# python3 compiling.py --mode llfree-auto --target write -m12 -c12 --delay 10
# python3 compiling.py --mode llfree-auto --target write -m12 -c12 --suffix write-llfree-auto --delay 10 --perf

# Linux
ARGS="--target linux -m8 -c12 --delay 30"

# python3 compiling.py --mode base-manual --kernel /srv/scratch/wrenger/llfree-linux/build-llfree-vm/arch/x86/boot/bzImage --qemu qemu-system-x86_64 --suffix linux-llfree-test $ARGS --frag
# python3 compiling.py --mode base-manual --kernel /srv/scratch/wrenger/llfree-linux/build-buddy-vm/arch/x86/boot/bzImage --qemu qemu-system-x86_64 --suffix base-llfree-test $ARGS


# python3 compiling.py --mode base-manual --suffix linux-base-manual $ARGS
# python3 compiling.py --mode base-auto --suffix linux-base-auto $ARGS
# python3 compiling.py --mode huge-auto --suffix linux-huge-auto $ARGS
# python3 compiling.py --mode llfree-manual --suffix linux-llfree-manual $ARGS
# python3 compiling.py --mode llfree-auto --suffix linux-llfree-auto $ARGS
# python3 compiling.py --mode llfree-auto --suffix linux-llfree-auto-vfio --vfio 4 $ARGS
# python3 compiling.py --mode virtio-mem-movable --suffix linux-virtio-mem-vfio --vfio 4 $ARGS

# Clang
ARGS="--target clang -m16 -c12 --delay 200"
# python3 compiling.py --mode base-manual --suffix clang-base-manual $ARGS
python3 compiling.py --mode base-auto --suffix clang-base-auto $ARGS
# python3 compiling.py --mode huge-auto --suffix clang-huge-auto $ARGS
# python3 compiling.py --mode llfree-manual --suffix clang-llfree-manual $ARGS
python3 compiling.py --mode llfree-auto --suffix clang-llfree-auto $ARGS
python3 compiling.py --mode llfree-auto --suffix clang-llfree-auto-vfio --vfio 4 $ARGS
python3 compiling.py --mode virtio-mem-movable --suffix clang-virtio-mem-vfio --vfio 4 $ARGS


# python3 compiling.py --mode base-manual --kernel /srv/scratch/wrenger/llfree-linux/build-llfree-vm/arch/x86/boot/bzImage --qemu qemu-system-x86_64 --suffix clang-llfree-test $ARGS --frag

# Blender
ARGS="--target blender -m16 -c12 --delay 240"
# python3 compiling.py --mode base-manual --suffix blender-base-manual $ARGS
# python3 compiling.py --mode base-auto --suffix blender-base-auto $ARGS
# python3 compiling.py --mode huge-auto --suffix blender-huge-auto $ARGS
# python3 compiling.py --mode llfree-manual --suffix blender-llfree-manual $ARGS
# python3 compiling.py --mode llfree-auto --suffix blender-llfree-auto $ARGS
# python3 compiling.py --mode llfree-auto --suffix blender-llfree-auto-vfio --vfio 4 $ARGS

# python3 compiling.py --mode base-auto --suffix blender-base-auto --repeat 3 $ARGS
# python3 compiling.py --mode llfree-auto --suffix blender-llfree-auto --repeat 3 $ARGS
