#!/bin/bash
# harness_mode.sh — v3/v4/v6 layout resolver, sourced by every hook.
#
# OPERATOR RULING 2026-08-14: there are no v4 spokes any more. Tooling EXPECTS v6 and,
# on meeting an older spoke, DETECTS and interrogates it rather than assuming a layout.
# Until 2026-08-14 this file computed HARNESS_V6, never branched on it and never exported
# it, so every hook on every v6 spoke in the estate resolved to v4
# (bug-harness-mode-resolver-computes-v6-then-discards-it-v1).
#
# The v4 upgrade is non-destructive: a spoke gains a WAI-Harness/ folder beside its
# legacy WAI-Spoke/. Both can be present at once. This resolver lets the SAME .claude
# hooks run v4 while TOLERATING v3 legacy files — so nothing breaks during the overlap
# window, and if something was missed in v4 we can still fall back to v3 to patch.
#
# Usage (in a hook):
#   source "$(dirname "$0")/harness_mode.sh" "$PROJECT_DIR"
#   [ "$HARNESS_ACTIVE" = "v4" ] && ...   # branch on the active harness
#
# Exports (never errors — pure detection, v3-safe):
#   HARNESS_V3      1 if a LEGACY WAI-Spoke/ (no kernel marker) present else 0
#   HARNESS_V4      1 if WAI-Harness/ present else 0
#   HARNESS_V6      1 if WAI-Spoke/installed.json (the kernel's marker) present else 0
#   HARNESS_MODE    v6 | coexist | v4-only | v3-only | none
#   HARNESS_ACTIVE  v6 | v4 | v3 | none   (which one this invocation drives)
#   HARNESS_ROOT    absolute path of the active harness root ("" if none)
#
# Active selection: an explicit WAI_HARNESS_MODE env override wins (this is how
# "which hub folder you run from" is expressed); otherwise v6 when its marker is
# present, else v4 when present, else v3 (the legacy path stays usable for patching).
#
# DATA PLANE NOTE for consumers: v6 is a CONTROL-plane distinction. The v6 kernel writes
# sessions/state to WAI-Harness/spoke/local — the SAME data plane as v4. A hook selecting
# a data directory must therefore treat v6 and v4 alike (`== v4 || == v6`); branching on
# `== v4` alone silently routes a v6 spoke into the legacy WAI-Spoke/ tree.

_hm_root="${1:-${PROJECT_DIR:-.}}"

HARNESS_V3=0; HARNESS_V4=0; HARNESS_V6=0
# v6 REUSES THE NAME `WAI-Spoke`, so directory presence alone no longer identifies v3.
# The kernel's marker is what separates them: v6 writes installed.json there, v3 never did.
# Without this a v6 spoke reads as coexist-with-a-phantom-v3-tree and the whole estate
# switches to legacy paths.
[ -f "$_hm_root/WAI-Spoke/installed.json" ] && HARNESS_V6=1
[ -d "$_hm_root/WAI-Spoke" ] && [ "$HARNESS_V6" = 0 ] && HARNESS_V3=1
[ -d "$_hm_root/WAI-Harness" ] && HARNESS_V4=1

if [ "$HARNESS_V6" = 1 ]; then HARNESS_MODE="v6"
elif [ "$HARNESS_V3" = 1 ] && [ "$HARNESS_V4" = 1 ]; then HARNESS_MODE="coexist"
elif [ "$HARNESS_V4" = 1 ]; then HARNESS_MODE="v4-only"
elif [ "$HARNESS_V3" = 1 ]; then HARNESS_MODE="v3-only"
else HARNESS_MODE="none"; fi

# active: explicit override first, else auto-resolution (v6 marker wins).
case "${WAI_HARNESS_MODE:-}" in
  v6) [ "$HARNESS_V6" = 1 ] && HARNESS_ACTIVE="v6" || HARNESS_ACTIVE="" ;;
  v4) [ "$HARNESS_V4" = 1 ] && HARNESS_ACTIVE="v4" || HARNESS_ACTIVE="" ;;
  v3) [ "$HARNESS_V3" = 1 ] && HARNESS_ACTIVE="v3" || HARNESS_ACTIVE="" ;;
  *)  HARNESS_ACTIVE="" ;;
esac
if [ -z "$HARNESS_ACTIVE" ]; then
  if [ "$HARNESS_V6" = 1 ]; then HARNESS_ACTIVE="v6"
  elif [ "$HARNESS_MODE" = "coexist" ]; then
    # Overlap-safe default: a coexist spoke (both trees present) stays v3 UNTIL it is
    # explicitly ACTIVATED (.activated marker or a migrated v4 local/WAI-State.json).
    # This stops a coexist spoke from silently flipping to v4 mid-overlap, while
    # already-cutover spokes (e.g. basher, which still has a lingering WAI-Spoke/ dir)
    # correctly stay v4 via their activation marker.
    if [ -e "$_hm_root/WAI-Harness/spoke/.activated" ] || [ -f "$_hm_root/WAI-Harness/spoke/local/WAI-State.json" ]; then
      HARNESS_ACTIVE="v4"
    else
      HARNESS_ACTIVE="v3"
    fi
  elif [ "$HARNESS_V4" = 1 ]; then HARNESS_ACTIVE="v4"
  elif [ "$HARNESS_V3" = 1 ]; then HARNESS_ACTIVE="v3"
  else HARNESS_ACTIVE="none"; fi
fi

case "$HARNESS_ACTIVE" in
  # v6's root is the KERNEL — the thing that actually runs. Fall back to WAI-Harness,
  # then to the kernel store itself, so a kernel-only spoke still resolves a root.
  v6) if   [ -d "$_hm_root/WAI-Harness/kernel" ]; then HARNESS_ROOT="$_hm_root/WAI-Harness/kernel"
      elif [ -d "$_hm_root/WAI-Harness" ];        then HARNESS_ROOT="$_hm_root/WAI-Harness"
      else HARNESS_ROOT="$_hm_root/WAI-Spoke"; fi ;;
  v4) HARNESS_ROOT="$_hm_root/WAI-Harness" ;;
  v3) HARNESS_ROOT="$_hm_root/WAI-Spoke" ;;
  *)  HARNESS_ROOT="" ;;
esac

export HARNESS_V3 HARNESS_V4 HARNESS_V6 HARNESS_MODE HARNESS_ACTIVE HARNESS_ROOT
