#pragma once
#include <cstdint>

namespace fdd {
constexpr int count = 8;
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
    unsigned leg = 0, seek = 0;
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
    uint32_t outputs() const;

  private:
    void phase(Drive &drive, Phase next, int64_t now);
    void fail(Drive &drive, Error error, int64_t now);
};
const char *name(Phase phase);
const char *message(Error error);
} // namespace fdd
