#pragma once
#include <cstdint>

namespace fdd {
constexpr int count = 12; // three FDD modules
constexpr unsigned step_low_us = 30;

// FDD module wiring (docs/WIRING.md): each module serves four drives with three
// 595s and one 165. Module 1 is closest to the mainboard.
constexpr int drives_per_module = 4;
constexpr int modules = count / drives_per_module;
constexpr int module_bits = 24;
constexpr int frame_bits = modules * module_bits;
constexpr int sensor_bits = modules * 8;
// Bit set of the FDD 595 chain. Three modules need 72 bits, more than one
// uint64_t, so each module keeps its 24 outputs in one word.
struct Frame {
    uint32_t module[modules] = {};
    static constexpr uint32_t word_mask = (uint32_t{1} << module_bits) - 1;
    static constexpr Frame bit(int index) {
        Frame f;
        f.module[index / module_bits] = uint32_t{1} << (index % module_bits);
        return f;
    }
    constexpr bool test(int index) const { return (module[index / module_bits] >> (index % module_bits)) & 1; }
    constexpr Frame operator|(const Frame &o) const {
        Frame f;
        for (int i = 0; i < modules; ++i) f.module[i] = module[i] | o.module[i];
        return f;
    }
    constexpr Frame operator&(const Frame &o) const {
        Frame f;
        for (int i = 0; i < modules; ++i) f.module[i] = module[i] & o.module[i];
        return f;
    }
    constexpr Frame operator~() const {
        Frame f;
        for (int i = 0; i < modules; ++i) f.module[i] = ~module[i] & word_mask;
        return f;
    }
    constexpr Frame &operator|=(const Frame &o) { return *this = *this | o; }
    constexpr Frame &operator&=(const Frame &o) { return *this = *this & o; }
    constexpr bool operator==(const Frame &o) const {
        for (int i = 0; i < modules; ++i) if (module[i] != o.module[i]) return false;
        return true;
    }
    constexpr bool operator!=(const Frame &o) const { return !(*this == o); }
    constexpr explicit operator bool() const {
        for (int i = 0; i < modules; ++i) if (module[i]) return true;
        return false;
    }
};
// Outputs of one drive position, in 595 chain order. All are active LOW.
enum class Line : uint8_t { ds0, ds1, ds2, motor, dir, step };
constexpr int lines_per_drive = 6;
// Frame bit 0 is module 1 U2 QA; it is shifted last.
constexpr int output_bit(int drive, Line line) {
    return drive * lines_per_drive + static_cast<int>(line);
}
constexpr Frame output_mask(int drive, Line line) {
    return Frame::bit(output_bit(drive, line));
}
// Sensor bit k is module k / 8, 165 input D(k % 8); each drive has TRACK0, then WP.
constexpr int track0_bit(int drive) {
    return (drive / drives_per_module) * 8 + (drive % drives_per_module) * 2;
}
// The select input depends on each drive's jumper. DS1 (FDD pin 12) suits
// typical PC drives and is the default; DS0 suits Amiga drives. The line of
// each drive is a runtime setting (Engine::select, stored in NVS).
constexpr Line default_select = Line::ds1;
constexpr bool is_select(Line line) {
    return line == Line::ds0 || line == Line::ds1 || line == Line::ds2;
}
// Bit i = drive i + 1, as in batch masks.
using DriveMask = uint16_t;
DriveMask track0_inputs(uint32_t sensors);
enum class Phase : uint8_t {
    unknown,
    staged,
    homing,
    checking_out,
    checking_return,
    ready,
    playing,
    parking,
    parked,
    error,
    stopped
};
enum class Error : uint8_t {
    none,
    track0_missing,
    track0_stuck,
    return_timeout,
    timing,
    aborted,
    power_lost,
    prepare_timeout
};
struct State {
    Phase phase = Phase::unknown;
    Error error = Error::none;
    uint32_t sequence = 0, batch = 0, rate = 0, duration = 0, elapsed = 0;
    uint16_t steps = 0, return_steps = 0;
    int16_t position = -1;
    bool track0 = false, track_valid = false, left = false, toward_zero = true;
};
struct Drive {
    State state;
    bool configured = false, step_low = false, parking_requested = false;
    unsigned leg = 0, seek = 0, startup_steps = 0;
    int64_t due = 0, raised = 0, started = 0, deadline = 0;
};
class Engine {
  public:
    Drive drives[count];
    // Select line per drive; kept outside Drive, which begin() resets.
    Line select[count] = {default_select, default_select, default_select, default_select,
                          default_select, default_select, default_select, default_select,
                          default_select, default_select, default_select, default_select};
    uint32_t pending = 0;
    DriveMask mask = 0;
    int64_t lease = 0;
    bool busy() const;
    bool begin(uint32_t batch, DriveMask devices, int64_t now);
    bool configure(uint32_t batch, int device, uint32_t rate, uint32_t duration);
    bool prepare(uint32_t batch, int64_t now);
    bool commit(uint32_t batch, int64_t now);
    void abort(uint32_t batch, int64_t now);
    void stop(int device, int64_t now);
    void stop_all(int64_t now);
    // Bus power ended (ATX OFF or PWR_OK lost): active drives fail with
    // power_lost, every position becomes unknown, a pending batch is dropped.
    void power_lost(int64_t now);
    // Accepted only while no drive is active; invalidates that drive's position.
    bool set_select(int device, Line line);
    // Earliest STEP deadline of a moving drive, or INT64_MAX when none is scheduled.
    int64_t next_step() const;
    void tick(int64_t now, DriveMask track0);
    void steps_latched(const Frame &before, const Frame &after, int64_t scheduled_at, int64_t latched_at);
    void finish_pulses();
    Frame outputs() const;

  private:
    void phase(Drive &drive, Phase next, int64_t now);
    void fail(Drive &drive, Error error, int64_t now);
};
const char *name(Phase phase);
const char *message(Error error);
} // namespace fdd
