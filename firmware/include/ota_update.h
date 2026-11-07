#pragma once
#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>
namespace ota {
// Stage: 0 idle, 1 writing, 2 ready, 3 failed. Sequence is scoped to this boot.
struct State { uint8_t stage; uint32_t received; int32_t error; uint32_t sequence; };
void set_listener(void (*callback)(State));
esp_err_t init();
void disconnected();
void describe(char* output,size_t capacity);
esp_err_t confirm();
esp_err_t reboot();
}
