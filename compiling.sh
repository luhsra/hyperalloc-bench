# ./max_power.sh python3 compiling.py --mode llfree-auto --target linux
# ./max_power.sh python3 compiling.py --mode base-auto --target linux
./max_power.sh python3 compiling.py --mode base-manual --target clang -m16 -c12
./max_power.sh python3 compiling.py --mode llfree-auto --target clang -m16 -c12
./max_power.sh python3 compiling.py --mode base-auto --target clang -m16 -c12
