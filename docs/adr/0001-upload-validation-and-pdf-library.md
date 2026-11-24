# ADR 0001: Upload validation, duplicates and PDF library

Status: accepted (T04, 2026-11-24)

## Decisions
- **PyMuPDF 1.28.2, not 2.1.** 2.1 pulls onnxruntime, numpy, networkx and a layout model (~110 MB) that the MVP does not need. 1.28.2 has no dependencies and provides encryption detection, page counts and text extraction. PyMuPDF is AGPL-3.0 (or commercial); acceptable for a local demo, must be revisited before any distribution or hosted deployment (alternative: pypdf, BSD).
- **Duplicates return the existing document** (`200`, `duplicate: true`) instead of `409`, keyed by SHA-256 of the bytes. The first upload's name is kept. A concurrent identical upload that loses the unique-index race gets the same response and its stored file is deleted.
- **Validation:** `.pdf`/`.txt`/`.md` only; content must match extension (`%PDF-` signature, UTF-8 without NUL bytes); 10 MB limit; PDFs must open without a password and have 1–100 pages. Scanned/no-text PDFs are rejected at parse time (T05).
- **Storage:** random `<uuid hex>.<ext>` keys, validated by regex on every access; user file names are metadata only. Files are written via temp file + atomic rename; the file is removed if the DB insert fails.
- **Request size:** rejected early from `Content-Length`. Known limitation: a chunked body without `Content-Length` is spooled to temp disk by the multipart parser before the route rejects it (the route reads at most limit+1 bytes into memory). Acceptable for a loopback-only demo; production needs a streaming byte limit at the proxy or middleware.
- **Original file responses** are `inline` with `nosniff`. Text/markdown also gets `Content-Security-Policy: sandbox` so it cannot execute in the API origin; PDFs do not, because a sandboxed document cannot load the browser's PDF viewer.
- **Encrypted PDFs:** rejected only when a user password is required (`needs_pass`); owner-password-only PDFs (permission restrictions) are accepted.
