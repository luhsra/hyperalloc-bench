#!/bin/bash

source ../venv/bin/activate

ARGS="--target blender -m16 -c12 --delay 60 --repeat 2 --vms 2 --high-mem 16"
# python3 multivm.py --mode base-manual --suffix blender-base-manual $ARGS

ARGS="--target write -m16 -c12 --delay 60 --repeat 2 --vms 2 --high-mem 32"
python3 multivm.py --mode base-manual --suffix write-base-manual $ARGS
