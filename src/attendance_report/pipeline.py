"""The whole pipeline for one file. Each stage knows only its input and output.

    PDF --extract--> RawDocument --classify--> ReportType
        --parse--> AttendanceReport --transform--> AttendanceReport (new)
        --render--> new PDF / HTML      (the input file is only ever read)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .domain.models import AttendanceReport
from .generation.base_renderer import BaseRenderer
from .parsing.classifier import classify
from .parsing.extraction import ExtractionMode, extract
from .parsing.factory import get_parser
from .transformation.service import TransformationService

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    source: AttendanceReport
    variant: AttendanceReport
    outputs: tuple[Path, ...]
    source_issues: tuple[str, ...]   # invariants the *input* already breaks (informational)


def read_report(pdf_path: Path, mode: ExtractionMode = ExtractionMode.AUTO) -> AttendanceReport:
    raw = extract(pdf_path, mode)
    report_type = classify(raw.text)
    log.info("%s: detected %s (%s)", pdf_path.name, report_type.value, raw.method)
    return get_parser(report_type).parse(raw)


def run(pdf_path: Path, out_dir: Path, renderers: list[BaseRenderer], seed: int | str = 42,
        mode: ExtractionMode = ExtractionMode.AUTO,
        service: TransformationService | None = None) -> PipelineResult:
    service = service or TransformationService()
    source = read_report(pdf_path, mode)
    issues = tuple(service.check(source))
    if issues:
        log.info("%s: the source itself breaks %d rule(s), e.g. %s",
                 pdf_path.name, len(issues), issues[0])
    variant = service.transform(source, seed)
    target = out_dir / f"{pdf_path.stem}_variant"
    outputs = tuple(r.render(variant, target) for r in renderers)
    return PipelineResult(source, variant, outputs, issues)
