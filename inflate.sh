P=$PATH

ARGS="-m16 -c12 --shrink-target 4 -i3"
# ./max_power.sh env PATH=$P python3 inflate.py --mode base-manual $ARGS
./max_power.sh env PATH=$P python3 inflate.py --mode huge-manual $ARGS
# ./max_power.sh env PATH=$P python3 inflate.py --mode virtio-mem-movable $ARGS
# ./max_power.sh env PATH=$P python3 inflate.py --mode virtio-mem-movable $ARGS --vfio 4 --suffix virtio-mem-movable-vfio
# ./max_power.sh env PATH=$P python3 inflate.py --mode llfree-manual $ARGS
# ./max_power.sh env PATH=$P python3 inflate.py --mode llfree-manual $ARGS --vfio 4 --suffix llfree-manual-vfio
