# Offline Deployment Bundle

Build the offline bundle on an internet-connected machine that matches the target
deployment platform as closely as possible.

```bash
python scripts/build_offline_bundle.py --chunk-mb 95 --easyocr-languages en
```

The builder creates:

- `offline/bundle/payload/` with wheels and local Docling/EasyOCR model assets.
- `offline/bundle/chat-with-contracts-offline.tar` as the full archive.
- `offline/bundle/chunks/*.part*`, each smaller than the configured chunk size.
- `offline/bundle/manifest.json` with SHA256 checksums.

For GitHub, commit `offline/bundle/manifest.json` and
`offline/bundle/chunks/*.part*`. Do not commit the raw payload or full tar archive.

On the offline target:

```bash
python scripts/install_offline_bundle.py
```

The installer reassembles and verifies the chunks, installs backend Python
packages from the local wheelhouse, copies Docling/EasyOCR model assets into
`backend/.data/offline-assets/`, and writes the local model paths into
`backend/.env`.

Runtime document extraction is intentionally offline-only:

- Docling uses the configured `DOCLING_ARTIFACTS_PATH`.
- EasyOCR uses `EASYOCR_MODEL_DIR` and runs with `download_enabled=False`.
- Missing models fail visibly during extraction instead of trying to download
  during a chat session.
