# Sky Radar: draw dispatch not firing

## Symptom
POST /hub/show?page=sky-radar returns {"status":"ok"} and does not
crash, but the device renders the System screen instead of the radar.

## Diagnosis needed
Check both switch statements:
1. upstream/src/display_ui.cpp — does `case SCREEN_SKY_RADAR:` exist
   in the top-level screen switch?
2. upstream/src/smart_hub.cpp smartHubDraw() — does
   `case SCREEN_SKY_RADAR: drawSkyRadar(); break;` exist?

Whichever is missing, add it and reflash.

## Next session (30 min)
1. grep -n SCREEN_SKY_RADAR /tmp/sky-radar-test/src/display_ui.cpp
2. grep -n SCREEN_SKY_RADAR /tmp/sky-radar-test/src/smart_hub.cpp
3. Add the missing case
4. Flash, trigger, capture 17-sky-radar.png
