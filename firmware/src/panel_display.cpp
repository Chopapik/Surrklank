#include "panel_display.h"
#include "esp_lcd_io_i2c.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_ssd1306.h"
#include "panel_font.h"
#include "panel_logo.h"
#include <cstdio>
#include <cstring>

namespace {
constexpr int width = 128, height = 64, pages = height / 8;
constexpr uint16_t display_address = 0x3c;
constexpr int64_t redraw_us = 500000;     // at most two redraws per second
constexpr int64_t banner_us = 2000000;    // splash, STOP and notice
constexpr int64_t shift_us = 300000000;   // burn-in: one pixel every 5 minutes

esp_lcd_panel_handle_t panel{};
bool available = false;
uint8_t frame[pages * width];
uint8_t sent[pages * width];
bool sent_valid = false;
char version_text[22] = "";
int64_t splash_until = 0, stop_until = 0, notice_until = 0, next_redraw = 0;
int dx = 0, dy = 0;

// Bluetooth rune, 7 x 8, rows top to bottom, bit 6 leftmost.
constexpr uint8_t bluetooth[8] = {0x08, 0x0c, 0x2a, 0x1c, 0x1c, 0x2a, 0x0c, 0x08};

void pixel(int x, int y) {
    x += dx;
    y += dy;
    if (x < 0 || x >= width || y < 0 || y >= height)
        return;
    frame[(y / 8) * width + x] |= 1u << (y % 8);
}
void fill(int x, int y, int w, int h) {
    for (int row = y; row < y + h; ++row)
        for (int column = x; column < x + w; ++column)
            pixel(column, row);
}
// One 5x7 glyph in a 6x8 cell, magnified by scale.
int text(int x, int y, const char *value, int scale = 1) {
    for (; *value; ++value, x += 6 * scale) {
        const uint8_t code = static_cast<uint8_t>(*value);
        if (code < panel_font_first || code > panel_font_last)
            continue;
        for (int column = 0; column < 5; ++column)
            for (int row = 0; row < 7; ++row)
                if (panel_font[code - panel_font_first][column] & (1u << row))
                    fill(x + column * scale, y + row * scale, scale, scale);
    }
    return x;
}
int centred(const char *value, int scale) {
    return (width - 2 - static_cast<int>(strlen(value)) * 6 * scale) / 2;
}

// Late-90s phone status bar: rune, then "?" while advertising (blinking) or a
// cross when BLE does not work; signal bars only while connected.
void status_bar(const panel_display::Status &status, bool blink) {
    using panel_display::Link;
    if (status.link != Link::advertising || blink)
        for (int row = 0; row < 8; ++row)
            for (int column = 0; column < 7; ++column)
                if (bluetooth[row] & (0x40u >> column))
                    pixel(column, row);
    if (status.link == Link::advertising && blink)
        text(9, 0, "?");
    if (status.link == Link::off)
        for (int i = 0; i < 8; ++i) {
            pixel(i, i);
            pixel(7 - i, i);
        }
    if (status.link != Link::connected)
        return;
    const int bars = status.rssi >= -60 ? 4 : status.rssi >= -70 ? 3 : status.rssi >= -80 ? 2
                                                : status.rssi >= -90 ? 1 : 0;
    for (int bar = 0; bar < 4; ++bar) {
        const int bar_height = 2 * (bar + 1);
        if (bar < bars)
            fill(10 + bar * 3, 8 - bar_height, 2, bar_height);
        else
            pixel(10 + bar * 3, 7); // empty bar keeps its place
    }
}

void splash() {
    const int left = (width - 2 - panel_logo_size) / 2;
    for (int row = 0; row < panel_logo_size; ++row)
        for (int column = 0; column < panel_logo_size; ++column)
            if (panel_logo[row][column / 8] & (0x80u >> (column % 8)))
                pixel(left + column, row);
    text(centred("SURRKLANK", 1), 43, "SURRKLANK");
    text(centred(version_text, 1), 53, version_text);
}

// Player area is a placeholder until the MIDI player fills it.
void player(int64_t now) {
    if (now < stop_until) {
        text(centred("STOP", 3), 20, "STOP", 3);
        return;
    }
    text(centred("-- brak --", 2), 18, "-- brak --", 2);
    fill(0, 40, 7, 7); // stop symbol
    text(12, 40, "--:--/--:--");
    if (now < notice_until)
        text(0, 54, "Brak odtwarzacza MIDI");
}

void render(const panel_display::Status &status, int64_t now) {
    memset(frame, 0, sizeof(frame));
    // Burn-in: the image walks a 1-pixel square, right, down, left, up.
    static constexpr int walk[4][2] = {{0, 0}, {1, 0}, {1, 1}, {0, 1}};
    const int step = static_cast<int>((now / shift_us) % 4);
    dx = walk[step][0];
    dy = walk[step][1];
    if (now < splash_until) {
        splash();
        return;
    }
    status_bar(status, (now / redraw_us) % 2 == 0);
    player(now);
}

// Sends only the pages that differ from the last successful transfer.
void flush() {
    for (int page = 0; page < pages; ++page) {
        uint8_t *data = frame + page * width;
        if (sent_valid && !memcmp(data, sent + page * width, width))
            continue;
        if (esp_lcd_panel_draw_bitmap(panel, 0, page * 8, width, page * 8 + 8, data) != ESP_OK) {
            available = false; // until restart; nothing else depends on the screen
            return;
        }
        memcpy(sent + page * width, data, width);
    }
    sent_valid = true;
}
} // namespace

bool panel_display::init(i2c_master_bus_handle_t bus, const char *version, int64_t now_us) {
    if (i2c_master_probe(bus, display_address, 20) != ESP_OK)
        return false;
    esp_lcd_panel_io_i2c_config_t io_config = {};
    io_config.dev_addr = display_address;
    io_config.control_phase_bytes = 1;
    io_config.dc_bit_offset = 6;
    io_config.lcd_cmd_bits = 8;
    io_config.lcd_param_bits = 8;
    io_config.scl_speed_hz = 100000;
    esp_lcd_panel_io_handle_t io;
    if (esp_lcd_new_panel_io_i2c(bus, &io_config, &io) != ESP_OK)
        return false;
    esp_lcd_panel_dev_config_t panel_config = {};
    panel_config.bits_per_pixel = 1;
    panel_config.reset_gpio_num = -1;
    if (esp_lcd_new_panel_ssd1306(io, &panel_config, &panel) != ESP_OK || esp_lcd_panel_init(panel) != ESP_OK ||
        esp_lcd_panel_disp_on_off(panel, true) != ESP_OK)
        return false;
    snprintf(version_text, sizeof(version_text), "%s", version);
    available = true;
    sent_valid = false;
    splash_until = now_us + banner_us;
    next_redraw = 0;
    update(Status{}, now_us);
    return available;
}

bool panel_display::present() { return available; }

void panel_display::show_stop(int64_t now_us) {
    stop_until = now_us + banner_us;
    next_redraw = 0;
}

void panel_display::show_notice(int64_t now_us) {
    notice_until = now_us + banner_us;
    next_redraw = 0;
}

void panel_display::update(const Status &status, int64_t now_us) {
    if (!available || now_us < next_redraw)
        return;
    next_redraw = now_us + redraw_us;
    render(status, now_us);
    flush();
}
