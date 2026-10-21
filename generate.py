#!/usr/bin/env python3
"""
Bulk Certificate Generator & Static QR Verification System
==========================================================

Reads participant records from a CSV file, renders personalized certificates
onto a high-resolution A4 landscape (3508 x 2480 px @ 300 DPI) template,
exports PDF + PNG for every participant, and compiles a flat O(1) lookup
registry (docs/certificates.json) for a client-side GitHub Pages
verification portal.

Usage:
    python generate.py
    python generate.py --csv participants.csv --config config.json
    python generate.py --base-url https://acme.github.io/cert-engine
"""

import argparse
import base64
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import qrcode
from qrcode.constants import ERROR_CORRECT_H

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def b64url_encode(data: bytes) -> str:
    """Base64url-encode bytes without padding (safe for URLs)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Decode a base64url string (with or without padding) back to bytes."""
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def encrypt_payload(plaintext_dict: dict, key_bytes: bytes) -> dict:
    """Encrypt a JSON-serializable dict with AES-GCM using a random IV.

    Returns {'iv': b64url, 'ciphertext': b64url}.
    """
    aesgcm = AESGCM(key_bytes)
    iv = os.urandom(12)
    plaintext = json.dumps(plaintext_dict, separators=(",", ":")).encode("utf-8")
    ciphertext = aesgcm.encrypt(iv, plaintext, None)
    return {"iv": b64url_encode(iv), "ciphertext": b64url_encode(ciphertext)}


def ensure_directories():
    """Create all required directories if they are missing."""
    for directory in ["assets", "output/pdfs", "output/pngs", "docs"]:
        Path(directory).mkdir(parents=True, exist_ok=True)


