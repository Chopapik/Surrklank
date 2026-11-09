"""Run the production motion task with a fake clock, GPIO and FreeRTOS, offline."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FddControlTest(unittest.TestCase):
    def test_bus_pulse_and_slow_telemetry(self):
        with tempfile.TemporaryDirectory(prefix="surrklank-fdd-control-") as directory:
            root = Path(directory)
            headers = {
                "esp_err.h": """#pragma once
#include <cassert>
using esp_err_t = int;
constexpr int ESP_OK=0, ESP_ERR_NO_MEM=1;
#define ESP_ERROR_CHECK(value) assert((value)==ESP_OK)
""",
                "esp_timer.h": """#pragma once
#include <cstdint>
inline int64_t fake_now=300000;
inline int64_t esp_timer_get_time() { return fake_now; }
struct esp_timer_create_args_t { void (*callback)(void*); const char* name; };
using esp_timer_handle_t = int;
inline int esp_timer_create(const esp_timer_create_args_t*, esp_timer_handle_t*) { return 0; }
inline int esp_timer_start_periodic(esp_timer_handle_t, int) { return 0; }
""",
                "esp_rom_sys.h": """#pragma once
#include "esp_timer.h"
inline void esp_rom_delay_us(unsigned us) { fake_now+=us; }
""",
                "esp_random.h": "#pragma once\ninline unsigned esp_random() { return 123; }\n",
                "freertos/FreeRTOS.h": """#pragma once
using BaseType_t=int;
constexpr int pdFALSE=0, pdTRUE=1, pdPASS=1, portMAX_DELAY=-1;
""",
                "freertos/task.h": """#pragma once
#include <string>
#include <map>
using TaskHandle_t = void*;
inline std::map<std::string, void (*)(void*)> tasks;
inline std::map<std::string, int> task_cores;
inline unsigned wakes=0;
struct EndIteration {};
inline int ulTaskNotifyTake(int,int) { if(wakes++) throw EndIteration{}; return 1; }
inline void xTaskNotifyGive(TaskHandle_t) {}
inline TaskHandle_t xTaskGetCurrentTaskHandle() { return reinterpret_cast<void*>(1); }
inline void vTaskNotifyGiveFromISR(TaskHandle_t, BaseType_t* wake) { *wake=pdTRUE; }
inline int xTaskCreate(void (*f)(void*), const char* name, int, void*, int, TaskHandle_t* handle) {
    tasks[name]=f; *handle=reinterpret_cast<void*>(tasks.size()); return pdPASS;
}
inline int xTaskCreatePinnedToCore(void (*f)(void*), const char* name, int stack, void* arg, int priority,
                                 TaskHandle_t* handle, int core) {
    task_cores[name]=core;
    return xTaskCreate(f,name,stack,arg,priority,handle);
}
inline void vTaskDelete(TaskHandle_t) {}
""",
                "freertos/semphr.h": """#pragma once
using SemaphoreHandle_t = int;
inline bool locked=false;
inline int xSemaphoreCreateMutex() { return 1; }
inline void xSemaphoreTake(int,int) { assert(!locked); locked=true; }
inline void xSemaphoreGive(int) { assert(locked); locked=false; }
""",
                "driver/gptimer.h": """#pragma once
using gptimer_handle_t=int;
struct gptimer_alarm_event_data_t {};
constexpr int GPTIMER_CLK_SRC_DEFAULT=0, GPTIMER_COUNT_UP=0;
struct gptimer_config_t { int clk_src, direction, resolution_hz; };
struct gptimer_event_callbacks_t { bool (*on_alarm)(gptimer_handle_t,const gptimer_alarm_event_data_t*,void*); };
struct gptimer_alarm_config_t { unsigned alarm_count=0; struct { bool auto_reload_on_alarm=false; } flags; };
inline int gptimer_new_timer(const gptimer_config_t* c,gptimer_handle_t* h) { assert(c->resolution_hz==1000000); *h=1; return 0; }
inline int gptimer_register_event_callbacks(int,const gptimer_event_callbacks_t* c,void* ctx) { assert(c->on_alarm(1,nullptr,ctx)); return 0; }
inline int gptimer_set_alarm_action(int,const gptimer_alarm_config_t* a) { assert(a->alarm_count==100 && a->flags.auto_reload_on_alarm); return 0; }
inline int gptimer_enable(int) { return 0; }
inline int gptimer_start(int) { return 0; }
""",
                "driver/gpio.h": """#pragma once
#include "esp_timer.h"
#include <vector>
using gpio_num_t = int;
constexpr int GPIO_NUM_23=23, GPIO_NUM_18=18, GPIO_NUM_22=22, GPIO_NUM_21=21,
    GPIO_NUM_17=17, GPIO_NUM_16=16, GPIO_NUM_33=33, GPIO_NUM_32=32, GPIO_NUM_34=34;
constexpr int GPIO_MODE_INPUT=1, GPIO_MODE_OUTPUT=2;
struct gpio_config_t { uint64_t pin_bit_mask; int mode; };
struct GpioEvent { int pin, level; int64_t at; };
inline std::vector<GpioEvent> gpio_events;
inline int levels[40]={};
inline uint32_t shifted=0, latched=0;
inline uint8_t input_image=255;
inline int input_bit=7;
inline int gpio_set_level(int pin, int value) {
    gpio_events.push_back({pin,value,fake_now});
    if(pin==18 && value && !levels[pin]) shifted=(shifted<<1)|levels[23];
    if(pin==22 && value && !levels[pin]) latched=shifted;
    if(pin==33 && value) input_bit=7;
    if(pin==32 && value && !levels[pin] && input_bit>0) --input_bit;
    levels[pin]=value; return 0;
}
inline int gpio_get_level(int) { return (input_image >> input_bit)&1; }
inline int gpio_config(const gpio_config_t*) { return 0; }
inline int gpio_set_direction(int,int) { return 0; }
""",
            }
            for name, text in headers.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            binary = root / "fdd-control-test"
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(root), "-I", str(ROOT / "include"), "-I", str(ROOT / "src"),
                            str(ROOT / "tests/fdd_control_test.cpp"), str(ROOT / "src/fdd_engine.cpp"),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
