"""Thin CLI: point it at input files (+ optional config), get JSON out.

Examples:
    candidate-transformer --csv data/samples/recruiter.csv \\
        --ats data/samples/ats.json --resume data/samples/resume_jane.pdf
    candidate-transformer --input data/samples/*.json --config data/configs/custom_compact.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG, ConfigError, load_config
from .pipeline import run_pipeline
from .projection import ProjectionError
from .sources import SOURCE_KEYS, sniff_source
from .validation import OutputValidationError

log = logging.getLogger("transformer")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="candidate-transformer",
        description="Merge messy multi-source candidate data into canonical profiles.",
    )
    # One repeatable flag per source type (explicit; always wins over sniffing).
    p.add_argument("--csv", action="append", metavar="FILE", help="recruiter CSV export")
    p.add_argument("--ats", action="append", metavar="FILE", help="ATS JSON blob")
    p.add_argument("--notes", action="append", metavar="FILE", help="recruiter notes (.txt)")
    p.add_argument("--github", action="append", metavar="FILE|URL|USER",
                   help="GitHub profile: URL (https://github.com/user), bare username, or cached JSON file")
    p.add_argument("--linkedin", action="append", metavar="FILE|URL",
                   help="LinkedIn profile: URL (https://linkedin.com/in/user) or cached JSON export")
    p.add_argument("--resume", action="append", metavar="FILE", help="resume .txt/.md/.pdf")
    # Type-agnostic input: detect by extension/content.
    p.add_argument("--input", action="append", metavar="FILE",
                   help="auto-detect source type from the file")
    p.add_argument("--config", metavar="FILE", help="runtime output config (default: full canonical)")
    p.add_argument("--out", metavar="FILE", help="write JSON here (default: stdout)")
    p.add_argument("-v", "--verbose", action="store_true", help="log info (skips, warnings) to stderr")
    return p


def _collect_sources(args: argparse.Namespace) -> list[tuple[str, str]]:
    """Turn parsed flags into an ordered list of (source_key, path)."""
    sources: list[tuple[str, str]] = []
    for key in SOURCE_KEYS:
        for path in getattr(args, key) or []:
            sources.append((key, path))
    for path in args.input or []:
        key = sniff_source(path)
        if key is None:
            log.warning("cannot detect source type for %s; skipping", path)
            continue
        sources.append((key, path))
    return sources


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        config = load_config(args.config) if args.config else DEFAULT_CONFIG
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    sources = _collect_sources(args)
    if not sources:
        print("error: no input sources (use --csv/--ats/--notes/--github/--resume or --input)",
              file=sys.stderr)
        return 2

    try:
        outputs = run_pipeline(sources, config=config)
    except (ProjectionError, OutputValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # indent=2 + stable internal ordering -> human-diffable, byte-stable output.
    text = json.dumps(outputs, indent=2, ensure_ascii=False)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {len(outputs)} profile(s) to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
