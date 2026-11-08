#include "fdd_control.h"
#include "atx_power.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "laboratory_timing.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <atomic>

namespace {
fdd::Engine engine;
laboratory::EventHistory history;
uint32_t boot_id;
SemaphoreHandle_t mutex;
TaskHandle_t task;
using Listener = void (*)(int, fdd::State);
std::atomic<Listener> listener{nullptr};
constexpr gpio_num_t data = GPIO_NUM_23, clock595 = GPIO_NUM_18, latch = GPIO_NUM_22, oe = GPIO_NUM_21,
                     dvd_data = GPIO_NUM_17, dvd_latch = GPIO_NUM_16;
constexpr gpio_num_t load = GPIO_NUM_33, clock165 = GPIO_NUM_32, input = GPIO_NUM_34;
bool powered = false;
uint32_t previous = 0;
void setup() {
    gpio_config_t config = {};
    config.pin_bit_mask = (1ULL << data) | (1ULL << clock595) | (1ULL << latch) | (1ULL << oe) | (1ULL << load) |
                          (1ULL << clock165) | (1ULL << dvd_data) | (1ULL << dvd_latch);
    gpio_set_level(oe, 1);
    gpio_set_level(latch, 0);
    gpio_set_level(clock595, 0);
    gpio_set_level(clock165, 0);
    gpio_set_level(load, 1);
    gpio_set_level(dvd_data, 0);
    gpio_set_level(dvd_latch, 0);
    config.mode = GPIO_MODE_OUTPUT;
    ESP_ERROR_CHECK(gpio_config(&config));
    for (int i = 0; i < 24; ++i) {
        gpio_set_level(clock595, 1);
        gpio_set_level(clock595, 0);
    }
    gpio_set_level(dvd_latch, 1);
    gpio_set_level(dvd_latch, 0);
    config.pin_bit_mask = 1ULL << input;
    config.mode = GPIO_MODE_INPUT;
    ESP_ERROR_CHECK(gpio_config(&config));
}
void write(uint32_t image) {
    gpio_set_level(latch, 0);
    for (int bit = 31; bit >= 0; --bit) {
        gpio_set_level(data, (image >> bit) & 1);
        gpio_set_level(clock595, 1);
        gpio_set_level(clock595, 0);
    }
    gpio_set_level(latch, 1);
    gpio_set_level(latch, 0);
}
uint8_t read() {
    gpio_set_level(load, 0);
    gpio_set_level(load, 1);
    uint8_t bits = 0;
    for (int bit = 7; bit >= 0; --bit) {
        if (!gpio_get_level(input))
            bits |= 1 << bit;
        gpio_set_level(clock165, 1);
        gpio_set_level(clock165, 0);
    }
    return bits;
}
void release_pins() {
    gpio_set_level(oe, 1);
    for (auto pin : {data, clock595, latch, load, clock165, dvd_data, dvd_latch})
        gpio_set_direction(pin, GPIO_MODE_INPUT);
}
void worker(void *) {
    uint32_t sequences[8] = {};
    int64_t published[8] = {};
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        fdd::State reports[8];
        bool changed[8] = {};
        xSemaphoreTake(mutex, portMAX_DELAY);
        int64_t now = esp_timer_get_time();
        bool on = atx::is_on();
        if (on && !powered) {
            setup();
            previous = engine.outputs();
            write(previous);
            gpio_set_level(oe, 0);
            powered = true;
        }
        if (!on && powered) {
            release_pins();
            powered = false;
            engine.power_lost();
        }
        if (powered) {
            engine.tick(now, read());
            uint32_t image = engine.outputs();
            if (image != previous) {
                write(image);
                previous = image;
            }
        }
        for (int i = 0; i < 8; ++i)
            history.observe(i + 1, engine.drives[i].state, esp_timer_get_time());
        if (!engine.busy())
            atx::release_instruments();
        for (int i = 0; i < 8; ++i) {
            auto &state = engine.drives[i].state;
            if (state.sequence != sequences[i] || (now - published[i] >= (engine.busy() ? 250000 : 1000000))) {
                if (state.sequence == sequences[i])
                    ++state.sequence;
                sequences[i] = state.sequence;
                published[i] = now;
                reports[i] = state;
                changed[i] = true;
            }
        }
        xSemaphoreGive(mutex);
        auto callback = listener.load();
        for (int i = 0; i < 8; ++i)
            if (changed[i] && callback)
                callback(i + 1, reports[i]);
    }
}
void timer(void *) {
    if (task)
        xTaskNotifyGive(task);
}
} // namespace
esp_err_t laboratory::init() {
    boot_id = esp_random();
    mutex = xSemaphoreCreateMutex();
    if (!mutex)
        return ESP_ERR_NO_MEM;
    if (xTaskCreate(worker, "fdd", 4096, nullptr, 10, &task) != pdPASS)
        return ESP_ERR_NO_MEM;
    esp_timer_create_args_t args = {};
    args.callback = timer;
    args.name = "fdd_tick";
    esp_timer_handle_t handle;
    ESP_ERROR_CHECK(esp_timer_create(&args, &handle));
    return esp_timer_start_periodic(handle, 100);
}
void laboratory::set_listener(void (*callback)(int, fdd::State)) {
    listener = callback;
}
void laboratory::command(const char *text, char *reply, size_t capacity) {
    int64_t received = esp_timer_get_time();
    if (!strcmp(text, "LAB CLOCK")) {
        xSemaphoreTake(mutex, portMAX_DELAY);
        uint32_t cursor = history.latest;
        xSemaphoreGive(mutex);
        snprintf(reply, capacity, "{\"timing_version\":1,\"event_cursor\":%lu,\"esp_boot_id\":%lu,\"esp_receive_time_us\":%lld,\"esp_send_time_us\":%lld}",
                 (unsigned long)cursor, (unsigned long)boot_id, (long long)received, (long long)esp_timer_get_time());
        return;
    }
    unsigned cursor = 0;
    char trailing = 0;
    if (sscanf(text, "LAB EVENT %u %c", &cursor, &trailing) == 1) {
        xSemaphoreTake(mutex, portMAX_DELAY);
        auto e = history.after(cursor);
        if (e) {
            snprintf(reply, capacity, "{\"esp_boot_id\":%lu,\"latest\":%lu,\"event\":{\"event_sequence\":%lu,\"batch\":%lu,\"device\":%u,\"state\":\"%s\",\"toward_zero\":%s,\"esp_event_time_us\":%lld}}",
                     (unsigned long)boot_id, (unsigned long)history.latest, (unsigned long)e->sequence,
                     (unsigned long)e->batch, e->device, fdd::name(e->phase), e->toward_zero ? "true" : "false", (long long)e->time_us);
        } else snprintf(reply, capacity, "{\"esp_boot_id\":%lu,\"latest\":%lu,\"event\":null}", (unsigned long)boot_id, (unsigned long)history.latest);
        xSemaphoreGive(mutex);
        return;
    }
    unsigned batch = 0, mask = 0, device = 0, rate = 0, duration = 0;
    char end = 0;
    xSemaphoreTake(mutex, portMAX_DELAY);
    int64_t now = esp_timer_get_time();
    bool ok = false;
    if (sscanf(text, "LAB INFO %u %c", &device, &end) == 1 && device >= 1 && device <= 8) {
        auto s = engine.drives[device - 1].state;
        snprintf(reply, capacity,
                 "{\"device\":%u,\"sequence\":%lu,\"batch\":%lu,\"state\":\"%s\",\"frequency_hz\":%.3f,\"duration_ms\":"
                 "%lu,\"elapsed_ms\":%lu,\"track0\":%s,\"left_track0\":%s,\"toward_zero\":%s,\"steps_issued\":%u,"
                 "\"return_steps\":%u,\"position_estimate\":%d,\"error_code\":%u}",
                 device, (unsigned long)s.sequence, (unsigned long)s.batch, fdd::name(s.phase), s.rate / 1000.0,
                 (unsigned long)s.duration, (unsigned long)s.elapsed,
                 s.track_valid ? (s.track0 ? "true" : "false") : "null", s.left ? "true" : "false",
                 s.toward_zero ? "true" : "false", s.steps, s.return_steps, s.position, (unsigned)s.error);
        xSemaphoreGive(mutex);
        return;
    }
    if (sscanf(text, "LAB BEGIN %u %u %c", &batch, &mask, &end) == 2 && mask > 0 && mask <= 255) {
        if (atx::claim_instruments())
            ok = engine.begin(batch, (uint8_t)mask, now);
    } else if (sscanf(text, "LAB SET %u %u %u %u %c", &batch, &device, &rate, &duration, &end) == 4)
        ok = engine.configure(batch, device, rate, duration);
    else if (sscanf(text, "LAB PREPARE %u %c", &batch, &end) == 1)
        ok = engine.prepare(batch, now);
    else if (sscanf(text, "LAB COMMIT %u %c", &batch, &end) == 1)
        ok = engine.commit(batch, now);
    else if (sscanf(text, "LAB ABORT %u %c", &batch, &end) == 1) {
        engine.abort(batch, now);
        ok = true;
    } else if (sscanf(text, "LAB STOP %u %c", &device, &end) == 1 && device >= 1 && device <= 8) {
        engine.stop(device, now);
        ok = true;
    } else if (!strcmp(text, "LAB STOPALL")) {
        engine.stop_all(now);
        ok = true;
    }
    for (int i = 0; i < 8; ++i)
        history.observe(i + 1, engine.drives[i].state, esp_timer_get_time());
    if (!engine.busy())
        atx::release_instruments();
    snprintf(reply, capacity, "%s", ok ? "LAB OK" : "ERR LAB BUSY OR INVALID");
    xSemaphoreGive(mutex);
}
