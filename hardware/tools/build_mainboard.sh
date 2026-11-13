#!/bin/sh
# Rebuild the mainboard (see build_module.sh).
exec "$(dirname "$0")/build_module.sh" mainboard "$@"
