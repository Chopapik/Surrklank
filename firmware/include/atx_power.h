#pragma once
#include "esp_err.h"
#include <stdint.h>

namespace atx {
struct State { bool on; uint32_t sequence; };
esp_err_t init();
State state();
bool is_on();
// Measured main rails: PWR_OK on GPIO36 after about 50 ms of stable level,
// unlike the GPIO19 request reported by is_on(). Own sequence per boot.
struct Rails { bool ok; uint32_t sequence; };
Rails rails();
bool rails_ok();
void set_listener(void (*callback)(State));
void set_rails_listener(void (*callback)(Rails));
bool set(bool on);
bool prepare();
bool claim_instruments();
void release_instruments();
}
