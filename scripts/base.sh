#!/bin/bash
# gdb /opt/ballooning/virtio-qemu-system --ex "hb main" --ex "run -smp 12 -hda /opt/ballooning/debian.img -serial mon:stdio -nographic -kernel /opt/ballooning/buddy-bzImage -qmp tcp:localhost:5023,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5222-:22 -no-reboot --cpu host -m 16G -append \"root=/dev/sda1 console=ttyS0 nokaslr\" -device \"{\\\"driver\\\": \\\"virtio-balloon\\\", \\\"free-page-reporting\\\": true}\" -enable-kvm"
DISK=resources/debian.qcow2
# DISK=/srv/scratch/albes/debian.qcow2.old

/opt/ballooning/virtio-qemu-system -smp 12 -hda $DISK -serial mon:stdio -nographic -kernel /opt/ballooning/llfree-bzImage -qmp tcp:localhost:5023,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5223-:22 -no-reboot -m 16G -append "root=/dev/sda3 console=ttyS0 nokaslr" --cpu host --enable-kvm
