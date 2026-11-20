idf_component_register(SRCS "main.cpp" "ble_connection.cpp" "ota_update.cpp" "atx_power.cpp" "fdd_engine.cpp" "fdd_control.cpp" "drive_settings.cpp" "panel.cpp" "panel_display.cpp"
    INCLUDE_DIRS "../include" REQUIRES driver esp_driver_gptimer esp_driver_i2c esp_lcd esp_timer esp_app_format bt nvs_flash app_update esp_event ble_conn_mgr ble_ota_raw ble_services)
