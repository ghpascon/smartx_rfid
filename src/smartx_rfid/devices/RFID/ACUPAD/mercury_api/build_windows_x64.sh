#!/usr/bin/env bash
set -euo pipefail

SDK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SDK_DIR"

ZIG="${ZIG:-zig}"
OUTPUT="${OUTPUT:-libmercuryapi.dll}"

"$ZIG" cc \
  -target x86_64-windows-gnu \
  -shared -O2 \
  -DWIN32 \
  -DTMR_DISABLE_BACKGROUND_READS=1 \
  -DTMR_ENABLE_SERIAL_READER_ONLY=1 \
  -DTMR_ENABLE_UHF=1 \
  -DTMR_ENABLE_HF_LF=1 \
  -I. \
  -o "$OUTPUT" \
  tm_reader.c \
  tm_reader_async.c \
  serial_reader.c \
  serial_reader_l3.c \
  tmr_loadsave_configuration.c \
  tmr_param.c \
  tmr_strerror.c \
  tmr_utils.c \
  hex_bytes.c \
  osdep_win32.c \
  serial_transport_win32.c \
  mercury_exports_win32.c \
  mercury_exports_win32.def \
  -lws2_32

printf 'Built %s\n' "$SDK_DIR/$OUTPUT"
