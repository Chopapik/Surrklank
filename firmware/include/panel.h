#pragma once
#include "esp_err.h"
#include <stdint.h>

// Remote panel (docs/WIRING.md): MCP23017 buttons and LEDs on I2C. Detected
// once at startup; without it ATX ON is refused (docs/FIRMWARE.md).
namespace panel {
enum Button : uint8_t { prev = 1, play = 2, stop = 3, next = 4 }; // 5-7: GPA4-GPA6
esp_err_t init();
// False when absent at startup or after a failed I2C transfer (until restart).
bool present();
void set_listener(void (*callback)(uint8_t button, uint32_t sequence));
} // namespace panel
