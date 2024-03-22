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
sudo ./max_power.sh python3 compiling.py --qemu /opt/ballooning/llfree-qemu-system --kernel /opt/ballooning/llfree-bzImage --img /opt/ballooning/debian.img -c 8 -m 8 --suffix demo --mode llfree-auto
```
