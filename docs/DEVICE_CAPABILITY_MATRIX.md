# Device Capability Matrix

This is the authoritative checklist for capabilities that the Smart Display should expose. A capability is only marked complete when its firmware/API path and user-facing behavior are both implemented.

| Domain | Capability | Target state |
|---|---|---|
| Device | identity / version / uptime | exposed |
| Device | display brightness | controllable |
| Device | standby / wake | controllable |
| Device | touch diagnostics | exposed |
| Device | speaker test / volume | controllable where firmware supports it |
| Network | Wi-Fi status | exposed |
| Network | reconnect | controllable |
| Network | signal / IP / gateway / DNS | exposed |
| Printer | connection state | exposed |
| Printer | job / progress / ETA | exposed |
| Printer | temperatures | exposed |
| Printer | pause / resume / stop | guarded controls |
| AMS | slot/material state | exposed |
| Workshop | filament inventory | service integration |
| System | health / diagnostics | exposed |
| System | logs | exposed |
| System | OTA | verified update flow |
| System | rollback / recovery | always available |
| System | factory reset | explicitly guarded |

## Rules

- Do not claim a setting is supported merely because a UI control exists.
- Unsupported hardware capabilities must be labeled `unsupported`, not silently ignored.
- Destructive actions require confirmation and a recoverable failure path.
- Printer state is read-only unless a command is explicitly implemented and acknowledged by the device.
- OTA must validate the image before staging it and preserve a known-good recovery path.