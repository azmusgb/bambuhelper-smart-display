# v11.25 UI state model

The primary WS350 UI must render state, not infer it.

## Printer state

Use only reported/configured device state:

- Unconfigured
- Offline
- Ready
- Printing
- Paused
- Error / attention when authoritative printer state reports it

Do not invent a ready/printing state from stale display context.

## Material / inventory state

Printer AMS telemetry may show slot, reported material text, color and reported remaining percentage when available. It is not Filament Inventory identity.

Inventory identity is one of:

- linked authoritative spool
- Unknown

Color/material similarity is never sufficient to claim a linked spool.

## Quantity state

Where the device contract eventually exposes inventory quantity, presentation must distinguish measured/calculated/printer-estimated/visual/imported/unknown evidence rather than flattening all values to an equivalent certainty.

## Interaction state

Every actionable control can be:

- enabled
- selected
- disabled
- staged
- warning
- guarded destructive
- loading/pending
- failed

Destructive controls use red only when the action is actually destructive. Amber is used for staged/caution states. Ordinary selected/navigation states use cyan/blue.
