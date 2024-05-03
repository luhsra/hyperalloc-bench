/opt/ballooning/llfree-qemu-system -smp 12 -hda /opt/ballooning/debian.img -serial mon:stdio -nographic -kernel /opt/ballooning/llfree-bzImage -qmp tcp:localhost:5023,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5222-:22 -no-reboot --cpu host -m 16G -append 'root=/dev/sda1 console=ttyS0 nokaslr' -object iothread,id=auto-mode-iothread -object iothread,id=api-triggered-mode-iothread -object iothread,id=iothread0 -object iothread,id=iothread1 -object iothread,id=iothread2 -object iothread,id=iothread3 -object iothread,id=iothread4 -object iothread,id=iothread5 -object iothread,id=iothread6 -object iothread,id=iothread7 -object iothread,id=iothread8 -object iothread,id=iothread9 -object iothread,id=iothread10 -object iothread,id=iothread11 -device '{"driver": "virtio-llfree-balloon", "auto-mode": true, "kvm-map-ioctl": true, "auto-mode-iothread": "auto-mode-iothread", "api-triggered-mode-iothread": "api-triggered-mode-iothread", "iothread-vq-mapping": [{"iothread": "iothread0"}, {"iothread": "iothread1"}, {"iothread": "iothread2"}, {"iothread": "iothread3"}, {"iothread": "iothread4"}, {"iothread": "iothread5"}, {"iothread": "iothread6"}, {"iothread": "iothread7"}, {"iothread": "iothread8"}, {"iothread": "iothread9"}, {"iothread": "iothread10"}, {"iothread": "iothread11"}]}' -enable-kvm