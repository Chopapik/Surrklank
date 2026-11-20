#include "fdd_control.h"
#include "atx_power.h"
#include "drive_settings.h"
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
fdd::State pending_reports[fdd::count];
fdd::DriveMask pending_report_mask = 0;
using Listener = void (*)(int, fdd::State);
std::atomic<Listener> listener{nullptr};
constexpr gpio_num_t data = GPIO_NUM_23, clock595 = GPIO_NUM_18, latch = GPIO_NUM_22, oe = GPIO_NUM_21,
                     dvd_data = GPIO_NUM_17, dvd_latch = GPIO_NUM_16;
constexpr gpio_num_t load = GPIO_NUM_33, clock165 = GPIO_NUM_32, input = GPIO_NUM_34,
                     actuator_input = GPIO_NUM_35;
// Zero clocks for the actuator branch: more than four actuator modules plus a
// 16-LED board. Extra zeros only pass out of the chain end.
constexpr int actuator_clear_bits = 128;
// Actuator modules read for ULT (nFAULT); LSM1-4 and HDD1-4 need six slots.
constexpr int actuator_modules = 2;
constexpr int input_modules = fdd::modules > actuator_modules ? fdd::modules : actuator_modules;
// Bring-up wave: 8 ones then 8 zeros, one CLK every 125 ms. Each 595 QH' LED
// blinks at 0.5 Hz in the opposite phase of its neighbour.
constexpr int64_t bus_test_step_us = 125000;
bool powered = false;
fdd::Frame previous;
std::atomic<bool> bus_test{false};
std::atomic<int> actuator_fault_mask{-1};
unsigned bus_test_step = 0;
int64_t bus_test_due = 0;
// Temporary bench instrumentation. Captures software latch timestamps only;
// printing happens in the report task after a drive reaches a terminal state.
struct CadenceProbe {
    uint32_t batch = 0, intervals = 0, outside_100us = 0, widths = 0;
    int64_t last = 0, sum = 0, squares = 0;
    int minimum = 1000000000, maximum = 0, low_minimum = 1000000000, low_maximum = 0;
    bool plateau = false, toward_zero = false, reported = false;
};
CadenceProbe probes[fdd::count];
void probe_edges(const fdd::Frame &before, const fdd::Frame &after, int64_t edge) {
    for (int i = 0; i < fdd::count; ++i) {
        const auto &drive = engine.drives[i];
        const auto &s = drive.state;
        const fdd::Frame bit = fdd::output_mask(i, fdd::Line::step);
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
// Idle bus while ATX is off (docs/WIRING.md): DATA, CLK, LATCH and CLK165 LOW,
// /OE and /PL HIGH, so nothing back-powers or enables an unpowered module.
void idle_bus() {
    gpio_set_level(oe, 1);
    gpio_set_level(load, 1);
    for (auto pin : {data, clock595, latch, clock165, dvd_data, dvd_latch})
        gpio_set_level(pin, 0);
}
void configure_bus() {
    idle_bus();
    gpio_config_t config = {};
    config.pin_bit_mask = (1ULL << data) | (1ULL << clock595) | (1ULL << latch) | (1ULL << oe) | (1ULL << load) |
                          (1ULL << clock165) | (1ULL << dvd_data) | (1ULL << dvd_latch);
    config.mode = GPIO_MODE_OUTPUT;
    ESP_ERROR_CHECK(gpio_config(&config));
    config.pin_bit_mask = (1ULL << input) | (1ULL << actuator_input);
    config.mode = GPIO_MODE_INPUT;
    ESP_ERROR_CHECK(gpio_config(&config));
}
// LSM/HDD playback is not implemented: all-zero IN and EEP keep every DRV8833
// asleep and coasting, and LED board outputs dark.
void clear_actuators() {
    gpio_set_level(dvd_data, 0);
    for (int i = 0; i < actuator_clear_bits; ++i) {
        gpio_set_level(clock595, 1);
        esp_rom_delay_us(1);
        gpio_set_level(clock595, 0);
        esp_rom_delay_us(1);
    }
    gpio_set_level(dvd_latch, 1);
    esp_rom_delay_us(1);
    gpio_set_level(dvd_latch, 0);
}
// Shares CLK with the actuator branch; its DATA stays LOW and its LATCH is not
// pulsed, so actuator outputs keep the cleared frame.
int64_t write(const fdd::Frame &image) {
    gpio_set_level(latch, 0);
    for (int bit = fdd::frame_bits - 1; bit >= 0; --bit) {
        gpio_set_level(data, image.test(bit));
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
struct Inputs {
    uint32_t fdd = 0, actuator = 0; // 8 bits per module, module 1 lowest
};
// Both branches share /PL and CLK165, so one pass reads both chains. Module 1
// is read first, D7 to D0, then module 2. Active LOW inputs become set bits.
Inputs read() {
    gpio_set_level(load, 0);
    esp_rom_delay_us(1);
    gpio_set_level(load, 1);
    esp_rom_delay_us(1);
    Inputs bits;
    for (int module = 0; module < input_modules; ++module)
        for (int bit = 7; bit >= 0; --bit) {
            if (!gpio_get_level(input))
                bits.fdd |= 1u << (module * 8 + bit);
            if (!gpio_get_level(actuator_input))
                bits.actuator |= 1u << (module * 8 + bit);
            gpio_set_level(clock165, 1);
            esp_rom_delay_us(1);
            gpio_set_level(clock165, 0);
            esp_rom_delay_us(1);
        }
    return bits;
}
// ULT of slots M1-M4 sits on D0-D3; D4-D7 are tied to GND and ignored.
// Result bit k is module k / 4, slot k % 4.
int actuator_faults(uint32_t inputs) {
    int faults = 0;
    for (int module = 0; module < actuator_modules; ++module)
        faults |= ((inputs >> (module * 8)) & 0x0f) << (module * 4);
    return faults;
}
// Clocks one wave bit into both branches without LATCH: only the shift
// registers and their QH' outputs change, never the drive or DRV8833 lines.
void step_bus_test() {
    const int level = (bus_test_step / 8) % 2 == 0;
    gpio_set_level(data, level);
    gpio_set_level(dvd_data, level);
    esp_rom_delay_us(1);
    gpio_set_level(clock595, 1);
    esp_rom_delay_us(1);
    gpio_set_level(clock595, 0);
    ++bus_test_step;
}
void stop_bus_test() {
    bus_test = false;
    gpio_set_level(data, 0);
    gpio_set_level(dvd_data, 0);
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
    uint32_t sequences[fdd::count] = {};
    int64_t published[fdd::count] = {};
    for (;;) {
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        bool report_ready = false;
        xSemaphoreTake(mutex, portMAX_DELAY);
        int64_t now = esp_timer_get_time();
        // The bus is live only with the ATX request ON and PWR_OK HIGH, so the
        // modules are powered before the safe frame and after every PWR_OK return.
        const bool live = atx::is_on() && atx::rails_ok();
        if (live && !powered) {
            clear_actuators();
            previous = engine.outputs();
            write(previous);
            gpio_set_level(oe, 0);
            powered = true;
        }
        if (!live && powered) {
            bus_test = false;
            idle_bus();
            powered = false;
            actuator_fault_mask = -1;
            engine.power_lost(now);
        }
        if (powered) {
            const Inputs inputs = read();
            const fdd::DriveMask track0 = fdd::track0_inputs(inputs.fdd);
            actuator_fault_mask = actuator_faults(inputs.actuator);
            if (bus_test && now >= bus_test_due) {
                step_bus_test();
                bus_test_due += bus_test_step_us;
            }
            now = esp_timer_get_time();
            engine.tick(now, track0);
            fdd::Frame image = engine.outputs();
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
                    const fdd::Frame low = previous;
                    previous = engine.outputs();
                    const int64_t high = write(previous);
                    probe_edges(low, previous, high);
                }
            }
        }
        for (int i = 0; i < fdd::count; ++i)
            history.observe(i + 1, engine.drives[i].state, esp_timer_get_time());
        if (!engine.busy())
            atx::release_instruments();
        for (int i = 0; i < fdd::count; ++i) {
            auto &state = engine.drives[i].state;
            if (state.sequence != sequences[i] || (now - published[i] >= (engine.busy() ? 250000 : 1000000))) {
                if (state.sequence == sequences[i])
                    ++state.sequence;
                sequences[i] = state.sequence;
                published[i] = now;
                pending_reports[i] = state;
                pending_report_mask |= fdd::DriveMask(1u << i);
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
        fdd::State reports[fdd::count];
        CadenceProbe completed[fdd::count];
        fdd::DriveMask complete = 0;
        xSemaphoreTake(mutex, portMAX_DELAY);
        const fdd::DriveMask changed = pending_report_mask;
        pending_report_mask = 0;
        for (int i = 0; i < fdd::count; ++i)
            if (changed & (1 << i)) {
                reports[i] = pending_reports[i];
                if ((reports[i].phase == fdd::Phase::stopped || reports[i].phase == fdd::Phase::error) &&
                    probes[i].intervals && !probes[i].reported && probes[i].batch == reports[i].batch) {
                    completed[i] = probes[i];
                    probes[i].reported = true;
                    complete |= fdd::DriveMask(1u << i);
                }
            }
        xSemaphoreGive(mutex);
        auto callback = listener.load();
        for (int i = 0; i < fdd::count; ++i)
            if ((changed & (1 << i)) && callback)
                callback(i + 1, reports[i]);
        for (int i = 0; i < fdd::count; ++i)
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
    drive_settings::load(engine.select);
    configure_bus();
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
    if (sscanf(text, "LAB INFO %u %c", &device, &end) == 1 && device >= 1 && device <= unsigned(fdd::count)) {
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
    if (sscanf(text, "LAB BEGIN %u %u %c", &batch, &mask, &end) == 2 && mask > 0 && mask < (1u << fdd::count)) {
        if (!bus_test && powered && atx::claim_instruments())
            ok = engine.begin(batch, fdd::DriveMask(mask), now);
    } else if (sscanf(text, "LAB SET %u %u %u %u %c", &batch, &device, &rate, &duration, &end) == 4)
        ok = engine.configure(batch, device, rate, duration);
    else if (sscanf(text, "LAB PREPARE %u %c", &batch, &end) == 1)
        ok = engine.prepare(batch, now);
    else if (sscanf(text, "LAB COMMIT %u %c", &batch, &end) == 1)
        ok = engine.commit(batch, now);
    else if (sscanf(text, "LAB ABORT %u %c", &batch, &end) == 1) {
        engine.abort(batch, now);
        ok = true;
    } else if (sscanf(text, "LAB STOP %u %c", &device, &end) == 1 && device >= 1 && device <= unsigned(fdd::count)) {
        engine.stop(device, now);
        ok = true;
    } else if (!strcmp(text, "LAB STOPALL")) {
        engine.stop_all(now);
        ok = true;
    }
    for (int i = 0; i < fdd::count; ++i)
        history.observe(i + 1, engine.drives[i].state, esp_timer_get_time());
    if (!engine.busy())
        atx::release_instruments();
    snprintf(reply, capacity, "%s", ok ? "LAB OK" : "ERR LAB BUSY OR INVALID");
    xSemaphoreGive(mutex);
}
bool laboratory::set_bus_test(bool enabled) {
    xSemaphoreTake(mutex, portMAX_DELAY);
    // The test needs powered modules and never shares the bus with motion.
    const bool accepted = !enabled || (powered && !engine.busy());
    if (accepted && enabled && !bus_test) {
        bus_test_step = 0;
        bus_test_due = esp_timer_get_time();
        bus_test = true;
    } else if (accepted && !enabled && bus_test)
        stop_bus_test();
    xSemaphoreGive(mutex);
    return accepted;
}
bool laboratory::bus_test_active() {
    return bus_test;
}
int laboratory::actuator_faults() {
    return actuator_fault_mask;
}
laboratory::SelectResult laboratory::set_select(int device, fdd::Line line) {
    if (device < 1 || device > fdd::count || !fdd::is_select(line))
        return SelectResult::invalid;
    xSemaphoreTake(mutex, portMAX_DELAY);
    SelectResult result = SelectResult::busy;
    if (!engine.busy() && !engine.pending) {
        fdd::Line lines[fdd::count];
        for (int i = 0; i < fdd::count; ++i)
            lines[i] = engine.select[i];
        lines[device - 1] = line;
        // No drive moves while idle, so the NVS write may hold the mutex.
        result = drive_settings::store(lines) == ESP_OK && engine.set_select(device, line)
            ? SelectResult::ok : SelectResult::storage;
    }
    xSemaphoreGive(mutex);
    return result;
}
void laboratory::select_lines(fdd::Line (&lines)[fdd::count]) {
    xSemaphoreTake(mutex, portMAX_DELAY);
    for (int i = 0; i < fdd::count; ++i)
        lines[i] = engine.select[i];
    xSemaphoreGive(mutex);
}
