#include "recovery_manager.h"
#include "wifi_manager.h"
#include <Preferences.h>
#include <esp_attr.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>

namespace {
constexpr uint32_t kRapidMagic = 0x52454334;
constexpr uint32_t kRapidClearMs = 15000;
constexpr uint32_t kCandidateHealthyMs = 25000;
constexpr uint8_t kCandidateMaxAttempts = 3;
constexpr char kNamespace[] = "bh_recovery";
RTC_DATA_ATTR uint32_t sRapidMagic = 0;
RTC_DATA_ATTR uint8_t sRapidCount = 0;
bool sSafeMode = false;
bool sRapidCleared = false;
bool sCandidatePending = false;
bool sWebReady = false;
uint8_t sCandidateAttempts = 0;
String sFallbackLabel;
String sKnownGoodLabel;
Preferences prefs;

String runningLabel(){
  const esp_partition_t* p=esp_ota_get_running_partition();
  return p && p->label ? String(p->label) : String();
}
const esp_partition_t* byLabel(const String& label){
  if(!label.length()) return nullptr;
  return esp_partition_find_first(ESP_PARTITION_TYPE_APP,ESP_PARTITION_SUBTYPE_ANY,label.c_str());
}
bool switchTo(const esp_partition_t* target,String& message){
  if(!target){message="No bootable firmware partition was found";return false;}
  const esp_partition_t* run=esp_ota_get_running_partition();
  if(run && target->address==run->address){message="Requested firmware is already running";return false;}
  esp_app_desc_t d;
  if(esp_ota_get_partition_description(target,&d)!=ESP_OK){message="Target firmware slot is empty or unreadable";return false;}
  esp_err_t err=esp_ota_set_boot_partition(target);
  if(err!=ESP_OK){message=String("Firmware verification failed: ")+esp_err_to_name(err);return false;}
  message=String("Boot partition switched to ")+target->label;
  return true;
}
void loadState(){
  prefs.begin(kNamespace,false);
  sCandidatePending=prefs.getBool("candidate",false);
  sCandidateAttempts=prefs.getUChar("attempts",0);
  sFallbackLabel=prefs.getString("fallback","");
  sKnownGoodLabel=prefs.getString("known","");
  if(prefs.getBool("safe_next",false)){sSafeMode=true;prefs.remove("safe_next");}
  prefs.end();
}
void saveCandidate(){
  prefs.begin(kNamespace,false);
  prefs.putBool("candidate",sCandidatePending);
  prefs.putUChar("attempts",sCandidateAttempts);
  if(sFallbackLabel.length()) prefs.putString("fallback",sFallbackLabel); else prefs.remove("fallback");
  if(sKnownGoodLabel.length()) prefs.putString("known",sKnownGoodLabel);
  prefs.end();
}
void acceptCandidate(){
  sCandidatePending=false;sCandidateAttempts=0;sKnownGoodLabel=runningLabel();sFallbackLabel="";saveCandidate();
  esp_ota_mark_app_valid_cancel_rollback();
  Serial.printf("Recovery: candidate accepted as known-good (%s)\n",sKnownGoodLabel.c_str());
}
}

void recoveryBootProbe(){
  if(sRapidMagic!=kRapidMagic){sRapidMagic=kRapidMagic;sRapidCount=0;}
  if(sRapidCount<250) ++sRapidCount;
  if(sRapidCount>=3){sSafeMode=true;sRapidCount=0;Serial.println("Recovery: triple reset -> Safe Mode");}
  loadState();
  if(!sCandidatePending) return;
  if(sCandidateAttempts<250) ++sCandidateAttempts;
  saveCandidate();
  Serial.printf("Recovery: candidate boot attempt %u/%u\n",(unsigned)sCandidateAttempts,(unsigned)kCandidateMaxAttempts);
  if(sCandidateAttempts<kCandidateMaxAttempts) return;
  String why;
  if(switchTo(byLabel(sFallbackLabel),why)){
    prefs.begin(kNamespace,false);prefs.putBool("candidate",false);prefs.putUChar("attempts",0);prefs.putString("known",sFallbackLabel);prefs.remove("fallback");prefs.end();
    Serial.printf("Recovery: repeated candidate failure; %s\n",why.c_str());Serial.flush();delay(150);ESP.restart();
  }
  sSafeMode=true;
  Serial.printf("Recovery: rollback unavailable (%s); Safe Mode forced\n",why.c_str());
}
void recoveryTick(){
  uint32_t now=millis();
  if(!sRapidCleared && now>=kRapidClearMs){sRapidCount=0;sRapidCleared=true;}
  if(sCandidatePending && now>=kCandidateHealthyMs && sWebReady && (isWiFiConnected()||isAPMode())) acceptCandidate();
}
void recoveryArmCandidateBoot(){
  String current=runningLabel();
  prefs.begin(kNamespace,false);prefs.putBool("candidate",true);prefs.putUChar("attempts",0);prefs.putString("fallback",current);if(current.length())prefs.putString("known",current);prefs.end();
  sCandidatePending=true;sCandidateAttempts=0;sFallbackLabel=current;sKnownGoodLabel=current;
  Serial.printf("Recovery: OTA candidate armed; fallback=%s\n",current.c_str());
}
void recoveryMarkWebReady(){sWebReady=true;}
bool recoveryWebReady(){return sWebReady;}
bool recoverySafeModeActive(){return sSafeMode;}
void recoveryRequestSafeModeNextBoot(){prefs.begin(kNamespace,false);prefs.putBool("safe_next",true);prefs.end();}
void recoveryClearSafeMode(){sSafeMode=false;prefs.begin(kNamespace,false);prefs.remove("safe_next");prefs.end();}
uint8_t recoveryRapidBootCount(){return sRapidCount;}
uint8_t recoveryCandidateAttempts(){return sCandidateAttempts;}
bool recoveryCandidatePending(){return sCandidatePending;}
String recoveryCurrentSlot(){return runningLabel();}
String recoveryKnownGoodSlot(){return sKnownGoodLabel;}
String recoveryFallbackSlot(){return sFallbackLabel;}
bool recoveryRollbackNow(String& message){
  const esp_partition_t* other=esp_ota_get_next_update_partition(nullptr);
  if(!switchTo(other,message)) return false;
  prefs.begin(kNamespace,false);prefs.putBool("candidate",false);prefs.putUChar("attempts",0);prefs.remove("fallback");prefs.end();
  sCandidatePending=false;sCandidateAttempts=0;sFallbackLabel="";return true;
}
