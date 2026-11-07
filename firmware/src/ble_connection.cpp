#include "ble_connection.h"
#include "atx_power.h"
#include "ota_update.h"
#include "esp_ble_conn_mgr.h"
#include "esp_event.h"
#include "esp_log.h"
#include "host/ble_gap.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
char lastReply[512]="IDLE";
void describe(char* text, size_t capacity);
std::atomic<uint16_t> connectionHandle{0xffff};
// FFF2 event v1: version, type, sequence LE32, typed payload (<=20 bytes).
void put32(uint8_t* bytes, uint32_t value) {
    for (int i=0;i<4;++i) bytes[i]=(value>>(8*i))&0xff;
}
void notify(uint8_t* bytes, uint16_t length) {
    if(connectionHandle==0xffff)return;
    esp_ble_conn_data_t message={};message.type=BLE_CONN_UUID_TYPE_16;
    message.uuid.uuid16=0xfff2;message.data=bytes;message.data_len=length;
    esp_err_t error=esp_ble_conn_notify_by_handle(connectionHandle,&message);
    if(error!=ESP_OK)ESP_LOGD("connection","state notification: %s",esp_err_to_name(error));
}
void notify_atx(atx::State state) {
    uint8_t bytes[7]={1,1};put32(bytes+2,state.sequence);bytes[6]=state.on?1:0;
    notify(bytes,sizeof(bytes));
}
void notify_firmware(ota::State state) {
    uint8_t bytes[15]={1,2};put32(bytes+2,state.sequence);bytes[6]=state.stage;
    put32(bytes+7,state.received);put32(bytes+11,(uint32_t)state.error);
    notify(bytes,sizeof(bytes));
}
esp_err_t output(const char* value,uint8_t** data,uint16_t* length,uint8_t* status){
    *length=strlen(value);*data=(uint8_t*)malloc(*length);
    if(!*data)return ESP_ERR_NO_MEM;
    memcpy(*data,value,*length);*status=0;return ESP_OK;
}
esp_err_t command(const uint8_t* input,uint16_t size,uint8_t** data,uint16_t* length,void*,uint8_t* status){
    if(!input)return output(lastReply,data,length,status);
    *status=0;*data=nullptr;*length=0;
    if(size==0||size>=64){*status=0x0d;return ESP_ERR_INVALID_SIZE;}
    char line[64];memcpy(line,input,size);line[size]=0;
    if(!strncmp(line,"PING ",5) && strlen(line+5)>0 && strspn(line+5,"0123456789")==strlen(line+5)){
        snprintf(lastReply,sizeof(lastReply),"PONG %s",line+5);
    }else if(!strcmp(line,"ATX ON") || !strcmp(line,"ATX OFF")){
        bool accepted=atx::set(!strcmp(line,"ATX ON"));
        snprintf(lastReply,sizeof(lastReply),"%s",accepted?(atx::is_on()?"ATX ON":"ATX OFF"):"ERR MAINTENANCE");
    }else if(!strcmp(line,"ATX PREPARE")){
        atx::prepare();strcpy(lastReply,"ATX OFF");
    }else if(!strcmp(line,"INFO")){
        describe(lastReply,sizeof(lastReply));
    }else if(!strcmp(line,"CONFIRM")){
        snprintf(lastReply,sizeof(lastReply),"%s",ota::confirm()==ESP_OK?"VALID":"ERR CONFIRM");
    }else if(!strcmp(line,"REBOOT")){
        snprintf(lastReply,sizeof(lastReply),"%s",ota::reboot()==ESP_OK?"REBOOTING":"ERR REBOOT");
    }else{snprintf(lastReply,sizeof(lastReply),"ERR COMMAND");*status=0x13;return ESP_ERR_INVALID_ARG;}
    return ESP_OK;
}
void describe(char* text, size_t capacity){
    ota::describe(text,capacity);
    ble_gap_conn_desc description={};
    if(connectionHandle!=0xffff && ble_gap_conn_find(connectionHandle,&description)==0){
        size_t end=strlen(text)-1;
        snprintf(text+end,capacity-end,",\"interval_us\":%u,\"latency\":%u}",description.conn_itvl*1250,description.conn_latency);
    }
    size_t end=strlen(text)-1;
    auto state=atx::state();
    snprintf(text+end,capacity-end,",\"atx_on\":%s,\"atx_sequence\":%lu,\"events_version\":1}",state.on?"true":"false",(unsigned long)state.sequence);
}
esp_err_t info(const uint8_t*,uint16_t,uint8_t** data,uint16_t* length,void*,uint8_t* status){
    char text[512];describe(text,sizeof(text));
    return output(text,data,length,status);
}
void event(void*,esp_event_base_t,int32_t id,void* value){
    if(id==ESP_BLE_CONN_EVENT_DISCONNECTED){
        if(value)ESP_LOGW("connection","disconnected reason=0x%x",((esp_ble_conn_event_data_t*)value)->disconnected.reason);
        connectionHandle=0xffff;strcpy(lastReply,"IDLE");ota::disconnected();
    }
    if(id==ESP_BLE_CONN_EVENT_CONNECTED && value){
        auto* event=(esp_ble_conn_event_data_t*)value;
        connectionHandle=event->connected.conn_handle;
        ble::request_fast_link();
    }
}
}
esp_err_t ble::init(){
    // Preserve the discovery identifier used by existing Surrklank installations.
    esp_ble_conn_config_t config={};strcpy((char*)config.device_name,"EM-MIDI-IDF");
    config.include_service_uuid=1;config.adv_uuid_type=BLE_CONN_UUID_TYPE_16;config.adv_uuid16=0x8018;
    esp_err_t error=esp_ble_conn_init(&config);if(error!=ESP_OK)return error;
    static esp_ble_conn_character_t chars[2]={};
    chars[0].name="command";chars[0].type=BLE_CONN_UUID_TYPE_16;chars[0].uuid.uuid16=0xfff1;
    chars[0].flag=BLE_CONN_GATT_CHR_READ|BLE_CONN_GATT_CHR_WRITE;chars[0].uuid_fn=command;
    chars[1].name="information";chars[1].type=BLE_CONN_UUID_TYPE_16;chars[1].uuid.uuid16=0xfff2;
    chars[1].flag=BLE_CONN_GATT_CHR_READ|BLE_CONN_GATT_CHR_NOTIFY;chars[1].uuid_fn=info;
    static esp_ble_conn_svc_t service={};service.type=BLE_CONN_UUID_TYPE_16;service.uuid.uuid16=0xfff0;
    service.nu_lookup_count=2;service.nu_lookup=chars;
    error=esp_ble_conn_add_svc(&service);if(error!=ESP_OK)return error;
    atx::set_listener(notify_atx);
    ota::set_listener(notify_firmware);
    return esp_event_handler_register(BLE_CONN_MGR_EVENTS,ESP_EVENT_ANY_ID,event,nullptr);
}
esp_err_t ble::start(){return esp_ble_conn_start();}

esp_err_t ble::request_fast_link(){
    if(connectionHandle==0xffff)return ESP_ERR_INVALID_STATE;
    esp_ble_conn_params_t parameters={};parameters.itvl_min=12;parameters.itvl_max=12;parameters.supervision_timeout=400;
    esp_err_t dle=esp_ble_conn_set_data_len(connectionHandle,251,2120);
    esp_err_t interval=esp_ble_conn_update_params(connectionHandle,&parameters);
    ESP_LOGI("connection","DLE request: %s; interval request: %s",esp_err_to_name(dle),esp_err_to_name(interval));
    return interval;
}
