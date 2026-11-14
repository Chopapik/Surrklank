#!/bin/sh
# Rebuild the actuator module (see build_module.sh).
exec "$(dirname "$0")/build_module.sh" actuator "$@"
