cd cpu2017
source shrc
ulimit -s 2097152
runcpu --config=ballooning.cfg --copies=14 --action=onlyrun 502.gcc_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=27 --action=onlyrun 531.deepsjeng_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=26 --action=onlyrun 557.xz_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=23 --action=onlyrun 503.bwaves_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=24 --action=onlyrun 507.cactuBSSN_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=32 --action=onlyrun 526.blender_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=22 --action=onlyrun 527.cam4_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=22 --action=onlyrun 549.fotonik3d_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
runcpu --config=ballooning.cfg --copies=23 --action=onlyrun 554.roms_r &
sleep 180s
kill -s SIGKILL -$(ps -o pgid= $(pgrep -o specperl) | awk '{print $1}')
sleep 10s
