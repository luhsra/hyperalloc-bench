systemd-run --user --slice ballooning-250121-215300.slice --scope /opt/ballooning/virtio-qemu-system -smp 8 -hda /opt/ballooning/debian.img -snapshot -serial mon:stdio -nographic -kernel /opt/ballooning/buddy-bzImage -qmp tcp:localhost:5123,server=on,wait=off -nic user,hostfwd=tcp:127.0.0.1:5223-:22 -no-reboot --cpu host -m 16G -device '{"driver": "virtio-balloon", "free-page-reporting": true}' -append 'root=/dev/sda3 console=ttyS0 nokaslr' -enable-kvm