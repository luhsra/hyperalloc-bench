#!/bin/bash
set -e
source ../venv/bin/activate

ARGS="--target blender -m8 -c12 --delay 60 --repeat 10 --vms 4 --high-mem 24"
# python3 multivm.py --mode base-manual --suffix blender-base-manual $ARGS

ARGS="--target write -m10 -c8 --delay 30 --repeat 5 --vms 3"
# python3 multivm.py --mode base-manual --suffix write-base-manual $ARGS
# python3 multivm.py --mode base-auto --suffix write-base-auto $ARGS
# python3 multivm.py --mode llfree-auto --suffix write-llfree-auto $ARGS
# python3 multivm.py --mode base-manual --suffix write-base-manual-s $ARGS --simultaneous
# python3 multivm.py --mode base-auto --suffix write-base-auto-s $ARGS --simultaneous
# python3 multivm.py --mode llfree-auto --suffix write-llfree-auto-s $ARGS --simultaneous

# clang takes about 40min on 12 cores
# 4 benchmarks at the same time, lets restart every 3h
ARGS="--target clang -m16 -c8 --delay 7200 --repeat 3 --vms 3"
python3 multivm.py --mode base-manual --suffix clang-base-manual $ARGS
python3 multivm.py --mode base-auto --suffix clang-base-auto $ARGS
python3 multivm.py --mode llfree-auto --suffix clang-llfree-auto $ARGS
python3 multivm.py --mode base-manual --suffix clang-base-manual-s $ARGS --simultaneous
python3 multivm.py --mode base-auto --suffix clang-base-auto-s $ARGS --simultaneous
python3 multivm.py --mode llfree-auto --suffix clang-llfree-auto-s $ARGS --simultaneous
