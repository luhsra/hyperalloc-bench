# Linux
P=$PATH
echo $PATH

./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto-map --target write -m8 -c12 --suffix write-llfree-auto-vfio --delay 10 --vfio 4
./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto-map --target write -m8 -c12 --suffix write-llfree-auto --delay 10

#./max_power.sh env PATH=$P python3 compiling.py --mode base-manual --target linux -m8 -c12 --suffix linux-base-manual --delay 30
#./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --target linux -m8 -c12 --suffix linux-base-auto --delay 30
#./max_power.sh env PATH=$P python3 compiling.py --mode huge-auto --target linux -m8 -c12 --suffix linux-huge-auto --delay 30
#./max_power.sh env PATH=$P python3 compiling.py --mode llfree-manual --target linux -m8 -c12 --suffix linux-llfree-manual --delay 30
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target linux -m8 -c12 --suffix linux-llfree-auto --delay 30
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target linux -m8 -c12 --suffix linux-llfree-auto --delay 30 --vfio 4

# Clang
#./max_power.sh env PATH=$P python3 compiling.py --mode base-manual --target clang -m16 -c12 --suffix clang-base-manual --delay 200
#./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --target clang -m16 -c12 --suffix clang-base-auto --delay 200
#./max_power.sh env PATH=$P python3 compiling.py --mode huge-auto --target clang -m16 -c12 --suffix clang-huge-auto --delay 200
#./max_power.sh env PATH=$P python3 compiling.py --mode llfree-manual --target clang -m16 -c12 --suffix clang-llfree-manual --delay 200
#./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target clang -m16 -c12 --suffix clang-llfree-auto --delay 200

# Blender
#./max_power.sh env PATH=$P python3 compiling.py --mode base-manual --target blender -m16 -c12 --suffix blender-base-manual --delay 120
#./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --target blender -m16 -c12 --suffix blender-base-auto --delay 120
#./max_power.sh env PATH=$P python3 compiling.py --mode huge-auto --target blender -m16 -c12 --suffix blender-huge-auto --delay 120
#./max_power.sh env PATH=$P python3 compiling.py --mode llfree-manual --target blender -m16 -c12 --suffix blender-llfree-manual --delay 120
#./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target blender -m16 -c12 --suffix blender-llfree-auto --delay 120

# ./max_power.sh env PATH=$P python3 compiling.py --mode base-auto --target blender -m16 -c12 --suffix blender-llfree-auto --delay 120 --repeat 2
# ./max_power.sh env PATH=$P python3 compiling.py --mode llfree-auto --target blender -m16 -c12 --suffix blender-llfree-auto --delay 120 --repeat 2