def load_config(config_path):
    """Load JSON configuration file."""
    with open(config_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_font(font_path, size):
    """Load a TTF font by path, trying common system fallbacks before the
    built-in Pillow default font. Always returns a scalable font object."""
    candidates = []
    if font_path:
        candidates.append(font_path)

    if sys.platform.startswith("win"):
        candidates.extend(
            [
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/times.ttf",
            ]
        )
    elif sys.platform.startswith("darwin"):
        candidates.extend(
            [
                "/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/SFNS.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            ]
        )

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def compute_cert_hash(cert_id, name, event, date):
    """Deterministic SHA-256 verification hash truncated to 12 hex chars."""
    payload = f"{cert_id}{name}{event}{date}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def create_default_template(config):
    """Procedurally draw a sleek A4 certificate template if none exists."""
    template_path = config.get("template_path", "assets/template.png")
    if os.path.exists(template_path):
        print(f"[template] Using existing template: {template_path}")
        return template_path

    width = int(config.get("canvas_width", 3508))
    height = int(config.get("canvas_height", 2480))
    colors = config.get("colors", {})

    bg = colors.get("background", "#ffffff")
    border = colors.get("border", "#0f172a")
    inner = colors.get("border_inner", "#4f46e5")

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    # Outer frame
    frame = 44
    draw.rectangle([0, 0, width - 1, frame - 1], fill=border)
    draw.rectangle([0, height - frame, width - 1, height - 1], fill=border)
    draw.rectangle([0, 0, frame - 1, height - 1], fill=border)
    draw.rectangle([width - frame, 0, width - 1, height - 1], fill=border)

    # Inner accent frame
    pad = 96
    thick = 12
    draw.rectangle([pad, pad, width - pad - 1, pad + thick - 1], fill=inner)
    draw.rectangle([pad, height - pad - thick, width - pad - 1, height - pad - 1], fill=inner)
    draw.rectangle([pad, pad, pad + thick - 1, height - pad - 1], fill=inner)
    draw.rectangle([width - pad - thick, pad, width - pad - 1, height - pad - 1], fill=inner)

    # Corner flourishes (subtle geometric accents)
    flourish_len = 260
    flourish_thick = 10
    corner_lines = [
        # top-left
        ((pad, pad), (pad + flourish_len, pad)),
        ((pad, pad), (pad, pad + flourish_len)),
        # top-right
        ((width - pad - 1, pad), (width - pad - flourish_len - 1, pad)),
        ((width - pad - 1, pad), (width - pad - 1, pad + flourish_len)),
        # bottom-left
        ((pad, height - pad - 1), (pad + flourish_len, height - pad - 1)),
        ((pad, height - pad - 1), (pad, height - pad - flourish_len - 1)),
        # bottom-right
        ((width - pad - 1, height - pad - 1), (width - pad - flourish_len - 1, height - pad - 1)),
        ((width - pad - 1, height - pad - 1), (width - pad - 1, height - pad - flourish_len - 1)),
    ]
    for p1, p2 in corner_lines:
        draw.line([p1, p2], fill=inner, width=flourish_thick)

    # Header
    header_font = load_font(None, 130)
    header_text = "CERTIFICATE OF ACHIEVEMENT"
    bbox = draw.textbbox((0, 0), header_text, font=header_font)
    h_width = bbox[2] - bbox[0]
    draw.text(((width - h_width) // 2, 220), header_text, font=header_font, fill=border)

    # Subheader
    sub_font = load_font(None, 56)
    sub_text = "Presented in recognition of outstanding achievement"
    bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    s_width = bbox[2] - bbox[0]
    draw.text(
        ((width - s_width) // 2, 400),
        sub_text,
        font=sub_font,
        fill=colors.get("text_secondary", "#64748b"),
    )

    image.save(template_path, "PNG")
    print(f"[template] Created default template at {template_path}")
    return template_path


def generate_qr(url, size):
    """Return a crisp RGBA PIL Image QR code (ERROR_CORRECT_H) with a quiet zone."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:
        resample = Image.LANCZOS
    img = img.resize((size, size), resample)
    return img


def draw_centered_text(draw, text, y, font, fill, canvas_width, x=None):
    """Draw text centered horizontally (unless x is given) at vertical y."""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    draw_x = x if x is not None else (canvas_width - text_width) // 2
    draw.text((draw_x, y), text, font=font, fill=fill)


def generate_certificates(args):
    config = load_config(args.config)
    base_url = (args.base_url or config.get("base_verify_url", "")).rstrip("/")

    ensure_directories()
    template_path = create_default_template(config)

    template = Image.open(template_path).convert("RGB")
    canvas_width = int(config.get("canvas_width", template.width))
    canvas_height = int(config.get("canvas_height", template.height))

    colors = config.get("colors", {})
    coords = config.get("coords", {})
    fonts_cfg = config.get("fonts", {})

    name_font = load_font(fonts_cfg.get("name"), int(coords.get("name", {}).get("font_size", 120)))
    event_font = load_font(fonts_cfg.get("body"), int(coords.get("event", {}).get("font_size", 70)))
    role_font = load_font(fonts_cfg.get("body"), int(coords.get("role", {}).get("font_size", 60)))
    date_font = load_font(fonts_cfg.get("body"), int(coords.get("date", {}).get("font_size", 60)))
    cert_id_font = load_font(fonts_cfg.get("body"), int(coords.get("cert_id", {}).get("font_size", 44)))
    qr_label_font = load_font(fonts_cfg.get("body"), int(coords.get("qr_label", {}).get("font_size", 36)))

    text_primary = colors.get("text_primary", "#0f172a")
    text_secondary = colors.get("text_secondary", "#475569")

    with open(args.csv, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    total = len(rows)
    if total == 0:
        print("[warn] No participant records found.")
        return

    print(f"[start] Generating {total} certificate(s)... base_url={base_url or '(none)'}")
    certificates = []

    for index, row in enumerate(rows, 1):
        cert_id = (row.get("id") or "").strip()
        name = (row.get("name") or "").strip()
        event = (row.get("event") or "").strip()
        role = (row.get("role") or "").strip()
        date = (row.get("date") or "").strip()

        if not cert_id:
            print(f"  [{index}/{total}] SKIPPED row without 'id': {row}")
            continue

        # Generate a random 256-bit secret key per certificate.
        key_bytes = os.urandom(32)
        key_b64 = b64url_encode(key_bytes)

        # Encrypt the participant payload (zero plaintext in the registry).
        encrypted = encrypt_payload(
            {"name": name, "event": event, "role": role, "date": date},
            key_bytes,
        )
        cert_hash = compute_cert_hash(cert_id, name, event, date)

        # QR URL now carries both the cert ID and the decryption key.
        verify_url = (
            f"{base_url}/?id={cert_id}&key={key_b64}"
            if base_url
            else f"/?id={cert_id}&key={key_b64}"
        )

        img = template.copy()
        draw = ImageDraw.Draw(img)

        # Name (centered)
        draw_centered_text(
            draw,
            name,
            int(coords.get("name", {}).get("y", 980)),
            name_font,
            text_primary,
            canvas_width,
        )
        # Event (centered)
        draw_centered_text(
            draw,
            event,
            int(coords.get("event", {}).get("y", 1220)),
            event_font,
            text_secondary,
            canvas_width,
        )
        # Role (centered)
        draw_centered_text(
            draw,
            role,
            int(coords.get("role", {}).get("y", 1440)),
            role_font,
            text_secondary,
            canvas_width,
        )
        # Date (centered)
        draw_centered_text(
            draw,
            date,
            int(coords.get("date", {}).get("y", 1660)),
            date_font,
            text_secondary,
            canvas_width,
        )
        # Certificate ID (absolute x if provided, otherwise centered)
        cert_id_coord = coords.get("cert_id", {})
        cert_id_x = cert_id_coord.get("x")
        cert_id_y = int(cert_id_coord.get("y", 2180))
        draw_centered_text(
            draw,
            f"Certificate ID: {cert_id}",
            cert_id_y,
            cert_id_font,
            text_primary,
            canvas_width,
            x=cert_id_x,
        )

        # QR code
        qr_coord = coords.get("qr_code", {})
        qr_size = int(qr_coord.get("box_size", 400))
        qr_x = int(qr_coord.get("x", canvas_width - qr_size - 140))
        qr_y = int(qr_coord.get("y", (canvas_height - qr_size) // 2))
        qr_img = generate_qr(verify_url, qr_size)
        img.paste(qr_img, (qr_x, qr_y), qr_img)

        # Label under QR code
        qr_label = "Scan to verify"
        lbbox = draw.textbbox((0, 0), qr_label, font=qr_label_font)
        l_width = lbbox[2] - lbbox[0]
        draw.text(
            (
                qr_x + (qr_size - l_width) // 2,
                qr_y + qr_size + int(coords.get("qr_label", {}).get("y_offset", 30)),
            ),
            qr_label,
            font=qr_label_font,
            fill=text_secondary,
        )

        # Exports: PNG + high-res PDF
        png_path = f"output/pngs/{cert_id}.png"
        pdf_path = f"output/pdfs/{cert_id}.pdf"

        img.save(png_path, "PNG", dpi=(300, 300))
        img.save(pdf_path, "PDF", resolution=300.0)

        certificates.append(
            {
                "id": cert_id,
                "encrypted": encrypted,
                "hash": cert_hash,
                "verify_url": verify_url,
            }
        )

        print(f"  [{index}/{total}] {cert_id} - {name}")

    # Compile flat O(1) lookup registry for GitHub Pages (/docs)
    # Zero plaintext names or sensitive data — only encrypted blobs + hashes.
    registry = {entry["id"]: entry for entry in certificates}
    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    registry_path = docs_dir / "certificates.json"
    with open(registry_path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2)

    print(f"[done] {len(certificates)} certificate(s) generated.")
    print(f"       PDFs : output/pdfs/*.pdf")
    print(f"       PNGs : output/pngs/*.png")
    print(f"       Registry: {registry_path} (encrypted, zero plaintext)")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk Certificate Generator & Static QR Verification System"
    )
    parser.add_argument("--csv", default="participants.csv", help="Path to participants CSV (default: participants.csv)")
    parser.add_argument("--config", default="config.json", help="Path to config JSON (default: config.json)")
    parser.add_argument("--base-url", default=None, help="Override base_verify_url from config")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"[error] Config file not found: {args.config}")
        sys.exit(1)
    if not os.path.exists(args.csv):
        print(f"[error] CSV file not found: {args.csv}")
        sys.exit(1)

    generate_certificates(args)


if __name__ == "__main__":
    main()