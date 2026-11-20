#pragma once
#include "driver/i2c_master.h"
#include <stdint.h>

// SSD1306 OLED on the remote panel (docs/FIRMWARE.md#remote-panel). Optional:
// its absence only disables drawing. Called from the panel task only.
namespace panel_display {
enum class Link : uint8_t { off, advertising, connected };
struct Status {
    Link link = Link::off;
    int rssi = 0; // dBm, used while connected
};
// Shows the boot splash; false when no display answers.
bool init(i2c_master_bus_handle_t bus, const char *version, int64_t now_us);
bool present();
void show_stop(int64_t now_us);   // large STOP for 2 s
void show_notice(int64_t now_us); // "no MIDI player" for 2 s
// Redraws at most twice per second (at once after show_*), sending only the
// 8-pixel pages that changed.
void update(const Status &status, int64_t now_us);
} // namespace panel_display
