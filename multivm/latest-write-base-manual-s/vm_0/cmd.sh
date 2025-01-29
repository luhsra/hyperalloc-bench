systemd-run --user --slice ballooning-250121-143602.slice --scope /opt/ballooning/virtio-qemu-system -smp 8 -hda /opt/ballooning/debian.img -snapshot -serial mon:stdio -nographic -kernel /opt/ballooning/buddy-bzImage -qmp tcp:localhost:5122,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5222-:22 -no-reboot --cpu host -m 10G -device '{"driver": "virtio-balloon", "free-page-reporting": false}' -append 'root=/dev/sda3 console=ttyS0 nokaslr' -enable-kvm