#!/bin/bash
ETH_DEV1=0000:19:00.0
ETH_DEV2=0000:19:00.1

DISK=/opt/ballooning/debian.img
LINUX=/opt/ballooning/llfree-bzImage

/opt/ballooning/llfree-qemu-system \
    -object iothread,id=auto-mode-iothread \
    -object iothread,id=api-triggered-mode-iothread \
    -object iothread,id=iothread1 \
    -object iothread,id=iothread2 \
    -object iothread,id=iothread3 \
    -object iothread,id=iothread4 \
    -device '{"driver":"virtio-llfree-balloon","auto-mode-iothread":"auto-mode-iothread","auto-mode":false,"kvm-map-ioctl":true,"api-triggered-mode-iothread":"api-triggered-mode-iothread","iothread-vq-mapping":[{"iothread":"iothread1"},{"iothread":"iothread2"},{"iothread":"iothread3"},{"iothread":"iothread4"}]}' \
    -nographic \
    -kernel $LINUX \
    -append "console=ttyS0 nokaslr root=/dev/sda1" \
    -hda $DISK \
    -enable-kvm \
    -smp 4 \
    -m 8G \
    -qmp unix:qmp.sock,server=on,wait=off \
    -serial mon:stdio \
    -gdb tcp::3333 \
    -cpu host \
    -nic user,hostfwd=tcp:127.0.0.1:5222-:22 \
    -device '{"driver":"vfio-pci","host":'\"$ETH_DEV1\"'}' \
    -device '{"driver":"vfio-pci","host":'\"$ETH_DEV2\"'}' \
    #-S
    # -nic none \
    # -trace events=traces/qemu-trace-events.txt \
# gdb /opt/ballooning/llfree-qemu-system
