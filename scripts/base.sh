#!/bin/bash
DISK=resources/debian-copy.qcow2

../hyperalloc-qemu/build/qemu-system-x86_64 -smp 12 -hda $DISK -serial mon:stdio -nographic -kernel ../hyperalloc-linux/build-llfree-vm/arch/x86/boot/bzImage -qmp tcp:localhost:5023,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5223-:22 -no-reboot -m 16G -append "root=/dev/sda3 console=ttyS0 nokaslr" --cpu host --enable-kvm $@
