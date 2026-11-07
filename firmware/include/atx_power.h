#pragma once
#include "esp_err.h"
#include <stdint.h>

namespace atx {
struct State { bool on; uint32_t sequence; };
esp_err_t init();
State state();
bool is_on();
void set_listener(void (*callback)(State));
bool set(bool on);
bool prepare();
bool claim_instruments();
void release_instruments();
}
