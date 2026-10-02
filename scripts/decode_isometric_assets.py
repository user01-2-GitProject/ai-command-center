#!/usr/bin/env python3
"""Losslessly repair base64-text PNG placeholders; never generate new artwork.

Run from a checkout. Already-decoded PNGs are left alone. Record source/destination
hashes, dimensions and byte counts; reject any non-PNG decoded payload.
"""
import base64
import hashlib
import json
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]
records = []
for name in ('iggy-iso.png', 'iggy-robot-iso.png'):
    target = ROOT / 'app/ui/assets' / name
    before = target.read_bytes()
    if before.startswith(b'\x89PNG\r\n\x1a\n'):
        print(name, 'already PNG; unchanged')
        continue
    decoded = base64.b64decode(b''.join(before.split()), validate=True)
    if decoded[:8] != b'\x89PNG\r\n\x1a\n' or decoded[12:16] != b'IHDR':
        raise ValueError('Decoded payload is not a PNG')
    width, height = struct.unpack('>II', decoded[16:24])
    if not 0 < width <= 4096 or not 0 < height <= 4096:
        raise ValueError('Image dimensions outside bounded display-art budget')
    target.write_bytes(decoded)
    records.append({'path':str(target.relative_to(ROOT)),
                    'source_encoding':'base64 PNG text; decoded verbatim, no image editing',
                    'before_sha256':hashlib.sha256(before).hexdigest(),
                    'after_sha256':hashlib.sha256(decoded).hexdigest(),
                    'before_bytes':len(before),'after_bytes':len(decoded),
                    'width':width,'height':height})
if records:
    receipt = ROOT / 'docs/verification/live-session-bridge/asset-decoding.json'
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(records,indent=2))
