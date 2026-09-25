# Known Issue: hardware-* screens crash on draw

## Symptom
Any of the hardware-* views triggers a Guru Meditation LoadProhibited
and reboots the device:

- hardware-sound
- hardware-cooldown
- hardware-led
- hardware-finish
- hardware-error
- hardware-power
- hardware-auto-off

All seven go through drawAudioSettings() in smart_hub.cpp.

## Crash signature
Guru Meditation Error: Core 1 panic'ed (LoadProhibited)
EXCVADDR: 0x0f0a0501
Backtrace: 0x42039609 0x42048b87 0x4206bb92 0x4206bc9d
           0x4206bd7a 0x4206bf19 0x4205bd42 0x4202c9e1 0x42073009

EXCVADDR 0x0f0a0501 is packed bytes, not a real pointer. Something
is dereferencing corrupted data inside drawAudioSettings() or one of
its helpers.

## Impact
- Physical device: not reachable without crashing
- Capture automation: aborts at screen 37/38

## Next steps
1. Decode backtrace with addr2line:
   xtensa-esp32s3-elf-addr2line -pfiaC -e firmware.elf <addresses>
2. Read drawAudioSettings() (smart_hub.cpp ~line 2221)
3. Check buzzerSettings / ES8311 codec state initialization
4. Likely missing null guard on a codec object, or uninitialized struct field
