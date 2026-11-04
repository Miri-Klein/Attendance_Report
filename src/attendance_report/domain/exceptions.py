"""All error types of the project, in one place.

Two families, on purpose:

* ``AttendanceReportError`` - something is wrong with the *input report*
  (unreadable file, unknown type, missing hourly rate...). Expected: the CLI
  prints a one-line message and moves on to the next file.
* ``InternalError`` - the program itself broke a rule it promises to keep
  (e.g. a generated variation fails an invariant). That is a bug in our code,
  never the input's fault; the CLI reports it differently.

One class per station, so a caller can catch exactly the stage it cares about.
"""
from __future__ import annotations


class AttendanceReportError(Exception):
    """Base for every problem caused by the input report."""


# station 1 - reading the PDF
class ExtractionError(AttendanceReportError):
    """The PDF could not be read (no pages, no text, OCR not available...)."""


# station 2 - classification
class UnknownReportType(AttendanceReportError):
    """The text matches no known report type well enough."""


# station 3 - parsing
class ParseError(AttendanceReportError):
    """The report type is known, but its table could not be read."""


# station 4 - transformation
class TransformationError(AttendanceReportError):
    """The report was read, but a variation cannot be produced from it."""


class EmptyReportError(TransformationError):
    """There are no worked days to vary."""


class MissingRateError(TransformationError):
    """Type B: the hourly rate was not read, so pay cannot be recomputed."""


# bugs
class InternalError(Exception):
    """A bug in this program (deliberately NOT an AttendanceReportError)."""


class InvariantViolation(InternalError):
    """A generated variation breaks one of the rules in domain/validation.py."""
