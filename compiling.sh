#!/bin/bash
# Linux
P=$PATH
echo $PATH

# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target write -m8 -c12 --suffix write-llfree-auto-vfio --delay 10 --vfio 4
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target write -m8 -c12 --suffix write-llfree-auto --delay 10 --perf

# Linux
ARGS="--target linux -m8 -c12 --delay 30"
./max_power.sh env PATH=$P python3 compiling.py --mode base-manual --suffix linux-base-manual $ARGS
./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --suffix linux-base-auto $ARGS
./max_power.sh env PATH=$P python3 compiling.py --mode huge-auto --suffix linux-huge-auto $ARGS
./max_power.sh env PATH=$P python3 compiling.py --mode llfree-manual --suffix linux-llfree-manual $ARGS
./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix linux-llfree-auto $ARGS
./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix linux-llfree-auto-vfio --vfio 4 $ARGS

# Clang
ARGS="--target clang -m16 -c12 --delay 200"
# ./max_power.sh env PATH=$P python3 compiling.py --mode base-manual --suffix clang-base-manual $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --suffix clang-base-auto $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode huge-auto --suffix clang-huge-auto $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-manual --suffix clang-llfree-manual $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix clang-llfree-auto $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix clang-llfree-auto-vfio --vfio 4 $ARGS

# Blender
ARGS="--target blender -m16 -c12 --delay 120"
# ./max_power.sh env PATH=$P python3 compiling.py --mode base-manual --suffix blender-base-manual $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --suffix blender-base-auto $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode huge-auto --suffix blender-huge-auto $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-manual --suffix blender-llfree-manual $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix blender-llfree-auto $ARGS
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix blender-llfree-auto-vfio --vfio 4 $ARGS

./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --suffix blender-llfree-auto --repeat 2 $ARGS
./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --suffix blender-llfree-auto --repeat 2 $ARGS
