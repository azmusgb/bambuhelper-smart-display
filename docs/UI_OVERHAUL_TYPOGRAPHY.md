# v11.25 physical typography hierarchy

The WS350 screen should read in this order:

1. page / mode
2. current state or primary value
3. one short explanatory line
4. actions
5. secondary metadata

Guidelines:

- Use the largest existing firmware font for the one dominant value on a primary screen.
- Use body size for job/status/action labels.
- Use small text only for secondary metadata that is not required to operate the device.
- Avoid all-caps paragraphs; reserve uppercase for short mode/action labels.
- Prefer one concise line over wrapping long prose into a card.
- If a value is unknown, render `Unknown` or an em dash as appropriate rather than a fabricated numeric placeholder.
