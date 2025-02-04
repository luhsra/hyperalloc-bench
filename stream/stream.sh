#!/bin/bash
set -e
ROOT="$(dirname "$0")"
source $ROOT/../venv/bin/activate
cd $ROOT

ARGS="--cores 12 --stream-size 45000000 --bench-iters 1900 --port 5322 --qmp 5323 --bench-threads 1 4 12 --max-balloon 18" # "--spec"
python bench.py --baseline --suffix "baseline-stream" --mode base-manual $ARGS
python bench.py --suffix "virtio-balloon-stream" --mode base-manual $ARGS
python bench.py --suffix "virtio-balloon-huge-stream" --mode huge-manual $ARGS
python bench.py --suffix "virtio-mem-stream" --mode virtio-mem $ARGS
python bench.py --vfio 4 --suffix "virtio-mem-vfio-stream" --mode virtio-mem $ARGS
python bench.py --suffix "llfree-stream" --mode llfree-manual $ARGS
python bench.py --vfio 4 --suffix "llfree-vfio-stream" --mode llfree-manual $ARGS

ARGS="--cores 12 --port 5322 --qmp 5323 --bench-threads 1 4 12 --bench-iters 1096 --ftq --max-balloon 18" # "--spec"
python bench.py --baseline --suffix "baseline-ftq" --mode base-manual $ARGS
python bench.py --suffix "virtio-balloon-ftq" --mode base-manual $ARGS
python bench.py --suffix "virtio-balloon-huge-ftq" --mode huge-manual $ARGS
python bench.py --suffix "virtio-mem-ftq" --mode virtio-mem $ARGS
python bench.py --vfio 4 --suffix "virtio-mem-vfio-ftq" --mode virtio-mem $ARGS
python bench.py --suffix "llfree-ftq" --mode llfree-manual $ARGS
python bench.py --vfio 4 --suffix "llfree-vfio-ftq" --mode llfree-manual $ARGS
