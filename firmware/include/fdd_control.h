#pragma once
#include "fdd_engine.h"
#include "esp_err.h"
#include <cstddef>
namespace laboratory {
esp_err_t init();
void command(const char *text, char *reply, size_t capacity);
void set_listener(void (*callback)(int, fdd::State));
} // namespace laboratory
