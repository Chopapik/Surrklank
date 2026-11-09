#include "laboratory_timing.h"
#include "fdd_engine.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

struct Simulation {
    fdd::Engine engine;
    int position[8] = {};
    bool absent[8] = {}, stuck[8] = {};
    int skip_forward = 0, skip_return = 0;
    int64_t now = 0;
    unsigned played[8] = {};
    void tick() {
        uint8_t sensors = 0;
        for (int i = 0; i < 8; ++i)
            if (!absent[i] && (stuck[i] || position[i] <= 0))
                sensors |= 1 << i;
        auto before = engine.outputs();
        engine.tick(now, sensors);
        auto after = engine.outputs();
        for (int i = 0; i < 8; ++i) {
            int bit = (i / 2) * 8 + (i % 2 ? 1 : 4);
            if (!(before & (1UL << bit)) && (after & (1UL << bit))) {
                bool back = after & (1UL << (bit + 1));
                auto &state = engine.drives[i].state;
                if (state.phase == fdd::Phase::playing) {
                    ++played[i];
                    if (!back && skip_forward > 0 && position[i] > 0) {
                        --skip_forward;
                        continue;
                    }
                    if (back && skip_return > 0) {
                        --skip_return;
                        continue;
                    }
                }
                position[i] += back ? -1 : 1;
                if (position[i] < 0)
                    position[i] = 0;
            }
        }
        now += 100;
    }
    void run(int64_t us) {
        auto end = now + us;
        while (now < end)
            tick();
    }
    bool ready(uint8_t mask) {
        for (int i = 0; i < 8; ++i)
            if ((mask & (1 << i)) && engine.drives[i].state.phase != fdd::Phase::ready)
                return false;
        return true;
    }
    void prepare(uint32_t batch, uint8_t mask) {
        assert(engine.begin(batch, mask, now));
        for (int i = 0; i < 8; ++i)
            if (mask & (1 << i))
                assert(engine.configure(batch, i + 1, 100000, 3000));
        assert(engine.prepare(batch, now));
        for (int i = 0; i < 30000 && !ready(mask); ++i)
            tick();
    }
};
int main() {
    // High-rate profiles complete repeated sensor-confirmed traverses and still
    // fault at the existing return limit when TRACK0 disappears during playing.
    for (uint32_t rate : {200000u, 300000u}) {
        Simulation sim;
        sim.prepare(1, 1);
        auto &state = sim.engine.drives[0].state;
        state.rate = rate;
        state.duration = 8000;
        assert(sim.engine.commit(1, sim.now));
        sim.run(8100000);
        assert(state.phase == fdd::Phase::stopped && state.error == fdd::Error::none);
        assert(sim.played[0] > 1000 && sim.played[0] < rate / 1000 * 8);
        assert(sim.position[0] >= 0 && sim.position[0] <= 70);

        sim.prepare(2, 1);
        auto &again = sim.engine.drives[0].state;
        again.rate = rate;
        assert(sim.engine.commit(2, sim.now));
        sim.run(50000);
        sim.absent[0] = true;
        sim.run(2000000);
        assert(again.phase == fdd::Phase::error && again.error == fdd::Error::return_timeout);
        assert(again.return_steps == 120);
    }
    // High-rate playback starts gradually and then keeps the requested cadence.
    for (uint32_t rate : {100000u, 120000u, 199999u, 200000u, 300000u}) {
        fdd::Engine engine;
        auto &d = engine.drives[0];
        d.state.phase = fdd::Phase::playing;
        d.state.rate = rate;
        d.state.duration = 3000;
        d.state.left = true;
        d.state.toward_zero = false;
        d.due = 10000;
        int64_t previous_period = 10000;
        for (int step = 0; step < 16; ++step) {
            const int64_t now = d.due;
            engine.tick(now, 0);
            assert(d.step_low);
            const int64_t period = d.due - now;
            if (rate < 200000 || step >= 8)
                assert(period == 1000000000LL / rate);
            else {
                assert(period <= previous_period && period >= 1000000000LL / rate);
                if (step == 0) assert(period == 10000);
            }
            previous_period = period;
            engine.finish_pulses();
        }
        // A reversal retains the plateau; it must not restart the tone ramp.
        d.state.toward_zero = true;
        engine.tick(d.due, 1);
        assert(!d.state.toward_zero);
        auto now = d.due;
        engine.tick(now, 0);
        assert(d.step_low && d.due - now == 1000000000LL / rate);
    }
    // The outward limit retains the plateau, then allows a longer reversal pause.
    {
        fdd::Engine engine;
        auto &d = engine.drives[0];
        d.state.phase = fdd::Phase::playing;
        d.state.rate = 300000;
        d.state.duration = 3000;
        d.state.left = true;
        d.state.toward_zero = false;
        d.state.position = 62;
        d.leg = d.seek = 62;
        d.startup_steps = 8;
        d.due = 10000;

        for (int i = 0; i < 8; ++i) {
            const auto now = d.due;
            engine.tick(now, 0);
            assert(d.step_low && !d.state.toward_zero);
            const auto period = d.due - now;
            assert(period == 1000000000LL / 300000);
            engine.finish_pulses();
        }
        const auto limit = d.due;
        engine.tick(limit, 0);
        assert(!d.step_low && d.state.toward_zero && d.leg == 70);
        assert(d.due >= limit + 15000);
    }
    // Register latency extends the LOW hold but must not move the cadence grid.
    {
        fdd::Engine engine;
        auto &drive = engine.drives[0];
        drive.state.phase = fdd::Phase::playing;
        drive.state.rate = 100000;
        drive.state.duration = 1000;
        drive.state.left = true;
        drive.state.toward_zero = false;
        auto before = engine.outputs();
        drive.due = 10000;
        engine.tick(10000, 0);
        auto after = engine.outputs();
        engine.steps_latched(before, after, 10000, 10350);
        assert(drive.raised == 10350 + fdd::step_low_us);
        assert(drive.due == 20000);
        engine.tick(10350 + fdd::step_low_us - 1, 0);
        assert(drive.step_low);
        engine.tick(10350 + fdd::step_low_us, 0);
        assert(!drive.step_low);
        engine.tick(19999, 0);
        assert(!drive.step_low);
        engine.tick(20000, 0);
        assert(drive.step_low);
    }
    // Varying task and register delays do not accumulate over a 100 Hz run.
    {
        fdd::Engine engine;
        auto &d = engine.drives[0];
        d.state.phase = fdd::Phase::playing;
        d.state.rate = 100000;
        d.state.duration = 1000;
        d.state.left = true;
        d.state.toward_zero = false;
        d.due = 10000;
        for (int i = 0; i < 50; ++i) {
            int64_t now = 10000 + i * 10000 + (i % 3) * 100;
            auto before = engine.outputs();
            engine.tick(now, 0);
            assert(d.step_low);
            engine.steps_latched(before, engine.outputs(), now, now + 70);
            assert(d.due == 10000 + (i + 1) * 10000);
            engine.finish_pulses();
        }
        // A late dispatch must not trigger a burst immediately afterwards.
        engine.tick(d.due + 7500, 0);
        const auto next = d.due;
        engine.finish_pulses();
        engine.tick(next - 1, 0);
        assert(!d.step_low);
        engine.tick(next, 0);
        assert(d.step_low);
    }
    {
        laboratory::EventHistory history;
        fdd::State state;
        history.observe(1, state, 1);
        assert(history.latest == 0);
        state.phase = fdd::Phase::playing; state.batch = 7;
        history.observe(1, state, 100);
        history.observe(1, state, 101);
        assert(history.latest == 1 && history.after(0)->time_us == 100);
        for (unsigned i = 0; i < 140; ++i) {
            state.toward_zero = !state.toward_zero;
            history.observe(1, state, 200 + i);
        }
        assert(history.after(0)->sequence == history.latest - 127);
        assert(history.after(history.latest) == nullptr);
    }

    // SELECT is active LOW at the documented QG/QD outputs, independently of STEP/DIR.
    {
        Simulation s;
        constexpr uint32_t select_mask = 0x48484848;
        assert((s.engine.outputs() & select_mask) == select_mask);
        s.prepare(1, 255);
        assert(s.ready(255));
        assert((s.engine.outputs() & select_mask) == 0);
        assert(s.engine.commit(1, s.now));
        s.engine.stop_all(s.now);
        s.run(100000);
        assert((s.engine.outputs() & select_mask) == select_mask);
    }
    // Preparation must confirm sensor transitions, not merely trust a LOW input.
    {
        Simulation s;
        s.stuck[1] = true;
        s.prepare(1, 3);
        assert(!s.engine.commit(1, s.now));
        assert(s.played[0] == 0 && s.played[1] == 0);
        assert(s.engine.drives[1].state.error == fdd::Error::track0_stuck);
    }
    {
        Simulation s;
        s.absent[1] = true;
        s.prepare(1, 3);
        assert(!s.engine.commit(1, s.now));
        assert(s.engine.drives[1].state.error == fdd::Error::track0_missing);
        assert(s.played[0] == 0);
    }
    // Unknown initial positions may be beyond the playing leg's 70 pulses.
    {
        Simulation s;
        s.position[0] = 79;
        s.prepare(1, 1);
        assert(s.ready(1));
        assert(s.position[0] == 0);
    }
    // Fewer real forward movements -> return completes before 70 commands.
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.ready(1));
        assert(s.engine.commit(1, s.now));
        s.skip_forward = 7;
        s.run(1450000);
        assert(s.engine.drives[0].state.return_steps == 63);
        assert(!s.engine.drives[0].state.toward_zero);
    }
    // Missed return movements -> the sensor, not a count of 70, ends the return.
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.engine.commit(1, s.now));
        s.skip_return = 5;
        s.run(1510000);
        assert(s.engine.drives[0].state.return_steps == 75);
        assert(!s.engine.drives[0].state.toward_zero);
    }
    // A second batch can start without stopping the first.
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.engine.commit(1, s.now));
        s.prepare(2, 2);
        assert(s.ready(2));
        assert(s.engine.commit(2, s.now));
        s.run(200000);
        assert(s.played[0] > 0 && s.played[1] > 0);
        s.engine.stop(1, s.now);
        s.run(400000);
        assert(s.engine.drives[0].state.phase == fdd::Phase::parked);
        assert(s.engine.drives[1].state.phase == fdd::Phase::playing);
        s.engine.stop_all(s.now);
        s.run(1500000);
        assert(!s.engine.busy());
    }
    // Stopping preparation cancels COMMIT and repeated STOP does not restart parking.
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.engine.commit(1, s.now));
        while (!s.engine.drives[0].step_low)
            s.tick();
        s.engine.stop(1, s.now);
        assert(!s.engine.drives[0].state.toward_zero);
        while (s.engine.drives[0].step_low) {
            assert(!s.engine.drives[0].state.toward_zero);
            s.tick();
        }
        s.tick();
        assert(s.engine.drives[0].state.toward_zero);
        s.run(100000);
        assert(!s.engine.busy());
    }
    {
        Simulation s;
        assert(s.engine.begin(1, 1, s.now));
        assert(s.engine.configure(1, 1, 100000, 3000));
        assert(s.engine.prepare(1, s.now));
        s.engine.stop_all(s.now);
        assert(!s.engine.commit(1, s.now));
        s.run(100000);
        assert(!s.engine.busy());
    }
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.engine.commit(1, s.now));
        s.run(800000);
        s.absent[0] = true;
        s.run(1300000);
        assert(s.engine.drives[0].state.phase == fdd::Phase::error);
        assert(s.engine.drives[0].state.position == -1);
    }
    // New preparation failures must not affect older active batches.
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.engine.commit(1, s.now));
        s.absent[1] = true;
        s.prepare(2, 2);
        assert(s.engine.drives[0].state.phase == fdd::Phase::playing);
    }
    {
        Simulation s;
        s.prepare(1, 1);
        assert(s.engine.commit(1, s.now));
        s.run(3500000);
        assert(s.engine.drives[0].state.phase == fdd::Phase::stopped);
        assert(!s.engine.busy());
        int position = s.position[0];
        auto steps = s.engine.drives[0].state.steps;
        assert(position > 0);
        s.run(1000000);
        assert(s.position[0] == position && s.engine.drives[0].state.steps == steps);
        s.prepare(2, 1);
        assert(s.ready(1) && s.position[0] == 0);
        assert(s.engine.commit(2, s.now));
    }
    puts("FDD engine: sensor faults, atomic preparation, 63/75-step returns, concurrent batches, stop, duration and "
         "bounded faults passed");
}
