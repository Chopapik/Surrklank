idf_component_register(SRCS "main.cpp" "ble_connection.cpp" "ota_update.cpp" "atx_power.cpp" "fdd_engine.cpp" "fdd_control.cpp"
    INCLUDE_DIRS "../include" REQUIRES driver bt nvs_flash app_update esp_event ble_conn_mgr ble_ota_raw ble_services)
