#pragma once

#include "media_service.h"
#include "ws350_media_backend.h"

void workshopMediaBegin();
void workshopMediaPoll();
workshop::media::MediaService& workshopMediaService();
const workshop::media::Snapshot& workshopMediaSnapshot();
const workshop::media::VideoDiagnostics& workshopVideoDiagnostics();
