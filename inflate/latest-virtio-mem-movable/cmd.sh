/opt/ballooning/virtio-qemu-system -smp 12 -hda /opt/ballooning/debian.img -serial mon:stdio -nographic -kernel /opt/ballooning/buddy-bzImage -qmp tcp:localhost:5023,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5222-:22 -no-reboot --cpu host -m 2G,maxmem=20G -append 'root=/dev/sda1 console=ttyS0 nokaslr memhp_default_state=online_movable' -machine pc -object memory-backend-ram,id=vmem0,size=18G,prealloc=off,reserve=off -device virtio-mem-pci,id=vm0,memdev=vmem0,node=0,requested-size=18G,prealloc=off -enable-kvm