# Workshop OS v11.28 Physical Companion Viewer

v11.28 is the internal reconstruction step between the software-green v11.27 Companion Link candidate and v11.29 Acceptance Mode.

## Purpose

Make a phone photo that was explicitly uploaded through Companion visible on the physical WS350 without creating a second camera renderer or allowing uploads to steal the display automatically.

## Behavior

- phone capture remains JPEG in volatile PSRAM only;
- upload includes validated source width/height, each 1–480 px;
- upload alone never changes the physical screen;
- `POST /companion/capture/show` is the only phone action that activates the physical viewer;
- the existing `SCREEN_CAMERA` JPEG surface is reused;
- phone photos are contain-fitted and letterboxed rather than stretched;
- the overlay identifies `PHONE PHOTO | TAP TO EXIT`;
- leaving the camera surface clears the phone-viewer override;
- when the phone viewer is inactive, the existing chamber-camera path still calls `cameraGetLatestFrame()` unchanged;
- clearing an actively displayed phone photo returns to the remembered screen before releasing the volatile buffer.

## Physical checks carried forward into v11.29

- upload photo from iPhone Safari;
- confirm upload alone does not change WS350 screen;
- tap **Show on Waveshare** and verify correct orientation/aspect ratio;
- tap the WS350 to exit;
- reopen normal chamber camera and verify it is not replaced by the phone image;
- clear the phone photo while viewer is active;
- reboot and confirm phone photo is gone;
- confirm no capture bytes are written to flash.
