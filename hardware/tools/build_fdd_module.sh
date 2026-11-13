#!/bin/sh
# Rebuild the FDD module (see build_module.sh).
exec "$(dirname "$0")/build_module.sh" fdd "$@"
