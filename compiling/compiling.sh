#!/bin/bash
set -e
ROOT="$(dirname "$0")"
source $ROOT/../venv/bin/activate
cd $ROOT

# Write

ORDERS="0 9"
CAPACITIES="32 512"
DELAYS="2000 100"

# for O in $ORDERS; do
#     for D in $DELAYS; do
#         for C in $CAPACITIES; do
#             python3 bench.py --mode base-auto --target write -m12 -c12 --delay 10 --fpr-order $O --fpr-delay $D --fpr-capacity $C --suffix "base-auto-o$O-d$D-c$C"
#         done
#     done
# done

python3 bench.py --mode base-manual --target write -m12 -c12 --delay 10
# python3 bench.py --mode base-auto --target write -m12 -c12 --delay 10
# python3 bench.py --mode huge-auto --target write -m12 -c12 --delay 10
# python3 bench.py --mode llfree-auto --target write -m12 -c12 --delay 10
# python3 bench.py --mode llfree-auto --target write -m12 -c12 --delay 10 --perf
# python3 bench.py --mode llfree-auto --target write -m12 -c12 --suffix llfree-auto-vfio --delay 10 --vfio 4
# python3 bench.py --mode virtio-mem --target write -m12 -c12 --delay 10


# Linux
ARGS="--target linux -m8 -c12 --delay 30"

# python3 bench.py --mode base-manual --kernel /srv/scratch/wrenger/llfree-linux/build-llfree-vm/arch/x86/boot/bzImage --qemu qemu-system-x86_64 --suffix linux-llfree-test $ARGS --frag
# python3 bench.py --mode base-manual --kernel /srv/scratch/wrenger/llfree-linux/build-buddy-vm/arch/x86/boot/bzImage --qemu qemu-system-x86_64 --suffix base-llfree-test $ARGS


# python3 bench.py --mode base-manual --suffix linux-base-manual $ARGS
# python3 bench.py --mode base-auto --suffix linux-base-auto $ARGS
# python3 bench.py --mode huge-auto --suffix linux-huge-auto $ARGS
# python3 bench.py --mode llfree-manual --suffix linux-llfree-manual $ARGS
# python3 bench.py --mode llfree-auto --suffix linux-llfree-auto $ARGS
# python3 bench.py --mode llfree-auto --suffix linux-llfree-auto-vfio --vfio 4 $ARGS
# python3 bench.py --mode virtio-mem --suffix linux-virtio-mem-vfio $ARGS
# python3 bench.py --mode virtio-mem --suffix linux-virtio-mem-vfio --vfio 4 $ARGS

# Clang
ARGS="--target clang -m16 -c12 --delay 200  --iter 3"
# python3 bench.py --mode base-manual --suffix clang-base-manual $ARGS
# python3 bench.py --mode base-auto --suffix clang-base-auto $ARGS
# python3 bench.py --mode huge-auto --suffix clang-huge-auto $ARGS
# python3 bench.py --mode llfree-manual --suffix clang-llfree-manual $ARGS
# python3 bench.py --mode llfree-auto --suffix clang-llfree-auto $ARGS
# python3 bench.py --mode llfree-auto --suffix clang-llfree-auto-vfio --vfio 4 $ARGS
# python3 bench.py --mode virtio-mem --suffix clang-virtio-mem $ARGS
# python3 bench.py --mode virtio-mem --suffix clang-virtio-mem-vfio --vfio 4 $ARGS


# python3 bench.py --mode base-manual --kernel /srv/scratch/wrenger/llfree-linux/build-llfree-vm/arch/x86/boot/bzImage --qemu qemu-system-x86_64 --suffix clang-llfree-test $ARGS --frag

for O in $ORDERS; do
    for D in $DELAYS; do
        for C in $CAPACITIES; do
            #python3 bench.py --mode base-auto $ARGS --fpr-order $O --fpr-delay $D --fpr-capacity $C --suffix "clang-base-auto-o$O-d$D-c$C"
            true;
        done
    done
done

# Blender
ARGS="--target blender -m16 -c12 --delay 360"
# python3 bench.py --mode base-manual --suffix blender-base-manual $ARGS
# python3 bench.py --mode base-auto --suffix blender-base-auto $ARGS
# python3 bench.py --mode huge-auto --suffix blender-huge-auto $ARGS
# python3 bench.py --mode llfree-manual --suffix blender-llfree-manual $ARGS
# python3 bench.py --mode llfree-auto --suffix blender-llfree-auto $ARGS
# python3 bench.py --mode llfree-auto --suffix blender-llfree-auto-vfio --vfio 4 $ARGS

# python3 bench.py --mode base-auto --suffix blender-base-auto --repeat 3 $ARGS
# python3 bench.py --mode llfree-auto --suffix blender-llfree-auto --repeat 3 $ARGS
