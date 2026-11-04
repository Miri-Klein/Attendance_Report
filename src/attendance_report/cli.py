"""Command line: attendance-report INPUT.pdf [...] -o OUT_DIR [--seed N]"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from pathlib import Path

from .domain.exceptions import AttendanceReportError
from .generation.html_renderer import HtmlRenderer
from .generation.pdf_renderer import PdfRenderer
from .parsing.extraction import ExtractionMode
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="attendance-report",
                                description="Generate a valid variation of an attendance report PDF.")
    p.add_argument("inputs", nargs="+", type=Path, help="input PDF file(s)")
    p.add_argument("-o", "--output", type=Path, default=Path("output"), help="output folder")
    p.add_argument("--seed", default="42", help="same seed + same input = same output (default 42)")
    p.add_argument("--extract", choices=[m.value for m in ExtractionMode], default="auto",
                   help="auto: text layer if present, else OCR (default)")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--pdf-only", action="store_true")
    fmt.add_argument("--html-only", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    renderers = ([] if args.html_only else [PdfRenderer()]) + ([] if args.pdf_only else [HtmlRenderer()])

    failures = bugs = 0
    for path in args.inputs:
        try:
            result = run(path, args.output, renderers, args.seed, ExtractionMode(args.extract))
        except AttendanceReportError as exc:     # a problem in this input file: say so, go on
            failures += 1
            print(f"✗ {path.name}: {exc}", file=sys.stderr)
            continue
        except Exception as exc:                 # a bug in this program: say so clearly
            bugs += 1
            print(f"✗ {path.name}: INTERNAL ERROR (a bug, not a problem with the file): "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            continue
        print(f"✓ {path.name}: {result.variant.report_type.value}, "
              f"{len(result.variant.rows)} rows -> " + ", ".join(str(o) for o in result.outputs))
        if result.source_issues:
            print(f"  note: the input itself breaks {len(result.source_issues)} rule(s), "
                  f"e.g. {result.source_issues[0]}")
    # exit codes: 0 all good, 1 some input files could not be processed, 2 a bug
    return 2 if bugs else 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
