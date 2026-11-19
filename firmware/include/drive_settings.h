#pragma once
#include "esp_err.h"
#include "fdd_engine.h"

// Per-drive select line persisted in NVS (docs/FIRMWARE.md). Call after
// nvs_flash_init().
namespace drive_settings {
// Missing, unreadable or invalid entries keep fdd::default_select.
void load(fdd::Line (&lines)[fdd::count]);
esp_err_t store(const fdd::Line (&lines)[fdd::count]);
} // namespace drive_settings
