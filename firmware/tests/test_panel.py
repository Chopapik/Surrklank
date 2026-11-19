"""Run the real remote-panel module against I2C/GPIO/FreeRTOS stubs, without hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HEADERS = {
    "esp_err.h": """#pragma once
#include <cassert>
using esp_err_t = int;
constexpr int ESP_OK=0, ESP_FAIL=-1, ESP_ERR_NO_MEM=0x101, ESP_ERR_INVALID_STATE=0x103;
#define ESP_ERROR_CHECK(value) assert((value)==ESP_OK)
""",
    "driver/gpio.h": """#pragma once
#include <cstdint>
using gpio_num_t = int;
constexpr int GPIO_NUM_25=25, GPIO_NUM_26=26, GPIO_NUM_27=27;
constexpr int GPIO_MODE_INPUT=1, GPIO_INTR_NEGEDGE=2;
struct gpio_config_t { uint64_t pin_bit_mask; int mode; int pull_up_en; int pull_down_en; int intr_type; };
inline int interruptType=0;
inline void (*isrHandler)(void*)=nullptr;
inline int gpio_config(const gpio_config_t* c) { interruptType=c->intr_type; return 0; }
inline int gpio_install_isr_service(int) { return 0; }
inline int gpio_isr_handler_add(int pin, void (*handler)(void*), void*) { assert(pin==27); isrHandler=handler; return 0; }
""",
    "driver/i2c_master.h": """#pragma once
#include "esp_err.h"
#include <cstddef>
#include <cstdint>
#include <deque>
using i2c_master_bus_handle_t = int;
using i2c_master_dev_handle_t = int;
using i2c_port_num_t = int;
using i2c_clock_source_t = int;
constexpr int I2C_CLK_SRC_DEFAULT=0, I2C_ADDR_BIT_LEN_7=0;
struct i2c_master_bus_config_t { i2c_port_num_t i2c_port; int sda_io_num, scl_io_num; i2c_clock_source_t clk_source;
    uint8_t glitch_ignore_cnt; int intr_priority; size_t trans_queue_depth; struct { uint32_t enable_internal_pullup:1; } flags; };
struct i2c_device_config_t { int dev_addr_length; uint16_t device_address; uint32_t scl_speed_hz; };
// Fake MCP23017: registers, GPIOA levels queued per read, a switch for NACK.
inline uint8_t registers[0x16]={};
inline bool answers=true;
inline uint8_t gpioaLevel=0xff;
inline std::deque<uint8_t> gpioaAfterDelay;
inline unsigned transfers=0, olatbWrites=0;
inline int i2c_new_master_bus(const i2c_master_bus_config_t* c, i2c_master_bus_handle_t* h) {
    assert(c->sda_io_num==25 && c->scl_io_num==26 && !c->flags.enable_internal_pullup); *h=1; return ESP_OK; }
inline int i2c_master_bus_add_device(int, const i2c_device_config_t* d, i2c_master_dev_handle_t* h) {
    assert(d->device_address==0x20 && d->scl_speed_hz==100000); *h=1; return ESP_OK; }
inline int i2c_master_transmit(int, const uint8_t* bytes, size_t size, int) {
    ++transfers; if(!answers) return ESP_FAIL; assert(size==2); registers[bytes[0]]=bytes[1];
    if(bytes[0]==0x15) ++olatbWrites; return ESP_OK; }
inline int i2c_master_transmit_receive(int, const uint8_t* reg, size_t, uint8_t* out, size_t, int) {
    ++transfers; if(!answers) return ESP_FAIL; *out = *reg==0x12 ? gpioaLevel : registers[*reg]; return ESP_OK; }
""",
    "freertos/FreeRTOS.h": """#pragma once
#include <cstdint>
using BaseType_t=int; using TickType_t=uint32_t;
constexpr int pdFALSE=0, pdTRUE=1, pdPASS=1;
#define pdMS_TO_TICKS(ms) (ms)
#define portYIELD_FROM_ISR(x) ((void)(x))
""",
    "freertos/task.h": """#pragma once
#include "driver/i2c_master.h"
using TaskHandle_t=void*;
inline int taskCore=-1;
inline int xTaskCreatePinnedToCore(void (*)(void*), const char*, int, void*, int, TaskHandle_t* h, int core) {
    taskCore=core; *h=(void*)1; return pdPASS; }
