#!/bin/sh
# Rebuild the remote panel (see build_module.sh).
exec "$(dirname "$0")/build_module.sh" panel "$@"
