# Linux

./max_power.sh python3 compiling.py --mode base-manual --target linux -m8 -c12 --suffix linux-base-manual
./max_power.sh python3 compiling.py --mode base-auto --target linux -m8 -c12 --suffix linux-base-auto
./max_power.sh python3 compiling.py --mode huge-auto --target linux -m8 -c12 --suffix linux-huge-auto
./max_power.sh python3 compiling.py --mode llfree-manual --target linux -m8 -c12 --suffix linux-llfree-manual
./max_power.sh python3 compiling.py --mode llfree-auto --target linux -m8 -c12 --suffix linux-llfree-auto

# Clang
./max_power.sh python3 compiling.py --mode base-manual --target clang -m16 -c12 --suffix clang-base-manual --post-delay 60
./max_power.sh python3 compiling.py --mode base-auto --target clang -m16 -c12 --suffix clang-base-auto --post-delay 60
./max_power.sh python3 compiling.py --mode huge-auto --target clang -m16 -c12 --suffix clang-huge-auto --post-delay 60
./max_power.sh python3 compiling.py --mode llfree-manual --target clang -m16 -c12 --suffix clang-llfree-manual --post-delay 60
./max_power.sh python3 compiling.py --mode llfree-auto --target clang -m16 -c12 --suffix clang-llfree-auto --post-delay 60

# Blender
./max_power.sh python3 compiling.py --mode base-manual --target blender -m16 -c12 --suffix blender-base-manual --post-delay 60
./max_power.sh python3 compiling.py --mode base-auto --target blender -m16 -c12 --suffix blender-base-auto --post-delay 60
./max_power.sh python3 compiling.py --mode huge-auto --target blender -m16 -c12 --suffix blender-huge-auto --post-delay 60
./max_power.sh python3 compiling.py --mode llfree-manual --target blender -m16 -c12 --suffix blender-llfree-manual --post-delay 60
./max_power.sh python3 compiling.py --mode llfree-auto --target blender -m16 -c12 --suffix blender-llfree-auto --post-delay 60
