#include "drive_settings.h"
#include "nvs.h"

namespace {
constexpr const char *storage = "surrklank";
constexpr const char *select_key = "select";
} // namespace

void drive_settings::load(fdd::Line (&lines)[fdd::count]) {
    for (auto &line : lines)
        line = fdd::default_select;
    nvs_handle_t handle;
    if (nvs_open(storage, NVS_READONLY, &handle) != ESP_OK)
        return;
    uint8_t stored[fdd::count];
    size_t size = sizeof(stored);
    if (nvs_get_blob(handle, select_key, stored, &size) == ESP_OK && size == sizeof(stored))
        for (int i = 0; i < fdd::count; ++i) {
            const auto line = static_cast<fdd::Line>(stored[i]);
            if (fdd::is_select(line))
                lines[i] = line;
        }
    nvs_close(handle);
}

esp_err_t drive_settings::store(const fdd::Line (&lines)[fdd::count]) {
    uint8_t stored[fdd::count];
    for (int i = 0; i < fdd::count; ++i)
        stored[i] = static_cast<uint8_t>(lines[i]);
    nvs_handle_t handle;
    esp_err_t error = nvs_open(storage, NVS_READWRITE, &handle);
    if (error != ESP_OK)
        return error;
    error = nvs_set_blob(handle, select_key, stored, sizeof(stored));
    if (error == ESP_OK)
        error = nvs_commit(handle);
    nvs_close(handle);
    return error;
}
