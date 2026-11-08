#pragma once
#include "fdd_engine.h"
#include <cstdint>
namespace laboratory {
struct TimedEvent {
    uint32_t sequence = 0, batch = 0;
    int64_t time_us = 0;
    uint8_t device = 0;
    fdd::Phase phase = fdd::Phase::unknown;
    bool toward_zero = true;
};
// Accessed only under the engine mutex. Fixed storage; no I/O in the motion path.
class EventHistory {
public:
    static constexpr unsigned capacity = 128;
    uint32_t latest = 0;
    void observe(int device, const fdd::State &state, int64_t now) {
        auto &old = previous[device - 1];
        if (old.phase == state.phase && old.toward_zero == state.toward_zero && old.batch == state.batch) return;
        old = state;
        ++latest;
        events[(latest - 1) % capacity] = {latest, state.batch, now, (uint8_t)device, state.phase, state.toward_zero};
    }
    const TimedEvent *after(uint32_t cursor) const {
        if (cursor >= latest) return nullptr;
        uint32_t first = latest > capacity ? latest - capacity + 1 : 1;
        uint32_t wanted = cursor + 1 < first ? first : cursor + 1;
        return &events[(wanted - 1) % capacity];
    }
private:
    fdd::State previous[8];
    TimedEvent events[capacity];
};
}
