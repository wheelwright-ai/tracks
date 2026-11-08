#!/usr/bin/env python3
"""lug: the same program as backlog.py (kit part P-019), under the name the wheel uses for its work items.
  lug.py add ... | link ... | claim ... | initiative add ... | roadmap | lint | verify   (see lug.py --help)"""
import os, runpy, sys

sys.dont_write_bytecode = True
mod = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backlog.py"))
sys.exit(mod["main"](sys.argv[1:], prog="lug.py"))
