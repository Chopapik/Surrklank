#include "fdd_control.cpp"
#include <cassert>

namespace atx {
bool is_on() { return true; }
bool claim_instruments() { return true; }
void release_instruments() {}
}

unsigned callbacks = 0;
void slow_ble(int, fdd::State) {
    // A slow notification must run outside motion and never hold STEP LOW.
    assert(!locked);
    assert((latched & 0x12121212) == 0x12121212);
    ++callbacks;
    fake_now += 750;
}
void one_iteration(void (*function)(void*)) {
    wakes = 0;
    try { function(nullptr); } catch (const EndIteration&) {}
}
int main() {
    assert(laboratory::init() == ESP_OK);
    laboratory::set_listener(slow_ble);
    setup();
    input_image = 0xa5;
    assert(read() == 0x5a); // H is sampled before the first rising clock edge.
    input_image = 255;
    previous = engine.outputs();
    write(previous);
    powered = true;
    auto &drive = engine.drives[0];
    drive.state.phase = fdd::Phase::playing;
    drive.state.rate = 100000;
    drive.state.duration = 1000;
    drive.state.left = true;
    drive.state.toward_zero = false;
    drive.started = fake_now;
    drive.due = fake_now;
    gpio_events.clear();
    one_iteration(tasks.at("fdd"));
    assert(callbacks == 0); // BLE cannot delay completion of this step.
    assert(!drive.step_low);
    assert(latched & (1UL << 4));

    // Two complete 595 frames: one falling and one rising STEP edge.
    unsigned clocks = 0, latches = 0;
    int64_t falling = 0, rising = 0, clock_high = -1, data_at = -1, load_low = -1;
    uint32_t image = 0;
    for (const auto &event : gpio_events) {
        if(event.pin == 23) data_at = event.at;
        if(event.pin == 18 && event.level) {
            assert(event.at - data_at >= 1);
            clock_high = event.at;
            ++clocks;
        }
        if(event.pin == 18 && !event.level && clock_high >= 0)
            assert(event.at - clock_high >= 1);
        if(event.pin == 33 && !event.level) load_low = event.at;
        if(event.pin == 33 && event.level && load_low >= 0)
            assert(event.at - load_low >= 1);
        // Reconstruct FDD data at the latch from the logged bit stream below.
        if(event.pin == 23) image = (image << 1) | event.level;
        if(event.pin == 22 && event.level) {
            ++latches;
            if(!(image & (1UL << 4))) falling = event.at;
            else rising = event.at;
        }
    }
    assert(clocks == 64 && latches == 2);
    assert(falling > 0 && rising - falling >= 30 + 64);
    const auto next_step = drive.due;
    // No GPIO may change while the simulated BLE callback stalls.
    const auto edges = gpio_events.size();
    one_iteration(tasks.at("fdd_reports"));
    assert(callbacks > 0 && gpio_events.size() == edges);
    assert(drive.due == next_step);

    // The same pulse completion rule applies to all eight drives at these rates.
    const unsigned before = callbacks;
    for (unsigned rate : {10000u, 100000u, 110000u, 300000u}) {
        engine = fdd::Engine{};
        for (auto &d : engine.drives) {
            d.state.phase = fdd::Phase::playing;
            d.state.rate = rate;
            d.state.duration = 1000;
            d.state.left = true;
            d.state.toward_zero = false;
            d.started = fake_now;
            d.due = fake_now;
        }
        previous = engine.outputs();
        write(previous);
        // All eight STEP bits fall together and must rise before any report.
        one_iteration(tasks.at("fdd"));
        assert((latched & 0x12121212) == 0x12121212);
        for (const auto &d : engine.drives) {
            assert(d.state.steps == 1 && !d.step_low);
            assert(d.due > fake_now);
        }
        // Publishing is independently scheduled; a second pass cannot emit a burst.
        one_iteration(tasks.at("fdd"));
        for (const auto &d : engine.drives)
            assert(d.state.steps == 1);
    }
    assert(callbacks == before);
}
