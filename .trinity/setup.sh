#!/bin/bash
# Trinity persistent setup - runs on every container start (base image convention).
# Clones or refreshes the agency's canon into canon/. Idempotent, fast, never blocks startup.
# To use your own canon: change CANON_REPO (a public repo needs no token; for a private one the
# platform's GitHub token is passed on the command line and never written to disk).
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANON_REPO="${CANON_REPO:-https://github.com/Abilityai/keymaker-canon.git}"
CANON_DIR="$AGENT_DIR/canon"

if [ -d "$CANON_DIR/.git" ]; then
  git -C "$CANON_DIR" pull --ff-only --quiet 2>/dev/null \
    && echo "canon: refreshed at $(git -C "$CANON_DIR" rev-parse --short HEAD)" \
    || echo "canon: pull failed - reading the copy at $(git -C "$CANON_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
else
  if git clone --depth 1 --quiet "$CANON_REPO" "$CANON_DIR" 2>/dev/null; then
    echo "canon: cloned at $(git -C "$CANON_DIR" rev-parse --short HEAD)"
  else
    echo "canon: CLONE FAILED from $CANON_REPO - this desk falls back to its sample operators.yaml and pricing.md and must say so"
  fi
fi
mkdir -p "$AGENT_DIR/drafts" "$AGENT_DIR/invoices"
