# Caregiver Telegram alerts

Signed-in `/demo` and `/app` users can select a saved, tenant-owned Telegram connector.
The workspace owner can connect an existing BotFather bot in the alert panel: send
Start to the bot in Telegram, enter its token in the password field, discover the
destination chat, and save. The token is encrypted server-side and never returned.
Send an explicit connection test before presenting the feature.

For uploaded footage, a Nova match first saves the dashboard event. The browser then
re-encodes up to 12 seconds around the sampled match (four seconds before, eight
after, shortened at source boundaries). It uploads this **silent**, reduced-resolution
clip through the existing private recording archive, then calls the Telegram
delivery endpoint. Telegram receives the summary, source timestamp, and an HMAC-signed
clip link valid for 24 hours. Anyone holding that link can view this one clip; it is
not a public bucket or a link to the full original upload. Use only permitted footage.

Keep the browser tab visible during encoding. MediaRecorder/canvas support is
required; clips are capped below Vercel's body limit. If extraction/upload fails,
send the observation without claiming there is a clip, and show the failure in the
dashboard. Webcam analysis currently sends text only, explicitly noting that a clip
is unavailable. This is not a guaranteed emergency detector or an unattended backend
monitor. The browser must remain open for analysis and delivery.

Delivery is tenant-scoped, validates clip ownership and time overlap, and reserves
each event before the external call to prevent duplicate sends. An ambiguous network
failure is shown as unknown rather than automatically retried. Connection tests are
limited to one per minute per connector. HTTP success means Telegram accepted the
message, not that a human read it. Existing SMS remains separate and still requires
AWS sender registration.

## Verification

- `pytest tests/api/test_caregiver_telegram.py`: mocked provider delivery, signed clip
  access/tamper protection, idempotency, connector selection and test throttling.
- `pnpm --dir apps/web test`: clip-boundary tests and frontend regressions.
- Manual production acceptance: connect bot, receive test, upload permitted footage,
  analyze a positive event, open the resulting link on a phone, verify the actual
  clip, then run a negative example and confirm no alert.

Production acceptance must be performed with a real connected Telegram chat; unit
tests alone do not prove phone delivery or browser encoding compatibility.
