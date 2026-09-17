#include "workshop_media_runtime.h"

#include <Arduino.h>
#include "ws350_media_backend.h"

namespace {
workshop::media::MediaService gMediaService;
workshop::media::Ws350MediaBackend gMediaBackend;
}

void workshopMediaBegin() {
  gMediaService.begin(&gMediaBackend, millis());
}

void workshopMediaPoll() {
  gMediaService.poll(millis());
}

workshop::media::MediaService& workshopMediaService() {
  return gMediaService;
}

const workshop::media::Snapshot& workshopMediaSnapshot() {
  return gMediaService.snapshot();
}
