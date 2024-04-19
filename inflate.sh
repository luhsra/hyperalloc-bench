P=$PATH
./max_power.sh env PATH=$P python3 inflate.py --mode base-manual -m16 -c12 --shrink-target 4
./max_power.sh env PATH=$P python3 inflate.py --mode huge-manual -m16 -c12 --shrink-target 4
./max_power.sh env PATH=$P python3 inflate.py --mode llfree-manual -m16 -c12 --shrink-target 4

# TODO: Virtio-mem!
