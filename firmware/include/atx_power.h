#pragma once
#include "esp_err.h"

namespace atx {
esp_err_t init();
bool is_on();
bool set(bool on);
void prepare();
}
