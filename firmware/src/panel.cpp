#include "panel.h"
#include "atx_power.h"
#include "ble_connection.h"
#include "fdd_control.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <atomic>

namespace {
constexpr gpio_num_t sda = GPIO_NUM_25, scl = GPIO_NUM_26, interrupt_pin = GPIO_NUM_27;
constexpr uint16_t expander_address = 0x20;
constexpr uint32_t bus_hz = 100000;
constexpr int timeout_ms = 20;
// MCP23017 registers with IOCON.BANK = 0.
constexpr uint8_t iodira = 0x00, iodirb = 0x01, gpintena = 0x04, intcona = 0x08, iocon = 0x0a,
                  gppua = 0x0c, gppub = 0x0d, gpioa = 0x12, olatb = 0x15;
// IOCON: MIRROR joins INTA/INTB on the INT line, ODR makes it open-drain
// against the mainboard pull-up.
constexpr uint8_t iocon_value = 0x44;
constexpr uint8_t button_inputs = 0x7f; // GPA0-GPA6 (GPA7 is output only)
constexpr uint8_t led_outputs = 0x03;   // GPB0 ATX ON, GPB1 ESP
constexpr uint8_t atx_led = 0x01, esp_led = 0x02;
constexpr TickType_t tick = pdMS_TO_TICKS(100);
constexpr unsigned heartbeat_ticks = 5; // ESP LED toggles every 0.5 s (1 Hz)
constexpr TickType_t settle = pdMS_TO_TICKS(20);
constexpr int max_settle_reads = 5;

i2c_master_dev_handle_t expander;
TaskHandle_t task = nullptr;
std::atomic<bool> available{false};
using Listener = void (*)(uint8_t, uint32_t);
std::atomic<Listener> listener{nullptr};
uint8_t pressed = 0; // debounced, bit set = pressed
uint32_t sequence = 0;
unsigned ticks = 0;
bool blink = false;
int written = -1; // last OLATB value

bool write(uint8_t reg, uint8_t value) {
    const uint8_t bytes[2] = {reg, value};
    return i2c_master_transmit(expander, bytes, sizeof(bytes), timeout_ms) == ESP_OK;
}
bool read(uint8_t reg, uint8_t &value) {
    return i2c_master_transmit_receive(expander, &reg, 1, &value, 1, timeout_ms) == ESP_OK;
}
// A failed transfer ends panel I/O until restart; playing and ATX continue.
void lose() { available = false; }

void press(uint8_t button) {
    // STOP is local so it works without the app; it stops every drive.
    if (button == panel::stop) {
        char reply[32];
        laboratory::command("LAB STOPALL", reply, sizeof(reply));
    }
    ++sequence;
    if (auto callback = listener.load())
        callback(button, sequence);
}

// Reading GPIOA clears the expander interrupt. A level counts only when two
// reads 20 ms apart agree; a change inside that window is read again, because
// its interrupt was already cleared and no further edge would arrive.
void read_buttons() {
    uint8_t first = 0, second = 0;
    if (!read(gpioa, first))
        return lose();
    for (int attempt = 0; attempt < max_settle_reads; ++attempt) {
        vTaskDelay(settle);
        if (!read(gpioa, second))
            return lose();
        if (((first ^ second) & button_inputs) == 0)
            break;
        first = second;
    }
    const uint8_t stable = ~(first ^ second) & button_inputs;
    const uint8_t level = ~second & button_inputs; // active LOW
    const uint8_t next = (pressed & ~stable) | (level & stable);
    const uint8_t presses = next & ~pressed;
    pressed = next;
    for (int bit = 0; bit < 7; ++bit)
        if (presses & (1u << bit))
            press(bit + 1);
}

// The heartbeat write doubles as the only check that the panel still answers.
void update_leds(bool heartbeat) {
    const uint8_t value = (atx::is_on() ? atx_led : 0) | (ble::connected() || blink ? esp_led : 0);
    if (value == written && !heartbeat)
        return;
    if (!write(olatb, value))
        return lose();
    written = value;
}

void service(bool interrupted) {
    if (!available)
        return;
    if (interrupted)
        read_buttons();
    if (!available)
        return;
    const bool heartbeat = ++ticks >= heartbeat_ticks;
    if (heartbeat) {
        ticks = 0;
        blink = !blink;
    }
    update_leds(heartbeat);
}

void run(void *) {
    for (;;)
        service(ulTaskNotifyTake(pdTRUE, tick) > 0);
}

void on_interrupt(void *) {
    BaseType_t wake = pdFALSE;
    vTaskNotifyGiveFromISR(task, &wake);
    portYIELD_FROM_ISR(wake);
}

bool configure() {
    i2c_master_bus_config_t bus_config = {};
    bus_config.i2c_port = -1;
    bus_config.sda_io_num = sda;
    bus_config.scl_io_num = scl;
    bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_config.glitch_ignore_cnt = 7;
    // The mainboard has 2.2 kOhm pull-ups for the 2 m cable.
    bus_config.flags.enable_internal_pullup = false;
    i2c_master_bus_handle_t bus;
    if (i2c_new_master_bus(&bus_config, &bus) != ESP_OK)
        return false;
    i2c_device_config_t device = {};
    device.dev_addr_length = I2C_ADDR_BIT_LEN_7;
    device.device_address = expander_address;
    device.scl_speed_hz = bus_hz;
    if (i2c_master_bus_add_device(bus, &device, &expander) != ESP_OK)
        return false;
    const bool written_all = write(iocon, iocon_value) && write(iodira, button_inputs) &&
                             write(gppua, button_inputs) && write(intcona, 0) && write(gpintena, button_inputs) &&
                             write(olatb, 0) && write(iodirb, static_cast<uint8_t>(~led_outputs)) &&
                             write(gppub, static_cast<uint8_t>(~led_outputs));
    uint8_t check = 0, buttons = 0;
    // Reading back a register proves an MCP23017 answers, not only an ACK.
    if (!written_all || !read(iodira, check) || check != button_inputs || !read(gpioa, buttons))
        return false;
    pressed = ~buttons & button_inputs; // held at start: not a press
    return true;
}
} // namespace

esp_err_t panel::init() {
    if (!configure()) {
        atx::set_panel(false);
        return ESP_OK; // absence is a state, not an init error
    }
    written = 0;
    available = true;
    if (xTaskCreatePinnedToCore(run, "panel", 3072, nullptr, 3, &task, 0) != pdPASS) {
        available = false;
        atx::set_panel(false);
        return ESP_ERR_NO_MEM;
    }
    gpio_config_t config = {};
    config.pin_bit_mask = 1ULL << interrupt_pin;
    config.mode = GPIO_MODE_INPUT;
    config.intr_type = GPIO_INTR_NEGEDGE;
    ESP_ERROR_CHECK(gpio_config(&config));
    const esp_err_t service_error = gpio_install_isr_service(0);
    if (service_error != ESP_OK && service_error != ESP_ERR_INVALID_STATE)
        return service_error;
    ESP_ERROR_CHECK(gpio_isr_handler_add(interrupt_pin, on_interrupt, nullptr));
    atx::set_panel(true);
    return ESP_OK;
}

bool panel::present() { return available; }

void panel::set_listener(void (*callback)(uint8_t, uint32_t)) { listener = callback; }
