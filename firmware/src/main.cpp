#include "ble_connection.h"
#include "ota_update.h"
#include "nvs_flash.h"
#include "esp_event.h"
extern "C" void app_main(){
    esp_err_t error=nvs_flash_init();
    if(error==ESP_ERR_NVS_NO_FREE_PAGES||error==ESP_ERR_NVS_NEW_VERSION_FOUND){ESP_ERROR_CHECK(nvs_flash_erase());error=nvs_flash_init();}
    ESP_ERROR_CHECK(error);
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    ESP_ERROR_CHECK(ble::init());
    ESP_ERROR_CHECK(ota::init());
    ESP_ERROR_CHECK(ble::start());
}
