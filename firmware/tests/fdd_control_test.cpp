#include "fdd_control.cpp"
#include <cassert>
#include <cmath>
#include <vector>

bool atx_on = true, rails_up = true;
namespace atx {
bool is_on() { return atx_on; }
bool rails_ok() { return rails_up; }
bool claim_instruments() { return true; }
void release_instruments() {}
}

// NVS stand-in for drive_settings.cpp.
uint8_t stored_select[fdd::count] = {1, 1, 0, 1, 1, 1, 1, 2};
bool storage_fails = false;
namespace drive_settings {
void load(fdd::Line (&lines)[fdd::count]) {
    for (int i = 0; i < fdd::count; ++i)
        lines[i] = static_cast<fdd::Line>(stored_select[i]);
}
esp_err_t store(const fdd::Line (&lines)[fdd::count]) {
    if (storage_fails)
        return ESP_ERR_NO_MEM;
    for (int i = 0; i < fdd::count; ++i)
        stored_select[i] = static_cast<uint8_t>(lines[i]);
    return ESP_OK;
}
}
fdd::Frame step_mask() {
    fdd::Frame mask;
    for (int i = 0; i < fdd::count; ++i)
        mask |= fdd::output_mask(i, fdd::Line::step);
    return mask;
}
unsigned callbacks = 0;
void slow_ble(int, fdd::State) {
    // A slow notification must run outside motion and never hold STEP LOW.
    assert(!locked);
    assert((latched & step_mask()) == step_mask());
    ++callbacks;
    fake_now += 750;
}
void one_iteration(void (*function)(void*)) {
    wakes = 0;
    try { function(nullptr); } catch (const EndIteration&) {}
}
// Drive 1 plays outward under 100 us alarm wakes with 0-19 us dispatch latency.
// Pending alarms coalesce into an immediate wake; idle alarms long before a
// deadline are skipped. Returns software latch times of falling STEP edges.
std::vector<int64_t> cadence(uint32_t rate, unsigned steps) {
    engine = fdd::Engine{};
    auto &d = engine.drives[0];
    d.state.phase = fdd::Phase::playing;
    d.state.rate = rate;
    d.state.duration = 60000;
    d.state.left = true;
    d.state.toward_zero = false;
    d.startup_steps = 8; // Measure the constant-rate plateau after the startup ramp.
    d.started = fake_now;
    d.due = fake_now + 1234; // Deliberately off the alarm grid.
    previous = engine.outputs();
    write(previous);
    std::vector<int64_t> edges;
    uint32_t random = rate;
    int64_t alarm = fake_now / 100 * 100;
    while (edges.size() < steps) {
        assert(d.state.phase == fdd::Phase::playing && d.state.error == fdd::Error::none);
        random = random * 1103515245u + 12345u;
        const int64_t latency = (random >> 16) % 20;
        int64_t next = alarm + 100;
        if (next <= fake_now) {
            alarm = fake_now / 100 * 100;
        } else {
            if (d.due - next > 300)
                next = (d.due - 200) / 100 * 100;
            alarm = next;
            fake_now = next + latency;
        }
        gpio_events.clear();
        one_iteration(tasks.at("fdd"));
        // Rebuild the shifted FDD frame; a latch with drive 1 STEP LOW is an edge.
        fdd::Frame image;
        const fdd::Frame step = fdd::output_mask(0, fdd::Line::step);
        for (const auto &event : gpio_events) {
            if (event.pin == 23) shift_in(image, event.level);
            if (event.pin == 22 && event.level && !(image & step)) edges.push_back(event.at);
        }
    }
    return edges;
}
int main() {
    assert(laboratory::init() == ESP_OK);
    // Settings stored in NVS reach the engine at init.
    assert(engine.select[2] == fdd::Line::ds0 && engine.select[7] == fdd::Line::ds2 &&
           engine.select[0] == fdd::Line::ds1);
    assert(task_cores.at("fdd") == 1);
    laboratory::set_listener(slow_ble);
    // Init drives the idle bus: /OE and /PL HIGH, everything else LOW.
    assert(levels[21] == 1 && levels[33] == 1);
    for (int pin : {23, 18, 22, 32, 17, 16})
        assert(levels[pin] == 0);
    clear_actuators();
    assert(actuator_latched == 0 && actuator_shifted == 0);
    // H is sampled before the first rising clock edge; module 1 comes first.
    module_inputs[0] = 0xa5;
    module_inputs[1] = 0xfe;
    module_inputs[2] = 0x7f; // module 3 D7: FDD 12 WRITE PROTECT
    // M3 of actuator module 1 and M1 of module 2 report ULT LOW.
    actuator_inputs[0] = 0x0b;
    actuator_inputs[1] = 0x0e;
    const Inputs inputs = read();
    assert(inputs.fdd == 0x80015a);
    assert(actuator_faults(inputs.actuator) == 0x14);
    module_inputs[0] = module_inputs[1] = module_inputs[2] = 255;
    actuator_inputs[0] = actuator_inputs[1] = 0x0f;
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
    assert(latched & fdd::output_mask(0, fdd::Line::step));
    assert(actuator_latched == 0);

    // Two complete 595 frames: one falling and one rising STEP edge.
    unsigned clocks = 0, latches = 0;
    int64_t falling = 0, rising = 0, clock_high = -1, data_at = -1, load_low = -1;
    fdd::Frame image;
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
        if(event.pin == 23) shift_in(image, event.level);
        if(event.pin == 22 && event.level) {
            ++latches;
            if(!(image & fdd::output_mask(0, fdd::Line::step))) falling = event.at;
            else rising = event.at;
        }
    }
    assert(clocks == 2 * fdd::frame_bits && latches == 2);
    assert(falling > 0 && rising - falling >= 30 + 2 * fdd::frame_bits);
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
        assert((latched & step_mask()) == step_mask());
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

    // Bring-up test: only CLK moves, never a LATCH, and never alongside motion.
    engine = fdd::Engine{};
    previous = engine.outputs();
    write(previous);
    one_iteration(tasks.at("fdd"));
    assert(laboratory::actuator_faults() == 0);
    const fdd::Frame fdd_frame = latched;
    const uint64_t actuator_frame = actuator_latched;
    assert(laboratory::set_bus_test(true) && laboratory::bus_test_active());
    char reply[64];
    laboratory::command("LAB BEGIN 9 1", reply, sizeof(reply));
    assert(!strcmp(reply, "ERR LAB BUSY OR INVALID"));
    uint64_t wave = 0;
    for (int step = 0; step < 32; ++step) {
        clock_edges = 0;
        one_iteration(tasks.at("fdd"));
        assert(clock_edges == 1);
        wave = (wave << 1) | levels[23];
        assert(levels[17] == levels[23]);
        fake_now += 125000;
    }
    assert(wave == 0xff00ff00ULL);
    assert(latched == fdd_frame && actuator_latched == actuator_frame);
    clock_edges = 0;
    one_iteration(tasks.at("fdd"));
    // The wave keeps its 125 ms cadence; a fresh iteration in the same period is idle.
    one_iteration(tasks.at("fdd"));
    assert(clock_edges == 1);
    assert(laboratory::set_bus_test(false) && !laboratory::bus_test_active());
    assert(levels[23] == 0 && levels[17] == 0);
    laboratory::command("LAB BEGIN 9 1", reply, sizeof(reply));
    assert(!strcmp(reply, "LAB OK"));
    assert(!laboratory::set_bus_test(true)); // an active batch owns the bus
    laboratory::command("LAB ABORT 9", reply, sizeof(reply));
    engine = fdd::Engine{};
    assert(laboratory::set_bus_test(true));
    // ATX OFF ends the test, idles the bus and makes faults unknown.
    atx_on = false;
    one_iteration(tasks.at("fdd"));
    assert(!laboratory::bus_test_active() && laboratory::actuator_faults() == -1);
    assert(levels[21] == 1 && levels[23] == 0);
    assert(!laboratory::set_bus_test(true));

    // FDD SELECT stores in NVS before it takes effect.
    assert(laboratory::set_select(4, fdd::Line::ds2) == laboratory::SelectResult::ok);
    assert(stored_select[3] == 2 && engine.select[3] == fdd::Line::ds2);
    fdd::Line lines[fdd::count];
    laboratory::select_lines(lines);
    assert(lines[3] == fdd::Line::ds2);
    assert(laboratory::set_select(13, fdd::Line::ds0) == laboratory::SelectResult::invalid);
    assert(laboratory::set_select(1, fdd::Line::motor) == laboratory::SelectResult::invalid);
    storage_fails = true;
    assert(laboratory::set_select(4, fdd::Line::ds0) == laboratory::SelectResult::storage);
    assert(engine.select[3] == fdd::Line::ds2); // unchanged when NVS fails
    storage_fails = false;

    // ATX ON without PWR_OK keeps the idle bus and refuses LAB BEGIN.
    atx_on = true;
    rails_up = false;
    actuator_latched = actuator_shifted = ~0ULL;
    one_iteration(tasks.at("fdd"));
    assert(levels[21] == 1 && actuator_latched == ~0ULL && laboratory::actuator_faults() == -1);
    laboratory::command("LAB BEGIN 10 1", reply, sizeof(reply));
    assert(!strcmp(reply, "ERR LAB BUSY OR INVALID"));
    // PWR_OK HIGH: safe frame latched before /OE goes LOW.
    rails_up = true;
    gpio_events.clear();
    one_iteration(tasks.at("fdd"));
    assert(levels[21] == 0 && actuator_latched == 0);
    int64_t actuator_latch_at = -1, enable_at = -1;
    for (const auto &event : gpio_events) {
        if (event.pin == 16 && event.level && actuator_latch_at < 0) actuator_latch_at = event.at;
        if (event.pin == 21 && !event.level) enable_at = event.at;
    }
    assert(actuator_latch_at >= 0 && enable_at >= actuator_latch_at);
    laboratory::command("LAB BEGIN 10 1", reply, sizeof(reply));
    assert(!strcmp(reply, "LAB OK"));
    assert(laboratory::set_select(1, fdd::Line::ds0) == laboratory::SelectResult::busy);
    // PWR_OK lost while ATX stays ON: idle bus, pending batch failed.
    rails_up = false;
    one_iteration(tasks.at("fdd"));
    assert(levels[21] == 1 && levels[23] == 0 && levels[17] == 0);
    assert(!engine.busy() && !engine.pending);
    assert(engine.drives[0].state.phase == fdd::Phase::error &&
           engine.drives[0].state.error == fdd::Error::power_lost);
    // PWR_OK returns: the actuator branch is cleared again before /OE LOW.
    actuator_latched = actuator_shifted = ~0ULL;
    rails_up = true;
    one_iteration(tasks.at("fdd"));
    assert(levels[21] == 0 && actuator_latched == 0);

    // Twelve drives: 12-bit batch masks, devices 1-12 in LAB commands.
    char wide[512];
    laboratory::command("LAB BEGIN 12 4096", wide, sizeof(wide));
    assert(!strcmp(wide, "ERR LAB BUSY OR INVALID"));
    laboratory::command("LAB BEGIN 12 2048", wide, sizeof(wide)); // FDD 12 only
    assert(!strcmp(wide, "LAB OK") && engine.drives[11].state.phase == fdd::Phase::staged);
    laboratory::command("LAB INFO 12", wide, sizeof(wide));
    assert(!strncmp(wide, "{\"device\":12,", 13));
    laboratory::command("LAB INFO 13", wide, sizeof(wide));
    assert(!strcmp(wide, "ERR LAB BUSY OR INVALID"));
    laboratory::command("LAB ABORT 12", wide, sizeof(wide));

    // Every 1-300 Hz request and every equal-tempered note C1-D4 keeps equal
    // STEP intervals: no alternation between the two neighbouring 100 us values.
    std::vector<uint32_t> rates;
    for (uint32_t hz = 1; hz <= 300; ++hz)
        rates.push_back(hz * 1000);
    for (int note = 24; note <= 62; ++note)
        rates.push_back(uint32_t(std::lround(440000.0 * std::pow(2.0, (note - 69) / 12.0))));
    for (uint32_t rate : rates) {
        const auto edges = cadence(rate, rate < 5000 ? 6 : 40);
        const int64_t period = 1000000000LL / rate;
        for (size_t i = 1; i < edges.size(); ++i)
            assert(edges[i] - edges[i - 1] == period);
    }
}
