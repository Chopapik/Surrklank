#pragma once
#include "fdd_engine.h"
#include "esp_err.h"
#include <cstddef>
namespace laboratory {
esp_err_t init();
void command(const char *text, char *reply, size_t capacity);
void set_listener(void (*callback)(int, fdd::State));
enum class SelectResult { ok, busy, invalid, storage };
// FDD SELECT: device 1-8; refused while any drive is active or a batch is
// pending; stored in NVS before it takes effect.
SelectResult set_select(int device, fdd::Line line);
void select_lines(fdd::Line (&lines)[fdd::count]);
// Bring-up chain test (docs/FIRMWARE.md): ON needs a live bus and no active drive.
bool set_bus_test(bool enabled);
bool bus_test_active();
// DRV8833 ULT faults, bit k = actuator module k / 4, slot k % 4; -1 while the
// bus is not live.
int actuator_faults();
} // namespace laboratory
