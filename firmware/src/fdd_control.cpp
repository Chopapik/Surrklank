#include "fdd_control.h"
#include "atx_power.h"
#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_rom_sys.h"
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
TaskHandle_t reporting_task;
fdd::State pending_reports[8];
uint8_t pending_report_mask = 0;
using Listener = void (*)(int, fdd::State);
std::atomic<Listener> listener{nullptr};
constexpr gpio_num_t data = GPIO_NUM_23, clock595 = GPIO_NUM_18, latch = GPIO_NUM_22, oe = GPIO_NUM_21,
                     dvd_data = GPIO_NUM_17, dvd_latch = GPIO_NUM_16;
constexpr gpio_num_t load = GPIO_NUM_33, clock165 = GPIO_NUM_32, input = GPIO_NUM_34;
bool powered = false;
uint32_t previous = 0;
// Temporary bench instrumentation. Captures software latch timestamps only;
// printing happens in the report task after a drive reaches a terminal state.
struct CadenceProbe {
    uint32_t batch = 0, intervals = 0, outside_100us = 0, widths = 0;
    int64_t last = 0, sum = 0, squares = 0;
    int minimum = 1000000000, maximum = 0, low_minimum = 1000000000, low_maximum = 0;
    bool plateau = false, toward_zero = false, reported = false;
};
CadenceProbe probes[8];
void probe_edges(uint32_t before, uint32_t after, int64_t edge) {
    for (int i = 0; i < 8; ++i) {
        const auto &drive = engine.drives[i];
        const auto &s = drive.state;
        const uint32_t bit = 1UL << ((i / 2) * 8 + (i % 2 ? 1 : 4));
        auto &p = probes[i];
        if ((before & bit) && !(after & bit) && s.phase == fdd::Phase::playing) {
            if (p.batch != s.batch) {
                p = CadenceProbe{};
                p.batch = s.batch;
            }
            const bool plateau = s.rate < 200000 ||
                (drive.startup_steps >= 8 && drive.seek > 2);
            if (p.last && plateau && p.plateau && p.toward_zero == s.toward_zero) {
                const int gap = int(edge - p.last);
                const int64_t error = gap - 1000000000LL / s.rate;
                ++p.intervals;
                p.sum += gap;
                p.squares += int64_t(gap) * gap;
                if (gap < p.minimum) p.minimum = gap;
                if (gap > p.maximum) p.maximum = gap;
                if (error < -100 || error > 100) ++p.outside_100us;
            }
            p.last = edge;
            p.plateau = plateau;
            p.toward_zero = s.toward_zero;
        } else if (!(before & bit) && (after & bit) && s.phase == fdd::Phase::playing && p.last) {
            const int width = int(edge - p.last);
            ++p.widths;
            if (width < p.low_minimum) p.low_minimum = width;
            if (width > p.low_maximum) p.low_maximum = width;
        }
    }
}
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
        esp_rom_delay_us(1);
        gpio_set_level(clock595, 0);
        esp_rom_delay_us(1);
    }
    gpio_set_level(dvd_latch, 1);
    gpio_set_level(dvd_latch, 0);
    config.pin_bit_mask = 1ULL << input;
    config.mode = GPIO_MODE_INPUT;
    ESP_ERROR_CHECK(gpio_config(&config));
}
int64_t write(uint32_t image) {
    gpio_set_level(latch, 0);
    for (int bit = 31; bit >= 0; --bit) {
        gpio_set_level(data, (image >> bit) & 1);
        esp_rom_delay_us(1);
        gpio_set_level(clock595, 1);
        esp_rom_delay_us(1);
        gpio_set_level(clock595, 0);
    }
    gpio_set_level(latch, 1);
    int64_t edge = esp_timer_get_time();
    esp_rom_delay_us(1);
    gpio_set_level(latch, 0);
    return edge;
}
uint8_t read() {
    gpio_set_level(load, 0);
    esp_rom_delay_us(1);
    gpio_set_level(load, 1);
    esp_rom_delay_us(1);
    uint8_t bits = 0;
    for (int bit = 7; bit >= 0; --bit) {
        if (!gpio_get_level(input))
            bits |= 1 << bit;
        gpio_set_level(clock165, 1);
        esp_rom_delay_us(1);
        gpio_set_level(clock165, 0);
        esp_rom_delay_us(1);
    }
    return bits;
}
void release_pins() {
    gpio_set_level(oe, 1);
    for (auto pin : {data, clock595, latch, load, clock165, dvd_data, dvd_latch})
        gpio_set_direction(pin, GPIO_MODE_INPUT);
}
bool timer_alarm(gptimer_handle_t, const gptimer_alarm_event_data_t *, void *context) {
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(static_cast<TaskHandle_t>(context), &wake);
    return wake == pdTRUE;
}
void start_motion_timer() {
    gptimer_config_t config = {};
    config.clk_src = GPTIMER_CLK_SRC_DEFAULT;
    config.direction = GPTIMER_COUNT_UP;
    config.resolution_hz = 1000000;
    gptimer_handle_t handle;
    ESP_ERROR_CHECK(gptimer_new_timer(&config, &handle));
    gptimer_event_callbacks_t callbacks = {};
    callbacks.on_alarm = timer_alarm;
    ESP_ERROR_CHECK(gptimer_register_event_callbacks(handle, &callbacks, xTaskGetCurrentTaskHandle()));
    gptimer_alarm_config_t alarm = {};
    alarm.alarm_count = 100;
    alarm.flags.auto_reload_on_alarm = true;
    ESP_ERROR_CHECK(gptimer_set_alarm_action(handle, &alarm));
    // Enable on the motion core so the interrupt is allocated there.
    ESP_ERROR_CHECK(gptimer_enable(handle));
    ESP_ERROR_CHECK(gptimer_start(handle));
}
void worker(void *) {
    start_motion_timer();
    uint32_t sequences[8] = {};
    int64_t published[8] = {};
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        bool report_ready = false;
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
            const uint8_t sensors = read();
            now = esp_timer_get_time();
            engine.tick(now, sensors);
            uint32_t image = engine.outputs();
            if (image != previous) {
                const int64_t edge = write(image);
                probe_edges(previous, image, edge);
                engine.steps_latched(previous, image, now, edge);
                previous = image;
                // Complete STEP before yielding or publishing.
                bool pulsing = false;
                for (const auto &drive : engine.drives)
                    pulsing |= drive.step_low;
                if (pulsing) {
                    esp_rom_delay_us(fdd::step_low_us);
                    engine.finish_pulses();
                    const uint32_t low = previous;
                    previous = engine.outputs();
                    const int64_t high = write(previous);
                    probe_edges(low, previous, high);
                }
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
                pending_reports[i] = state;
                pending_report_mask |= 1 << i;
                report_ready = true;
            }
        }
        xSemaphoreGive(mutex);
        if (report_ready)
            xTaskNotifyGive(reporting_task);
    }
}
void report_worker(void *) {
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        fdd::State reports[8];
        CadenceProbe completed[8];
        uint8_t complete = 0;
        xSemaphoreTake(mutex, portMAX_DELAY);
        const uint8_t changed = pending_report_mask;
        pending_report_mask = 0;
        for (int i = 0; i < 8; ++i)
            if (changed & (1 << i)) {
                reports[i] = pending_reports[i];
                if ((reports[i].phase == fdd::Phase::stopped || reports[i].phase == fdd::Phase::error) &&
                    probes[i].intervals && !probes[i].reported && probes[i].batch == reports[i].batch) {
                    completed[i] = probes[i];
                    probes[i].reported = true;
                    complete |= 1 << i;
                }
            }
        xSemaphoreGive(mutex);
        auto callback = listener.load();
        for (int i = 0; i < 8; ++i)
            if ((changed & (1 << i)) && callback)
                callback(i + 1, reports[i]);
        for (int i = 0; i < 8; ++i)
            if (complete & (1 << i)) {
                const auto &p = completed[i];
                printf("FDD_CADENCE device=%d batch=%lu target_mhz=%lu n=%lu sum_us=%lld sum_sq_us=%lld min_us=%d max_us=%d outside_100us=%lu widths=%lu low_min_us=%d low_max_us=%d\n",
                    i + 1, (unsigned long)p.batch, (unsigned long)reports[i].rate, (unsigned long)p.intervals,
                    (long long)p.sum, (long long)p.squares, p.minimum, p.maximum,
                    (unsigned long)p.outside_100us, (unsigned long)p.widths, p.low_minimum, p.low_maximum);
                fflush(stdout);
            }
    }
}
} // namespace
esp_err_t laboratory::init() {
    boot_id = esp_random();
    mutex = xSemaphoreCreateMutex();
    if (!mutex)
        return ESP_ERR_NO_MEM;
    if (xTaskCreate(report_worker, "fdd_reports", 4096, nullptr, 5, &reporting_task) != pdPASS)
        return ESP_ERR_NO_MEM;
    if (xTaskCreatePinnedToCore(worker, "fdd", 4096, nullptr, 10, &task, 1) != pdPASS) {
        vTaskDelete(reporting_task);
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
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
