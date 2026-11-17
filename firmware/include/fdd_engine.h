#pragma once
#include <cstdint>

namespace fdd {
constexpr int count = 8;
constexpr unsigned step_low_us = 30;

// FDD module wiring (docs/WIRING.md): each module serves four drives with three
// 595s and one 165. Module 1 is closest to the mainboard.
constexpr int drives_per_module = 4;
constexpr int modules = count / drives_per_module;
constexpr int frame_bits = modules * 24;
constexpr int sensor_bits = modules * 8;
// Outputs of one drive position, in 595 chain order. All are active LOW.
enum class Line : uint8_t { ds0, ds1, ds2, motor, dir, step };
constexpr int lines_per_drive = 6;
// Frame bit 0 is module 1 U2 QA; it is shifted last.
constexpr int output_bit(int drive, Line line) {
    return drive * lines_per_drive + static_cast<int>(line);
}
constexpr uint64_t output_mask(int drive, Line line) {
    return uint64_t{1} << output_bit(drive, line);
}
// Sensor bit k is module k / 8, 165 input D(k % 8); each drive has TRACK0, then WP.
constexpr int track0_bit(int drive) {
    return (drive / drives_per_module) * 8 + (drive % drives_per_module) * 2;
}
// The select input depends on each drive's jumper. DS1 (FDD pin 12) suits
// typical PC drives and matches the hand-wired assembly; DS0 suits Amiga drives.
constexpr Line select_lines[count] = {Line::ds1, Line::ds1, Line::ds1, Line::ds1,
                                      Line::ds1, Line::ds1, Line::ds1, Line::ds1};
uint8_t track0_inputs(uint16_t sensors);
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
    uint32_t pending = 0;
    uint8_t mask = 0;
    int64_t lease = 0;
    bool busy() const;
    bool begin(uint32_t batch, uint8_t devices, int64_t now);
    bool configure(uint32_t batch, int device, uint32_t rate, uint32_t duration);
    bool prepare(uint32_t batch, int64_t now);
    bool commit(uint32_t batch, int64_t now);
    void abort(uint32_t batch, int64_t now);
    void stop(int device, int64_t now);
    void stop_all(int64_t now);
    void power_lost();
    void tick(int64_t now, uint8_t track0);
    void steps_latched(uint64_t before, uint64_t after, int64_t scheduled_at, int64_t latched_at);
    void finish_pulses();
    uint64_t outputs() const;

  private:
    void phase(Drive &drive, Phase next, int64_t now);
    void fail(Drive &drive, Error error, int64_t now);
};
const char *name(Phase phase);
const char *message(Error error);
} // namespace fdd
