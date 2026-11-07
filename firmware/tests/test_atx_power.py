"""Run the real ATX module against GPIO/FreeRTOS stubs, without hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AtxPowerTest(unittest.TestCase):
    def test_gpio_commands_button_and_maintenance(self):
        with tempfile.TemporaryDirectory(prefix="surrklank-atx-") as folder:
            root = Path(folder)
            (root / "driver").mkdir()
            (root / "freertos").mkdir()
            (root / "esp_err.h").write_text('''#pragma once
#include <cassert>
using esp_err_t = int;
constexpr int ESP_OK=0, ESP_ERR_NO_MEM=1;
#define ESP_ERROR_CHECK(value) assert((value)==ESP_OK)
''')
            (root / "driver/gpio.h").write_text('''#pragma once
#include <cstdint>
using gpio_num_t = int;
constexpr int GPIO_NUM_19=19, GPIO_NUM_13=13;
constexpr int GPIO_MODE_OUTPUT=1, GPIO_MODE_INPUT=2, GPIO_PULLUP_ENABLE=1;
struct gpio_config_t { uint64_t pin_bit_mask; int mode; int pull_up_en; };
inline int outputLevel=-1, buttonLevel=1;
inline int gpio_set_level(int pin, int value) { assert(pin==19); outputLevel=value; return 0; }
inline int gpio_get_level(int pin) { assert(pin==13); return buttonLevel; }
inline int gpio_config(const gpio_config_t*) { return 0; }
''')
            (root / "freertos/FreeRTOS.h").write_text('''#pragma once
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(lock) ((void)(lock))
#define portEXIT_CRITICAL(lock) ((void)(lock))
#define pdMS_TO_TICKS(ms) (ms)
constexpr int pdPASS=1;
''')
            (root / "freertos/task.h").write_text('''#pragma once
#include <vector>
struct EndSamples {};
inline std::vector<int> samples;
inline unsigned nextSample=0;
inline void (*buttonTask)(void*)=nullptr;
inline void vTaskDelay(int) {
    if(nextSample==samples.size()) throw EndSamples{};
    buttonLevel=samples[nextSample++];
}
inline int xTaskCreate(void (*task)(void*), const char*, int, void*, int, void*) {
    buttonTask=task; return pdPASS;
}
''')
            (root / "main.cpp").write_text('''#include "atx_power.cpp"
void press_samples(std::vector<int> values) {
    samples=values; nextSample=0;
    try { buttonTask(nullptr); } catch(const EndSamples&) {}
}
int main() {
    assert(atx::init()==ESP_OK);
    assert(!atx::is_on() && outputLevel==0);
    assert(atx::set(true) && atx::is_on() && outputLevel==1);
    assert(atx::set(true) && outputLevel==1);
    assert(atx::set(false) && !atx::is_on() && outputLevel==0);
    assert(atx::set(false));
    // Bounce does not become a press; a stable press toggles once while held.
    press_samples({0,1,0,1,0,1});
    assert(!atx::is_on());
    press_samples({0,0,0,0,0,0,0,0});
    assert(atx::is_on());
    atx::set(false);
    // Held at startup must be released before it can turn power on.
    buttonLevel=0;
    press_samples({0,0,0,0,0});
    assert(!atx::is_on());
    press_samples({1,1,1,1,0,0,0,0});
    assert(atx::is_on());
    atx::prepare();
    assert(!atx::is_on() && outputLevel==0);
    assert(!atx::set(true) && outputLevel==0);
    assert(atx::set(false));
    buttonLevel=1;
    press_samples({0,0,0,0});
    assert(!atx::is_on() && outputLevel==0);
}
''')
            binary = root / "test-atx"
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(root), "-I", str(ROOT / "include"),
                            "-I", str(ROOT / "src"), str(root / "main.cpp"),
                            "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