// Each settle delay lets the next queued GPIOA level appear.
inline void vTaskDelay(TickType_t) { if(!gpioaAfterDelay.empty()) { gpioaLevel=gpioaAfterDelay.front(); gpioaAfterDelay.pop_front(); } }
inline uint32_t ulTaskNotifyTake(int, TickType_t) { return 0; }
inline void vTaskNotifyGiveFromISR(TaskHandle_t, BaseType_t*) {}
""",
}

MAIN = r"""#include "panel.cpp"
#include <cstring>
#include <vector>
bool atxOn=false, panelReady=false, linked=false;
int stopAll=0;
namespace atx {
bool is_on() { return atxOn; }
void set_panel(bool present) { panelReady=present; }
}
namespace ble { bool connected() { return linked; } }
namespace laboratory {
void command(const char* text, char* reply, size_t capacity) {
    assert(!strcmp(text,"LAB STOPALL")); ++stopAll; snprintf(reply,capacity,"LAB OK"); }
}
std::vector<std::pair<int,uint32_t>> events;
void receive(uint8_t button, uint32_t sequence) { events.push_back({button,sequence}); }
uint8_t pressing(int button) { return static_cast<uint8_t>(~(1u << (button-1))); }
void reset() { answers=true; gpioaLevel=0xff; gpioaAfterDelay.clear(); memset(registers,0,sizeof(registers));
    available=false; pressed=0; sequence=0; ticks=0; blink=false; written=-1; events.clear(); stopAll=0; panelReady=false; }
int main() {
    panel::set_listener(receive);
    // Absent at startup: no task, no interrupt, ATX ON stays refused.
    answers=false;
    assert(panel::init()==ESP_OK && !panel::present() && !panelReady && taskCore==-1);
    // Present: MCP23017 configured, task on core 0, INT on GPIO27 falling edge.
    reset();
    assert(panel::init()==ESP_OK && panel::present() && panelReady);
    assert(registers[0x0a]==0x44 && registers[0x00]==0x7f && registers[0x0c]==0x7f && registers[0x04]==0x7f);
    assert(registers[0x01]==0xfc && registers[0x0d]==0xfc && registers[0x15]==0);
    assert(taskCore==0 && interruptType==2 && isrHandler);
    // STOP: local STOP ALL, then the FFF2 report; release reports nothing.
    gpioaLevel=pressing(panel::stop);
    service(true);
    assert(stopAll==1 && events.size()==1 && events[0].first==3 && events[0].second==1);
    gpioaLevel=0xff;
    service(true);
    assert(events.size()==1);
    // PLAY, PREV and NEXT are only reported; a spare input reports code 5.
    for (int button : {int(panel::play), int(panel::prev), int(panel::next), 5}) {
        gpioaLevel=pressing(button); service(true); gpioaLevel=0xff; service(true);
    }
    assert(stopAll==1 && events.size()==5 && events[4].first==5 && events[4].second==5);
    // A bounce that settles released is not a press.
    gpioaAfterDelay={0xff,0xff};
    gpioaLevel=pressing(panel::play);
    service(true);
    assert(events.size()==5);
    // A press that appears inside the settle window is still caught.
    gpioaLevel=0xff;
    gpioaAfterDelay={pressing(panel::next),pressing(panel::next)};
    service(true);
    assert(events.size()==6 && events[5].first==4);
    gpioaLevel=0xff; gpioaAfterDelay.clear(); service(true);
    // LEDs: ATX ON follows the request; ESP blinks without BLE, steady with it.
    atxOn=true; ticks=0; blink=false;
    service(false);
    assert((registers[0x15]&1) && !(registers[0x15]&2));
    std::vector<int> esp;
    for (int i=0;i<20;++i) { service(false); esp.push_back(registers[0x15]&2 ? 1 : 0); }
    int toggles=0; for (size_t i=1;i<esp.size();++i) toggles+=esp[i]!=esp[i-1];
    assert(toggles==4); // 2 s at 100 ms ticks: 1 Hz
    linked=true; for (int i=0;i<10;++i) { service(false); assert(registers[0x15]&2); }
    // Without changes only the 0.5 s heartbeat writes.
    const unsigned before=olatbWrites; for (int i=0;i<10;++i) service(false);
    assert(olatbWrites-before==2);
    // Held at startup is not a press.
    reset(); gpioaLevel=pressing(panel::next);
    assert(panel::init()==ESP_OK && panel::present());
    service(true);
    assert(events.empty());
    // Lost while running: the heartbeat write fails, panel I/O stops until
    // restart, ATX permission from startup stays.
    answers=false; ticks=4;
    service(false);
    assert(!panel::present() && panelReady);
    const unsigned after=transfers; service(true); service(false);
    assert(transfers==after);
    puts("panel: detection, STOP ALL, button reports, debounce, LEDs and loss passed");
}
"""


class PanelTest(unittest.TestCase):
    def test_buttons_leds_and_detection(self):
        with tempfile.TemporaryDirectory(prefix="surrklank-panel-") as folder:
            root = Path(folder)
            for name, text in HEADERS.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            (root / "main.cpp").write_text(MAIN)
            binary = root / "test-panel"
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(root), "-I", str(ROOT / "include"), "-I", str(ROOT / "src"),
                            str(root / "main.cpp"), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
