# Resolved: hardware-* screens crashed on show

## Symptom
Showing any hardware-* view (hardware-sound, hardware-cooldown, hardware-led,
hardware-finish, hardware-error, hardware-power, hardware-auto-off) through
`/hub/show` triggered a Guru Meditation LoadProhibited and rebooted the device.
Unattended capture aborted at the first hardware-* view.

## Root cause
The crash was not in `drawAudioSettings()`. A backtrace decoded against the
matching `firmware.elf` puts it in `smartHubShowPage()`, in a ROM `strcmp`
called from the network page-name lookup:

```text
Guru Meditation Error: Core 1 panic'ed (LoadProhibited)
EXCVADDR: 0x0f0a0501
0x4203a9b1: smartHubShowPage(char const*) at src/smart_hub.cpp:3881
0x42049e3b: initWebServer()::{lambda()#38} at src/web_server.cpp:3748
```

`apply_smart_home_network_locale_layout_v11_23.py` added a four-entry
`kNetworkPages` array and looped `i < HUB_NETWORK_PAGE_COUNT`.
`apply_workshop_os_physical_polish_v11_25_rc8.py` later raised
`HUB_NETWORK_PAGE_COUNT` to 7 for the network wizard. Any page name that missed
the first four entries then compared against `kNetworkPages[4..6]`, which are
past the end of the array. The hardware-* names are checked after this loop, so
all seven crashed.

## Fix
rc8 now bounds the lookup by `sizeof(kNetworkPages)/sizeof(kNetworkPages[0])`
where it changes the page count. The earlier attempt in
`apply_workshop_os_sky_radar_v11_30.py` was removed: that overlay is not in the
OS12 build chain, and its fixed text was overwritten by a later write in the
same script.
