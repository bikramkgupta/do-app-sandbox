# Transport Test Results

Date: run locally with `doctl` auth (`bg-doks-docr`), Spaces bucket `demo-app-sandbox-python` (`syd1`).

## Sandboxes Used
- Python: `bench-py-19e062` (`app_id=472d71f3-a2c5-445c-a3f3-ca57ed3a7fb7`) – create time ~33.4s
- Node: `bench-node-ec401c` (`app_id=80680c96-f1f9-49f2-a45d-217aa6cd1a85`) – create time ~49.1s

## File Transfer Findings
- Console (WebSocket) uploads:
  - 1MB with 64KB base64 chunks (python sandbox): **~134s** end-to-end.
  - Larger chunk sizes (128–256KB) hit `File name too long` / command-length issues.
  - Attempts for 1–4MB via console timed out at 120–300s. Practically unusable beyond small control payloads.
- Spaces side channel:
  - 100MB upload via `filesystem.upload_large` (python sandbox): **~30.3s** end-to-end (includes presign, client→Spaces, sandbox curl).
  - 1GB upload via `filesystem.upload_large` (python sandbox): **~263.5s** end-to-end (same path; ~4.4 MB/s effective).
  - Presigned URLs default to 15 minutes; adjust the presign expiry constant if you want shorter/longer.

## Recommendations
- Treat the console transport as a control plane only. Keep payloads **≤ ~250KB**; anything larger should go through Spaces when configured.
- We now chunk console writes at **32KB** to avoid command-length errors; users do not control chunk size.
- Spaces should be the default for real file transfers. Shorten presigned URL lifetimes if desired and rely on cleanup after transfers.
