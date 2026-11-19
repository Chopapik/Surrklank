#include "atx_power.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

namespace {
constexpr gpio_num_t output = GPIO_NUM_19;
constexpr gpio_num_t button = GPIO_NUM_13;
constexpr gpio_num_t power_good = GPIO_NUM_36; // PWR_OK via 10 k / 20 k divider
portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
bool on = false;
bool maintenance = false;
bool instruments = false;
uint32_t sequence = 0;
void (*listener)(atx::State) = nullptr;
// PWR_OK must hold one level for this many 10 ms samples (about 50 ms).
constexpr unsigned power_samples = 5;
bool rails_up = false;
uint32_t rails_sequence = 0;
void (*rails_listener)(atx::Rails) = nullptr;

void notify(atx::State value) {
    portENTER_CRITICAL(&lock);
    auto callback = listener;
    portEXIT_CRITICAL(&lock);
    if (callback) callback(value);
}

void sample_power(int &previous, unsigned &ticks) {
    const int value = gpio_get_level(power_good);
    ticks = value == previous ? ticks + 1 : 1;
    previous = value;
    if (ticks < power_samples) return;
    portENTER_CRITICAL(&lock);
    const bool changed = rails_up != (value == 1);
    if (changed) {
        rails_up = value == 1;
        ++rails_sequence;
    }
    atx::Rails next = {rails_up, rails_sequence};
    auto callback = rails_listener;
    portEXIT_CRITICAL(&lock);
    if (changed && callback) callback(next);
}

void poll_button(void*) {
    int stable = gpio_get_level(button), previous = stable;
    bool armed = stable == 1;
    unsigned ticks = 0;
    int power_previous = rails_up ? 1 : 0;
    unsigned power_ticks = power_samples;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10));
        sample_power(power_previous, power_ticks);
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
            if (!maintenance && !instruments) {
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
    // GPIO36 has no internal pulls; the divider's lower resistor reads LOW
    // while the supply is unplugged.
    config.pin_bit_mask = 1ULL << power_good;
    config.pull_up_en = GPIO_PULLUP_DISABLE;
    ESP_ERROR_CHECK(gpio_config(&config));
    rails_up = gpio_get_level(power_good) == 1;
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

atx::Rails atx::rails() {
    portENTER_CRITICAL(&lock);
    Rails value = {rails_up, rails_sequence};
    portEXIT_CRITICAL(&lock);
    return value;
}

bool atx::rails_ok() { return rails().ok; }

void atx::set_rails_listener(void (*callback)(Rails)) {
    portENTER_CRITICAL(&lock);
    rails_listener = callback;
    portEXIT_CRITICAL(&lock);
}

void atx::set_listener(void (*callback)(State)) {
    portENTER_CRITICAL(&lock);
    listener = callback;
    portEXIT_CRITICAL(&lock);
}

bool atx::set(bool requested) {
    portENTER_CRITICAL(&lock);
    bool accepted = (!requested || !maintenance) && (!instruments || requested);
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

bool atx::prepare() {
    portENTER_CRITICAL(&lock);
    if (instruments) { portEXIT_CRITICAL(&lock); return false; }
    maintenance = true;
    bool changed = on;
    if (changed) ++sequence;
    on = false;
    gpio_set_level(output, 0);
    State value = {on, sequence};
    portEXIT_CRITICAL(&lock);
    if (changed) notify(value);
    return true;
}
bool atx::claim_instruments() {
    portENTER_CRITICAL(&lock);
    bool accepted=on && !maintenance;
    if(accepted) instruments=true;
    portEXIT_CRITICAL(&lock);
    return accepted;
}
void atx::release_instruments() {
    portENTER_CRITICAL(&lock);instruments=false;portEXIT_CRITICAL(&lock);
}
