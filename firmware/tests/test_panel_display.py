"""Render the real OLED module against esp_lcd stubs and write PNG previews.

Set SURRKLANK_PREVIEW_DIR to keep the previews (white-on-black, 4x scale);
otherwise they are written to a temporary folder and discarded.
"""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]

HEADERS = {
    "esp_err.h": """#pragma once
using esp_err_t = int;
constexpr int ESP_OK=0, ESP_FAIL=-1;
""",
    "driver/i2c_master.h": """#pragma once
#include "esp_err.h"
#include <cstdint>
using i2c_master_bus_handle_t = int;
inline bool displayAnswers=true;
inline int i2c_master_probe(int, uint16_t address, int) { return displayAnswers && address==0x3c ? ESP_OK : ESP_FAIL; }
""",
    "esp_lcd_io_i2c.h": """#pragma once
#include "driver/i2c_master.h"
#include <cstddef>
using esp_lcd_panel_io_handle_t = int;
struct esp_lcd_panel_io_i2c_config_t { uint32_t dev_addr; size_t control_phase_bytes; unsigned dc_bit_offset;
    int lcd_cmd_bits, lcd_param_bits; uint32_t scl_speed_hz; };
inline int esp_lcd_new_panel_io_i2c(int, const esp_lcd_panel_io_i2c_config_t* c, esp_lcd_panel_io_handle_t* io) {
    return c->dev_addr==0x3c && c->dc_bit_offset==6 && c->control_phase_bytes==1 ? (*io=1, ESP_OK) : ESP_FAIL; }
""",
    "esp_lcd_panel_ssd1306.h": """#pragma once
#include "esp_lcd_io_i2c.h"
using esp_lcd_panel_handle_t = int;
struct esp_lcd_panel_dev_config_t { int bits_per_pixel; int reset_gpio_num; };
inline int esp_lcd_new_panel_ssd1306(int, const esp_lcd_panel_dev_config_t* c, esp_lcd_panel_handle_t* p) {
    return c->bits_per_pixel==1 ? (*p=1, ESP_OK) : ESP_FAIL; }
""",
    "esp_lcd_panel_ops.h": """#pragma once
#include "esp_lcd_panel_ssd1306.h"
#include <cstring>
// Screen memory of the fake SSD1306, one byte per 8 vertical pixels.
inline uint8_t screen[8*128]={};
inline unsigned pageWrites=0;
inline bool drawFails=false;
inline int esp_lcd_panel_init(int) { return ESP_OK; }
inline int esp_lcd_panel_disp_on_off(int, bool) { return ESP_OK; }
inline int esp_lcd_panel_draw_bitmap(int, int x0, int y0, int x1, int y1, const void* data) {
    if(drawFails) return ESP_FAIL;
    if(x0!=0 || x1!=128 || y0%8 || y1-y0!=8) return ESP_FAIL;
    memcpy(screen+(y0/8)*128, data, 128); ++pageWrites; return ESP_OK; }
""",
}

