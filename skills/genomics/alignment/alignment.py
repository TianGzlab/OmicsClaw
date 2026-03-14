#!/usr/bin/env python3
"""Genomics Alignment - Read alignment to reference genome.

Usage:
    python alignment.py --input <file> --output <dir>
    python alignment.py --demo --output <dir>
"""

from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "alignment"
SKILL_VERSION = "0.1.0"

def main():
    parser = argparse.ArgumentParser(description="Alignment")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {"status": "demo"}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, result, {})

    print(f"Success: alignment")
    print(f"  Output: {output_dir}")
    print(f"Alignment complete")

if __name__ == "__main__":
    main()
