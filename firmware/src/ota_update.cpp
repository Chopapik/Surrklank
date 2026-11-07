// Application integration only. Packet ordering, CRC and receipts belong to Espressif ble_ota_raw.
#include "ota_update.h"
#include "atx_power.h"
#include "ble_connection.h"
#include "esp_ble_ota_raw.h"
#include "esp_ble_ota_svc.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstring>

namespace {
struct Sector {uint32_t epoch;uint32_t length;uint8_t data[4096];};
QueueHandle_t queue;
SemaphoreHandle_t mutex;
esp_ota_handle_t handle;
const esp_partition_t* target;
bool writing=false,ready=false;
uint32_t expected=0,received=0,committed=0,epoch=0;
esp_err_t failure=ESP_OK;
int64_t lastData=0,bootAt=0;
// Batch sequential SDK writes at a flash erase-block boundary. No protocol change.
uint8_t flashBlock[64*1024];
size_t buffered=0;
ota::State published = {};
void (*listener)(ota::State) = nullptr;
// INFO and notifications use the same stage mapping while the flash mutex is held.
uint8_t current_stage() { return failure != ESP_OK ? 3 : ready ? 2 : writing ? 1 : 0; }
const char* stage_name(uint8_t stage) {
    switch(stage) { case 1: return "writing"; case 2: return "ready"; case 3: return "failed"; default: return "idle"; }
}
// BLE callbacks run after releasing the mutex.
ota::State state_update() {
    uint8_t stage = current_stage();
    // Report bytes after each flash block has actually been written.
    if (published.stage != stage || published.received != committed || published.error != failure)
        published = {stage, committed, failure, published.sequence + 1};
    return published;
}
void notify(ota::State state) { if (listener) listener(state); }
bool trial(){esp_ota_img_states_t state;return esp_ota_get_state_partition(esp_ota_get_running_partition(),&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY;}
void abortTransfer(){if(writing)esp_ota_abort(handle);writing=false;buffered=0;++epoch;}
esp_err_t begin(uint32_t size){
    xSemaphoreTake(mutex,portMAX_DELAY);
    esp_err_t error=ESP_ERR_INVALID_STATE;
    if(!writing&&!ready&&!trial()){
        target=esp_ota_get_next_update_partition(nullptr);
        if(target&&target->address!=esp_ota_get_running_partition()->address&&size<=target->size&&size){
            atx::prepare();
            ble::request_fast_link();
            ESP_LOGI("ota","begin target=0x%lx bytes=%lu reset_reason=%d",(unsigned long)target->address,(unsigned long)size,(int)esp_reset_reason());
            error=esp_ota_begin(target,OTA_WITH_SEQUENTIAL_WRITES,&handle);
            ESP_LOGI("ota","begin result=%s",esp_err_to_name(error));
            if(error==ESP_OK){++epoch;writing=true;received=0;committed=0;buffered=0;expected=size;failure=ESP_OK;lastData=esp_timer_get_time();}
        }
    }
    auto state = state_update();
    xSemaphoreGive(mutex);notify(state);return error;
}
void receive(uint8_t* data,uint32_t length){
    Sector sector={};xSemaphoreTake(mutex,portMAX_DELAY);
    sector.epoch=epoch;sector.length=length;
    bool valid=writing&&length>0&&length<=sizeof(sector.data);
    if(valid)memcpy(sector.data,data,length);
    xSemaphoreGive(mutex);
    if(!valid||xQueueSend(queue,&sector,pdMS_TO_TICKS(1000))!=pdTRUE){
        xSemaphoreTake(mutex,portMAX_DELAY);failure=ESP_ERR_NO_MEM;abortTransfer();auto state=state_update();xSemaphoreGive(mutex);notify(state);
    }
}
void worker(void*){
    Sector sector;
    for(;;){
        bool available=xQueueReceive(queue,&sector,pdMS_TO_TICKS(500))==pdTRUE;
        xSemaphoreTake(mutex,portMAX_DELAY);
        uint32_t previous = published.sequence;
        if(available&&writing&&sector.epoch==epoch){
            if(sector.length>expected-received || buffered+sector.length>sizeof(flashBlock)){
                failure=ESP_ERR_INVALID_SIZE;abortTransfer();
            }else{
                memcpy(flashBlock+buffered,sector.data,sector.length);
                buffered+=sector.length;received+=sector.length;lastData=esp_timer_get_time();
                if(buffered==sizeof(flashBlock)||received==expected){
                    failure=esp_ota_write(handle,flashBlock,buffered);
                    if(failure==ESP_OK)committed+=buffered;
                    buffered=0;
                    if(failure!=ESP_OK)abortTransfer();
                    else if(received==expected){
                        failure=esp_ota_end(handle);writing=false;
                        if(failure==ESP_OK)failure=esp_ota_set_boot_partition(target);
                        ready=failure==ESP_OK;
                    }
                }
            }
        }
        if(writing&&esp_timer_get_time()-lastData>30000000){failure=ESP_ERR_TIMEOUT;abortTransfer();}
        auto state = state_update();
        xSemaphoreGive(mutex);
        if (state.sequence != previous) notify(state);
        if(trial()&&esp_timer_get_time()-bootAt>60000000)esp_ota_mark_app_invalid_rollback_and_reboot();
    }
}
void restart(void*){vTaskDelay(pdMS_TO_TICKS(400));esp_restart();}
}
void ota::set_listener(void (*callback)(State)) { listener = callback; }
esp_err_t ota::init(){
    bootAt=esp_timer_get_time();mutex=xSemaphoreCreateMutex();queue=xQueueCreate(4,sizeof(Sector));
    if(!mutex||!queue)return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(esp_ble_ota_raw_init());
    esp_ble_ota_raw_set_ota_begin_cb(begin);
    esp_ble_ota_raw_set_sector_send_window_for_ringbuf(3*4096);
    ESP_ERROR_CHECK(esp_ble_ota_raw_recv_fw_data_callback(receive));
    return xTaskCreate(worker,"ota_flash",8192,nullptr,5,nullptr)==pdPASS?ESP_OK:ESP_ERR_NO_MEM;
}
void ota::disconnected(){
    if(!mutex)return;
    xSemaphoreTake(mutex,portMAX_DELAY);abortTransfer();auto state=state_update();xSemaphoreGive(mutex);notify(state);
    // Reset the official profile through its existing STOP parser after link loss.
    const uint8_t stop[]={2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,67,240};
    esp_ble_ota_recv_cmd_data(stop,sizeof(stop));
}
void ota::describe(char* output,size_t capacity){
    const auto* partition=esp_ota_get_running_partition();const auto* desc=esp_app_get_description();
    char sha[65];for(int i=0;i<32;++i)snprintf(sha+2*i,3,"%02x",desc->app_elf_sha256[i]);
    xSemaphoreTake(mutex,portMAX_DELAY);
    snprintf(output,capacity,"{\"identity\":\"%s\",\"version\":\"%s\",\"slot\":%lu,\"trial\":%s,\"ota\":\"%s\",\"received\":%lu,\"error\":%d,\"reset_reason\":%d}",sha,desc->version,(unsigned long)partition->address,trial()?"true":"false",stage_name(current_stage()),(unsigned long)committed,(int)failure,(int)esp_reset_reason());
    size_t end=strlen(output)-1;
    snprintf(output+end,capacity-end,",\"firmware_sequence\":%lu}",(unsigned long)published.sequence);
    xSemaphoreGive(mutex);
}
esp_err_t ota::confirm(){return trial()?esp_ota_mark_app_valid_cancel_rollback():ESP_OK;}
esp_err_t ota::reboot(){
    xSemaphoreTake(mutex,portMAX_DELAY);bool allowed=ready;xSemaphoreGive(mutex);
    if(!allowed)return ESP_ERR_INVALID_STATE;
    return xTaskCreate(restart,"restart",2048,nullptr,5,nullptr)==pdPASS?ESP_OK:ESP_ERR_NO_MEM;
}
