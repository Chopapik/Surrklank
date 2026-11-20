#pragma once
#include "esp_err.h"
#include <stdint.h>
namespace ble {
esp_err_t init();
esp_err_t start();
esp_err_t request_fast_link();
bool connected();
// Same order as panel_display::Link: BLE not working, advertising, connected.
enum class Link : uint8_t { off, advertising, connected };
Link link();
int rssi(); // dBm of the current connection, 0 when unknown
}
