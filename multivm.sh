#!/bin/bash
set -e
source ../venv/bin/activate

ARGS="--target blender -m8 -c12 --delay 60 --repeat 10 --vms 4 --high-mem 24"
# python3 multivm.py --mode base-manual --suffix blender-base-manual $ARGS

ARGS="--target write -m10 -c12 --delay 10 --repeat 10 --vms 4"
# python3 multivm.py --mode base-manual --suffix write-base-manual $ARGS
# python3 multivm.py --mode base-auto --suffix write-base-auto $ARGS
python3 multivm.py --mode llfree-auto --suffix write-llfree-auto $ARGS
