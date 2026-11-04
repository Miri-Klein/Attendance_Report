"""The error families and how the CLI reports them (always run)."""
import pytest

from attendance_report import cli
from attendance_report.domain import exceptions as ex

from conftest import SYNTHETIC


def test_every_input_error_shares_one_base():
    for cls in (ex.ExtractionError, ex.UnknownReportType, ex.ParseError,
                ex.EmptyReportError, ex.MissingRateError):
        assert issubclass(cls, ex.AttendanceReportError)


def test_a_bug_is_not_an_input_error():
    assert issubclass(ex.InvariantViolation, ex.InternalError)
    assert not issubclass(ex.InvariantViolation, ex.AttendanceReportError)


def test_cli_ok(tmp_path, capsys):
    code = cli.main([str(SYNTHETIC / "type_a_synthetic.pdf"), "-o", str(tmp_path)])
    assert code == 0
    assert "✓ type_a_synthetic.pdf: TYPE_A" in capsys.readouterr().out


def test_cli_bad_input_file_exit_1_and_continues(tmp_path, capsys):
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf")
    code = cli.main([str(bad), str(SYNTHETIC / "type_b_synthetic.pdf"), "-o", str(tmp_path)])
    out = capsys.readouterr()
    assert code == 1
    assert "✗ bad.pdf: bad.pdf: not a readable PDF" in out.err
    assert "✓ type_b_synthetic.pdf" in out.out              # the next file was still processed


def test_cli_bug_exit_2(tmp_path, capsys, monkeypatch):
    def broken(*args, **kwargs):
        raise ZeroDivisionError("oops")
    monkeypatch.setattr(cli, "run", broken)
    code = cli.main([str(SYNTHETIC / "type_a_synthetic.pdf"), "-o", str(tmp_path)])
    assert code == 2
    assert "INTERNAL ERROR (a bug, not a problem with the file)" in capsys.readouterr().err


@pytest.mark.parametrize("cls", [ex.ParseError, ex.UnknownReportType])
def test_input_errors_carry_their_message(cls):
    assert str(cls("table header not found")) == "table header not found"
