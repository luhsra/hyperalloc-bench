# Benchmark Data & Visualization

Setup venv and dependencies:

```sh
python3 -m venv venv
source ./venv/bin/activate
pip install -r requirements.txt
```

Run benchmark:

```sh
./max_power.sh python compiling.py --qemu <path> --kernel <path> --img <path> -c 8 -m 8 --suffix demo
# e.g.
sudo ./max_power.sh python3 compiling.py --qemu ../../llfree-ballooning-qemu/build/qemu-system-x86_64 --kernel ../../llfree-linux-ballooning/build-llfree-vm/arch/x86/boot/bzImage --img ../../llfree-ballooning-work/workplace/drives/debian_drive.img -c 8 -m 8 --suffix demo
```
