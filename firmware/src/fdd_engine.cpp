#include "fdd_engine.h"

namespace {
bool active(fdd::Phase p) {
    return p != fdd::Phase::unknown && p != fdd::Phase::parked && p != fdd::Phase::error && p != fdd::Phase::stopped;
}
bool moving(fdd::Phase p) {
    return p == fdd::Phase::homing || p == fdd::Phase::checking_out || p == fdd::Phase::checking_return ||
           p == fdd::Phase::playing || p == fdd::Phase::parking;
}
constexpr int64_t seek_period = 10000, direction_guard = 5000;
constexpr unsigned seek_limit = 120;
constexpr uint32_t startup_threshold = 200000, startup_rate = 100000;
constexpr unsigned startup_length = 8;
} // namespace
bool fdd::Engine::busy() const {
    for (const auto &d : drives)
        if (active(d.state.phase))
            return true;
    return false;
}
void fdd::Engine::phase(Drive &d, Phase next, int64_t now) {
    d.state.phase = next;
    if (next == Phase::parking || next == Phase::homing || next == Phase::checking_return)
        d.state.return_steps = 0;
    d.step_low = false;
    d.seek = 0;
    d.due = now + (d.state.phase == Phase::playing && d.state.rate >= startup_threshold ? 15000 : direction_guard);
    d.deadline = now + 2000000;
    ++d.state.sequence;
}
void fdd::Engine::fail(Drive &d, Error error, int64_t now) {
    phase(d, Phase::error, now);
    d.state.error = error;
    d.state.position = -1;
}
bool fdd::Engine::begin(uint32_t batch, uint8_t devices, int64_t now) {
    if (!batch || !devices || pending)
        return false;
    for (int i = 0; i < count; ++i)
        if ((devices & (1 << i)) && active(drives[i].state.phase))
            return false;
    for (const auto &d : drives)
        if (d.state.batch == batch && active(d.state.phase))
            return false;
    pending = batch;
    mask = devices;
    lease = now + 30000000;
    for (int i = 0; i < count; ++i)
        if (devices & (1 << i)) {
            auto &d = drives[i];
            uint32_t sequence = d.state.sequence;
            d = Drive{};
            d.state.sequence = sequence;
            d.state.batch = batch;
            phase(d, Phase::staged, now);
        }
    return true;
}
bool fdd::Engine::configure(uint32_t batch, int device, uint32_t rate, uint32_t duration) {
    if (batch != pending || device < 1 || device > count || !(mask & (1 << (device - 1))) || rate < 1000 ||
        rate > 300000 || !duration || duration > 60000)
        return false;
    auto &d = drives[device - 1];
    if (d.state.phase != Phase::staged || d.configured)
        return false;
    d.state.rate = rate;
    d.state.duration = duration;
    d.configured = true;
    ++d.state.sequence;
    return true;
}
bool fdd::Engine::prepare(uint32_t batch, int64_t now) {
    if (batch != pending)
        return false;
    for (int i = 0; i < count; ++i)
        if ((mask & (1 << i)) && (!drives[i].configured || drives[i].state.phase != Phase::staged))
            return false;
    for (int i = 0; i < count; ++i)
        if (mask & (1 << i)) {
            auto &d = drives[i];
            d.state.toward_zero = true;
            phase(d, Phase::homing, now);
        }
    return true;
}
bool fdd::Engine::commit(uint32_t batch, int64_t now) {
    if (batch != pending)
        return false;
    for (int i = 0; i < count; ++i)
        if ((mask & (1 << i)) && drives[i].state.phase != Phase::ready)
            return false;
    for (int i = 0; i < count; ++i)
        if (mask & (1 << i)) {
            auto &d = drives[i];
            d.started = now;
            d.startup_steps = 0;
            d.leg = 0;
            d.state.toward_zero = false;
            d.state.left = false;
            phase(d, Phase::playing, now);
        }
    pending = 0;
    mask = 0;
    return true;
}
void fdd::Engine::abort(uint32_t batch, int64_t now) {
    (void)now;
    if (!batch || pending != batch)
        return;
    pending = 0;
    mask = 0;
    for (auto &d : drives)
        if (d.state.batch == batch && active(d.state.phase)) {
            d.state.error = Error::aborted;
            d.parking_requested = true;
        }
}
void fdd::Engine::stop(int device, int64_t now) {
    if (device < 1 || device > count)
        return;
    auto &d = drives[device - 1];
    if (pending && d.state.batch == pending) {
        abort(pending, now);
        return;
    }
    if (d.state.phase == Phase::parking || !active(d.state.phase))
        return;
    d.parking_requested = true;
}
void fdd::Engine::stop_all(int64_t now) {
    pending = 0;
    mask = 0;
    for (int i = 1; i <= count; ++i)
        stop(i, now);
}
void fdd::Engine::power_lost() {
    pending = 0;
    mask = 0;
    for (auto &d : drives) {
        d.step_low = false;
        d.state.phase = Phase::unknown;
        d.state.position = -1;
        d.state.track_valid = false;
        d.state.error = Error::power_lost;
        ++d.state.sequence;
    }
}
void fdd::Engine::tick(int64_t now, uint8_t track0) {
    if (pending && now > lease) {
        for (auto &d : drives)
            if (d.state.batch == pending && active(d.state.phase))
                fail(d, Error::prepare_timeout, now);
        pending = 0;
        mask = 0;
    }
    for (int i = 0; i < count; ++i) {
        auto &d = drives[i];
        auto &s = d.state;
        if (!active(s.phase))
            continue;
        s.track_valid = true;
        s.track0 = track0 & (1 << i);
        if (s.phase == Phase::playing) {
            s.elapsed = static_cast<uint32_t>((now - d.started) / 1000);
        }
        if (d.step_low) {
            if (now >= d.raised)
                d.step_low = false;
            continue;
        }
        // Finish the current pulse, then leave the head in place until the next preparation.
        if (s.phase == Phase::playing && s.elapsed >= s.duration && !d.parking_requested) {
            phase(d, Phase::stopped, now);
            continue;
        }
        if (d.parking_requested) {
            d.parking_requested = false;
            s.toward_zero = true;
            phase(d, Phase::parking, now);
        }
        if (!moving(s.phase) || now < d.due)
            continue;
        if (s.phase == Phase::homing && s.track0) {
            s.position = 0;
            s.toward_zero = false;
            phase(d, Phase::checking_out, now);
            continue;
        }
        if (s.phase == Phase::checking_out && !s.track0) {
            s.left = true;
            s.toward_zero = true;
            phase(d, Phase::checking_return, now);
            continue;
        }
        if ((s.phase == Phase::checking_return || s.phase == Phase::parking) && s.track0) {
            s.position = 0;
            phase(d, s.phase == Phase::parking ? Phase::parked : Phase::ready, now);
            continue;
        }
        if (s.phase == Phase::playing && s.toward_zero && s.track0) {
            s.position = 0;
            d.leg = 0;
            s.left = false;
            s.toward_zero = false;
            phase(d, Phase::playing, now);
            continue;
        }
        if ((s.phase != Phase::playing && now > d.deadline) || d.seek >= seek_limit) {
            fail(d, s.phase == Phase::homing ? Error::track0_missing : Error::return_timeout, now);
            continue;
        }
        if ((s.phase == Phase::checking_out && d.seek >= 4) ||
            (s.phase == Phase::playing && !s.toward_zero && d.leg >= 4 && !s.left)) {
            fail(d, Error::track0_stuck, now);
            continue;
        }
        if (s.phase == Phase::playing && !s.toward_zero && d.leg >= 70) {
            s.toward_zero = true;
            s.return_steps = 0;
            d.seek = 0;
            d.due = now + (d.state.phase == Phase::playing && d.state.rate >= startup_threshold ? 15000 : direction_guard);
            ++s.sequence;
            continue;
        }
        uint32_t rate = s.rate;
        if (s.phase == Phase::playing && rate >= startup_threshold) {
            // Ramp only once per tone, retaining constant rate across later traverses.
            unsigned progress = d.startup_steps < startup_length ? d.startup_steps : startup_length;
            rate = startup_rate + (rate - startup_rate) * progress / startup_length;
        }
        int64_t period = s.phase == Phase::playing ? 1000000000LL / rate : seek_period;
        // Late work must not emit a burst of catch-up steps.
        if (s.phase == Phase::playing && now - d.due > period * 2) {
            fail(d, Error::timing, now);
            continue;
        }
        d.step_low = true;
        d.raised = now + step_low_us;
        // Keep the cadence on its deadline grid; small dispatch delays must not accumulate.
        // A substantial overrun starts a fresh period rather than a catch-up pulse.
        d.due = now - d.due > period / 2 ? now + period : d.due + period;
        ++s.steps;
        if (s.phase == Phase::playing && d.startup_steps < startup_length)
            ++d.startup_steps;
        ++d.seek;
        if (s.toward_zero)
            ++s.return_steps;
        if (s.position >= 0) {
            if (s.toward_zero)
                --s.position;
            else
                ++s.position;
        }
        if (s.phase == Phase::playing && !s.toward_zero) {
            if (!s.track0)
                s.left = true;
            ++d.leg;
        }
    }
    // A failed preparation invalidates the whole pending batch; unrelated playing drives continue.
    if (pending) {
        bool failed = false;
        for (const auto &d : drives)
            if (d.state.batch == pending && d.state.phase == Phase::error)
                failed = true;
        if (failed) {
            for (auto &d : drives)
                if (d.state.batch == pending && active(d.state.phase)) {
                    d.state.error = Error::aborted;
                    d.parking_requested = true;
                }
            pending = 0;
            mask = 0;
        }
    }
}
void fdd::Engine::steps_latched(uint32_t before, uint32_t after, int64_t scheduled_at, int64_t latched_at) {
    const int64_t delay = latched_at - scheduled_at;
    for (int i = 0; i < count; ++i) {
        const int bit = (i / 2) * 8 + (i % 2 ? 1 : 4);
        const uint32_t step = 1UL << bit;
        if ((before & step) && !(after & step)) {
            drives[i].raised += delay;
        }
    }
}
void fdd::Engine::finish_pulses() {
    for (auto &drive : drives)
        drive.step_low = false;
}
uint32_t fdd::Engine::outputs() const {
    uint32_t image = 0;
    for (int i = 0; i < count; ++i) {
        int base = (i / 2) * 8 + (i % 2 ? 1 : 4);
        const auto &d = drives[i];
        if (!d.step_low)
            image |= 1UL << base;
        if (d.state.toward_zero)
            image |= 1UL << (base + 1);
        if (!active(d.state.phase))
            image |= 1UL << (base + 2);
    }
    return image;
}
const char *fdd::name(Phase p) {
    switch (p) {
    case Phase::staged:
        return "staged";
    case Phase::homing:
        return "homing";
    case Phase::checking_out:
        return "checking_out";
    case Phase::checking_return:
        return "checking_return";
    case Phase::ready:
        return "ready";
    case Phase::playing:
        return "playing";
    case Phase::parking:
        return "parking";
    case Phase::parked:
        return "parked";
    case Phase::error:
        return "error";
    case Phase::stopped:
        return "stopped";
    default:
        return "unknown";
    }
}
const char *fdd::message(Error e) {
    switch (e) {
    case Error::none:
        return "";
    case Error::track0_missing:
        return "TRACK0 not confirmed; check drive, power and wiring";
    case Error::track0_stuck:
        return "TRACK0 did not release";
    case Error::return_timeout:
        return "TRACK0 return limit exceeded";
    case Error::timing:
        return "Step scheduling deadline missed";
    case Error::aborted:
        return "Batch aborted";
    case Error::power_lost:
        return "Power request off; position unknown";
    default:
        return "Preparation lease expired";
    }
}
