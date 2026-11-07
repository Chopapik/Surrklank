#include "atx_power.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {
constexpr gpio_num_t output = GPIO_NUM_19;
constexpr gpio_num_t button = GPIO_NUM_13;
portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
bool on = false;
bool maintenance = false;

void poll_button(void*) {
    int stable = gpio_get_level(button), previous = stable;
    bool armed = stable == 1;
    unsigned ticks = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10));
        int value = gpio_get_level(button);
        ticks = value == previous ? ticks + 1 : 0;
        previous = value;
        if (ticks < 3 || value == stable) continue;
        stable = value;
        portENTER_CRITICAL(&lock);
        if (stable == 1) armed = true;
        else if (armed) {
            armed = false;
            if (!maintenance) {
                on = !on;
                gpio_set_level(output, on);
            }
        }
        portEXIT_CRITICAL(&lock);
    }
}
}

esp_err_t atx::init() {
    gpio_set_level(output, 0);
    gpio_config_t config = {};
    config.pin_bit_mask = 1ULL << output;
    config.mode = GPIO_MODE_OUTPUT;
    ESP_ERROR_CHECK(gpio_config(&config));
    config.pin_bit_mask = 1ULL << button;
    config.mode = GPIO_MODE_INPUT;
    config.pull_up_en = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&config));
    return xTaskCreate(poll_button, "atx_button", 2048, nullptr, 2, nullptr) == pdPASS
        ? ESP_OK : ESP_ERR_NO_MEM;
}

bool atx::is_on() {
    portENTER_CRITICAL(&lock);
    bool value = on;
    portEXIT_CRITICAL(&lock);
    return value;
}

bool atx::set(bool requested) {
    portENTER_CRITICAL(&lock);
    bool accepted = !requested || !maintenance;
    if (accepted) {
        on = requested;
        gpio_set_level(output, on);
    }
    portEXIT_CRITICAL(&lock);
    return accepted;
}

void atx::prepare() {
    portENTER_CRITICAL(&lock);
    maintenance = true;
    on = false;
    gpio_set_level(output, 0);
    portEXIT_CRITICAL(&lock);
}

