#pragma once
#include "esp_err.h"
#include <stddef.h>
namespace ota {
esp_err_t init();
void disconnected();
void describe(char* output,size_t capacity);
esp_err_t confirm();
esp_err_t reboot();
}
