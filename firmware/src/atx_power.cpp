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
uint32_t sequence = 0;
void (*listener)(atx::State) = nullptr;

void notify(atx::State value) {
    portENTER_CRITICAL(&lock);
    auto callback = listener;
    portEXIT_CRITICAL(&lock);
    if (callback) callback(value);
}

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
        bool changed = false;
        portENTER_CRITICAL(&lock);
        if (stable == 1) armed = true;
        else if (armed) {
            armed = false;
            if (!maintenance) {
                on = !on;
                ++sequence;
                changed = true;
                gpio_set_level(output, on);
            }
        }
        atx::State next = {on, sequence};
        portEXIT_CRITICAL(&lock);
        if (changed) notify(next);
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

atx::State atx::state() {
    portENTER_CRITICAL(&lock);
    State value = {on, sequence};
    portEXIT_CRITICAL(&lock);
    return value;
}

bool atx::is_on() { return state().on; }

void atx::set_listener(void (*callback)(State)) {
    portENTER_CRITICAL(&lock);
    listener = callback;
    portEXIT_CRITICAL(&lock);
}

bool atx::set(bool requested) {
    portENTER_CRITICAL(&lock);
    bool accepted = !requested || !maintenance;
    bool changed = accepted && on != requested;
    if (changed) ++sequence;
    if (accepted) {
        on = requested;
        gpio_set_level(output, on);
    }
    State value = {on, sequence};
    portEXIT_CRITICAL(&lock);
    if (changed) notify(value);
    return accepted;
}

void atx::prepare() {
    portENTER_CRITICAL(&lock);
    maintenance = true;
    bool changed = on;
    if (changed) ++sequence;
    on = false;
    gpio_set_level(output, 0);
    State value = {on, sequence};
    portEXIT_CRITICAL(&lock);
    if (changed) notify(value);
}