MAIN = r"""#include "panel_display.cpp"
#include <cassert>
#include <cstdio>
#include <string>
using panel_display::Link;
std::string folder;
bool lit(int x, int y) { return screen[(y/8)*128+x] & (1u << (y%8)); }
int count(int x0, int y0, int x1, int y1) { int n=0; for(int y=y0;y<y1;++y) for(int x=x0;x<x1;++x) n+=lit(x,y); return n; }
void dump(const char* name) {
    FILE* f=fopen((folder+"/"+name+".txt").c_str(),"w");
    for(int y=0;y<64;++y) { for(int x=0;x<128;++x) fputc(lit(x,y)?'#':'.',f); fputc('\n',f); }
    fclose(f);
}
panel_display::Status with(Link link, int rssi=0) { panel_display::Status s; s.link=link; s.rssi=rssi; return s; }
int main(int, char** argv) {
    folder=argv[1];
    // No display at 0x3c: nothing is drawn and the module stays inactive.
    displayAnswers=false;
    assert(!panel_display::init(1,"v1",0) && !panel_display::present());
    displayAnswers=true;
    // Boot splash: logo, name and version, all eight pages sent once.
    assert(panel_display::init(1,"0.2.0",0) && panel_display::present());
    assert(pageWrites==8 && count(44,0,84,40)>200);
    dump("1-splash");
    // During the 2 s splash nothing new is sent; afterwards the status screen.
    panel_display::update(with(Link::advertising), 600000);
    assert(pageWrites==8);
    panel_display::update(with(Link::advertising), 2000000);
    dump("2-advertising");
    const unsigned afterStatus=pageWrites;
    // Advertising blinks the rune and the question mark every 0.5 s; only the
    // status page changes.
    panel_display::update(with(Link::advertising), 2500000);
    assert(pageWrites==afterStatus+1 && count(0,0,16,8)==0);
    panel_display::update(with(Link::advertising), 2700000); // rate limit
    assert(pageWrites==afterStatus+1);
    // Connected: rune with four bars at strong signal, one bar at -85 dBm.
    panel_display::update(with(Link::connected,-55), 3000000);
    const int strong=count(10,0,22,8);
    dump("3-connected");
    panel_display::update(with(Link::connected,-85), 3500000);
    assert(count(10,0,22,8) < strong && count(10,0,22,8) > 0);
    // BLE not working: crossed rune, no bars, no question mark.
    panel_display::update(with(Link::off), 4000000);
    assert(count(0,0,8,8)>0 && count(9,0,22,8)==0);
    dump("4-ble-off");
    // STOP banner at once (no rate limit), gone after 2 s.
    panel_display::show_stop(4100000);
    panel_display::update(with(Link::connected,-55), 4100000);
    assert(count(20,18,108,44)>300);
    dump("5-stop");
    panel_display::update(with(Link::connected,-55), 6200000);
    assert(count(20,18,108,44)<300);
    // PLAY without a MIDI player: notice on the bottom line for 2 s.
    panel_display::show_notice(6300000);
    panel_display::update(with(Link::connected,-55), 6300000);
    assert(count(0,53,128,64)>40);
    dump("6-no-player");
    panel_display::update(with(Link::connected,-55), 8400000);
    assert(count(0,53,128,64)==0);
    // Burn-in: after 5 minutes the whole image is one pixel to the right.
    int before[2]={-1,-1};
    for(int x=0;x<128 && before[0]<0;++x) if(count(x,0,x+1,64)) before[0]=x;
    panel_display::update(with(Link::connected,-55), 300000000LL+100);
    for(int x=0;x<128 && before[1]<0;++x) if(count(x,0,x+1,64)) before[1]=x;
    assert(before[1]==before[0]+1);
    // A failed transfer disables drawing until restart.
    drawFails=true;
    panel_display::show_stop(300100000LL);
    panel_display::update(with(Link::connected,-55), 300100000LL);
    assert(!panel_display::present());
    drawFails=false;
    const unsigned stopped=pageWrites;
    panel_display::update(with(Link::off), 301000000LL);
    assert(pageWrites==stopped);
    puts("panel display: splash, status bar, bars, STOP, notice, page diff, rate limit, pixel shift and loss passed");
}
"""


def write_png(text_path, png_path, scale=4):
    rows = text_path.read_text().splitlines()
    width, height = len(rows[0]) * scale, len(rows) * scale
    raw = bytearray()
    for row in rows:
        line = bytearray([0])
        for char in row:
            line += (b"\xf0\xf8\xff" if char == "#" else b"\x05\x08\x10") * scale
        raw += bytes(line) * scale
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    png_path.write_bytes(png)


class PanelDisplayTest(unittest.TestCase):
    def test_render_and_preview(self):
        with tempfile.TemporaryDirectory(prefix="surrklank-oled-") as folder:
            root = Path(folder)
            for name, text in HEADERS.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            (root / "main.cpp").write_text(MAIN)
            binary = root / "test-oled"
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(root), "-I", str(ROOT / "include"), "-I", str(ROOT / "src"),
                            str(root / "main.cpp"), "-o", str(binary)], check=True)
            frames = root / "frames"
            frames.mkdir()
            subprocess.run([str(binary), str(frames)], check=True)
            output = Path(os.environ.get("SURRKLANK_PREVIEW_DIR", str(frames)))
            output.mkdir(parents=True, exist_ok=True)
            for text in sorted(frames.glob("*.txt")):
                write_png(text, output / (text.stem + ".png"))


if __name__ == "__main__":
    unittest.main()
