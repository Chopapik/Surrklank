#!/bin/sh
# Rebuild the LSM/HDD module (see build_module.sh).
exec "$(dirname "$0")/build_module.sh" lsm-hdd "$@"
