#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"

cd "$REPO_ROOT"
source "$REPO_ROOT/EnvSetup.sh"

/usr/bin/time -v yosys-hier-equiv hier-check \
  --gold /home/hgh/remuws/remu/examples/build/picorv32-comp/part0/emu_system.v \
  --gate /home/hgh/remuws/remu/examples/build/picorv32/part0/emu_system.v \
  --common /home/hgh/remuws/remu/emulib/common/emulib_deserializer.v \
  --common /home/hgh/remuws/remu/emulib/common/emulib_serializer.v \
  --common /home/hgh/remuws/remu/emulib/common/emulib_simple_dma.v \
  --common /home/hgh/remuws/remu/emulib/partition/HuaFenCtrl.v \
  --common /home/hgh/remuws/remu/emulib/partition/axis2decouple.v \
  --common /home/hgh/remuws/remu/emulib/partition/axis_ring_fifo.v \
  --common /home/hgh/remuws/remu/emulib/partition/comm_in_demux.v \
  --common /home/hgh/remuws/remu/emulib/partition/comm_in_unpack.v \
  --common /home/hgh/remuws/remu/emulib/partition/comm_out_mux.v \
  --common /home/hgh/remuws/remu/emulib/partition/comm_out_pack.v \
  --common /home/hgh/remuws/remu/emulib/partition/decouple2axis.v \
  --common /home/hgh/remuws/remu/emulib/partition/ring_fifo.v \
  --common /home/hgh/remuws/remu/emulib/platform/fpga/ClockGate.v \
  --common /home/hgh/remuws/remu/emulib/system/AXILiteToCtrl.v \
  --common /home/hgh/remuws/remu/emulib/system/EmuAXIRemapCtrl.v \
  --common /home/hgh/remuws/remu/emulib/system/EmuScanCtrl.v \
  --common /home/hgh/remuws/remu/emulib/system/EmuSysCtrl.v \
  --common /home/hgh/remuws/remu/emulib/system/ctrlbus_bridge.v \
  --common /home/hgh/remuws/remu/emulib/system/ctrlbus_gpio_out.v \
  -I /home/hgh/remuws/remu/emulib/include \
  --top EMU_SYSTEM_0 \
  --seq 2 \
  --work-dir build/picorv32-part0-hier
