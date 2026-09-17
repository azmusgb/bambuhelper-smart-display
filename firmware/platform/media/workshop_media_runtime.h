#pragma once

#include "media_service.h"

void workshopMediaBegin();
void workshopMediaPoll();
workshop::media::MediaService& workshopMediaService();
const workshop::media::Snapshot& workshopMediaSnapshot();
