# cert-engine — Bulk Certificate Generator & Static QR Verification System

Zero-cost, local-first certificate generation with a client-side, serverless
verification portal — ready for GitHub Pages from the `/docs` folder.

## Features

- **Local Python CLI engine** (`generate.py`) — reads `participants.csv`, renders
  certificates onto a 3508 × 2480 px A4 landscape @ 300 DPI template, and
  exports PDF + PNG per participant.
- **Auto-generated template** — if `assets/template.png` is missing, the CLI
  paints a modern certificate border, header, and geometric accents with Pillow
  so the repo works out of the box.
- **High-error-correction QR codes** (`ERROR_CORRECT_H`) per certificate,
  pointing to `{BASE_VERIFY_URL}/?id={cert_id}`.
- **Tamper-evident hashing** — SHA-256 of `id + name + event + date`,
  truncated to 12 hex characters, stored in the public registry.
- **Flat O(1) lookup registry** — `docs/certificates.json` keyed by certificate
  ID, safe to publish (no raw CSV, no Python source exposed).
- **Static verification portal** (`docs/index.html`) — pure HTML/Tailwind
  (CDN) + vanilla JS, dark/light adaptive glassmorphic UI, works 100%
  client-side with zero backend.
- **Three URL states** — valid `?id=…` (verified card), invalid `?id=…` (red
  warning), and no parameter (search landing).

## Project Structure

```
cert-engine/
├── assets/                 # template.png (auto-generated on first run)
├── output/
│   ├── pdfs/               # per-certificate PDFs (@ 300 DPI)
│   └── pngs/               # per-certificate PNGs (@ 300 DPI)
├── docs/                   # GitHub Pages publish directory (/docs)
│   ├── index.html          # Verification portal
│   └── certificates.json   # Auto-generated O(1) registry
├── participants.csv        # Input data (id,name,event,role,date)
├── config.json             # Coordinates, colors, base URL, fonts
├── generate.py             # CLI pipeline
├── requirements.txt        # Python dependencies
└── README.md
```

## Quickstart (3 steps)

### 1. Install dependencies
```bash
cd cert-engine
pip install -r requirements.txt
```

### 2. Prepare your data
Edit `participants.csv` (columns: `id,name,event,role,date`) and tune
`config.json` (coordinates, font sizes, colors, `base_verify_url`).

### 3. Generate certificates
```bash
python generate.py
```
Outputs:
- `output/pdfs/{cert_id}.pdf` — print-ready PDF
- `output/pngs/{cert_id}.png` — print-ready PNG
- `docs/certificates.json` — public verification registry

CLI flags:
- `--csv` — input CSV path (default: `participants.csv`)
- `--config` — config path (default: `config.json`)
- `--base-url` — override `base_verify_url` from config

## Deploy on GitHub Pages (free)

1. Push this repository to GitHub (`https://github.com/AnanthaBhalan/cert`).
2. Go to **Settings → Pages → Build and deployment**.
3. **Source:** Deploy from a branch → branch: `main`, folder: `/docs` → **Save**.
4. Your portal is live at:
   `https://ananthabhalan.github.io/cert/?id=CERT-2026-0001`

Because the registry lives in `/docs`, GitHub Pages serves it directly and no
Python runtime, database, or backend is required.

## Verification URL States

| URL | State |
|-----|-------|
| `/` | Landing — search input to verify any certificate |
| `/?id=CERT-2026-0001` | Verified — credential card, copy link, copy hash |
| `/?id=FAKE-ID` | Invalid — red warning with retry input |

## License

MIT — free to use, modify, and deploy.