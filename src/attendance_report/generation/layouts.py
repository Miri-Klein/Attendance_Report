"""Page geometry of each report type, as *data*.

All numbers were measured on the real scans (300 dpi render, converted to PDF
points, y measured from the top of the page): table lines and column
separators with OpenCV, text positions from the OCR word boxes. The renderers
are generic and only draw what is described here, so they split by output
format, not by report type. A new report type = a new PageLayout.

Text positions are *baselines*.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..domain.models import ReportType


@dataclass(frozen=True)
class ColumnLayout:
    key: str
    header: str                  # "\n" = two-line header
    x0: float                    # cell borders
    x1: float
    align: str = "right"        # "right" | "center"
    pad: float = 3.0             # distance from the right border when right-aligned


@dataclass(frozen=True)
class TableLayout:
    columns: tuple[ColumnLayout, ...]
    top: float                   # y of the line above the column titles
    header_height: float
    header_baselines: tuple[float, ...]   # 1 or 2 title lines
    row_height: float
    row_baseline: float          # baseline offset inside a row
    font_size: float
    header_bold: bool
    body_bold: bool
    full_grid: bool              # True: border around every cell (B). False: only the title rule (A)
    line_width: float
    shade_shabbat: tuple[str, ...] = ()   # column keys shaded on Shabbat rows
    shade_header: tuple[str, ...] = ()    # column title cells shaded
    summary_row: bool = False
    date_style: str = "dd/mm/yyyy"       # or "d/m/yy"
    time_style: str = "HH:MM"            # or "H:MM"
    weekday_style: str = "long"          # "long" = יום ראשון, "short" = ראשון

    @property
    def x0(self) -> float:
        return min(c.x0 for c in self.columns)

    @property
    def x1(self) -> float:
        return max(c.x1 for c in self.columns)


@dataclass(frozen=True)
class BoxRow:
    label: str
    key: str | None              # value field, None = no value (empty row)
    split: bool = True           # False = one cell over the whole width
    style: str = "compact"       # number style: plain | int | compact | hours2 | money


@dataclass(frozen=True)
class KeyValueBox:
    """A small bordered table of "label | value" rows (label on the right)."""
    x0: float
    divider: float
    x1: float
    top: float                   # absolute y, or gap below the table if after_table
    row_height: float
    rows: tuple[BoxRow, ...]
    font_size: float
    bold: bool
    line_width: float
    baseline: float              # baseline offset inside a row
    label_align: str = "right"
    value_align: str = "right"
    shade_label: bool = False
    shade_value: bool = False
    after_table: bool = False


@dataclass(frozen=True)
class TextLine:
    key: str                     # "header:0" = first source header line, or a fixed text
    right: float
    baseline: float
    size: float
    bold: bool = False


@dataclass(frozen=True)
class Redaction:
    """Where the source shows a blacked-out name; drawn when the name is unknown."""
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class PageLayout:
    texts: tuple[TextLine, ...]
    table: TableLayout
    boxes: tuple[KeyValueBox, ...]
    redaction: Redaction | None
    shade_gray: float = 0.6


A_COLS = (
    ColumnLayout("date", "תאריך", 471.0, 529.7),
    ColumnLayout("weekday", "יום", 419.0, 471.0),
    ColumnLayout("location", "מקום ע.", 380.4, 419.0),
    ColumnLayout("entry", "כניסה", 346.6, 380.4),
    ColumnLayout("exit", "יציאה", 314.6, 346.6),
    ColumnLayout("break", "הפסקה", 273.6, 314.6),
    ColumnLayout("total", 'סה"כ', 236.8, 273.6),
    ColumnLayout("h100", "100%", 199.0, 236.8),
    ColumnLayout("h125", "125%", 161.0, 199.0),
    ColumnLayout("h150", "150%", 123.4, 161.0),
    ColumnLayout("shabbat", "שבת", 91.2, 123.4),
)

TYPE_A_LAYOUT = PageLayout(
    texts=(TextLine("header:0", 526.6, 84.3, 12, bold=True),),
    redaction=Redaction(394.8, 88.8, 531.6, 101.0),
    table=TableLayout(
        columns=A_COLS, top=101.5, header_height=13.0, header_baselines=(112.3,),
        row_height=12.93, row_baseline=125.0 - 114.5, font_size=10.2,
        header_bold=True, body_bold=False, full_grid=False, line_width=1.0,
        shade_shabbat=("weekday",), shade_header=("weekday",), summary_row=True,
    ),
    boxes=(KeyValueBox(
        x0=418.1, divider=470.9, x1=529.2, top=1.9, after_table=True, row_height=12.875,
        # trailing zeros dropped: 143.00 -> '143', 110.50 -> '110.5' (both scans)
        rows=(BoxRow("ימים", "days", style="plain"), BoxRow('סה"כ שעות', "total"),
              BoxRow("שעות 100%", "h100"), BoxRow("שעות 125%", "h125"),
              BoxRow("שעות 150%", "h150"), BoxRow("שבת 150%", "shabbat"),
              BoxRow("בונוס", "bonus"), BoxRow("נסיעות", "travel")),
        font_size=10.2, bold=False, line_width=1.0, baseline=10.0,
    ),),
)

B_COLS = (
    ColumnLayout("date", "\nתאריך", 380.9, 431.3, pad=10.0),
    ColumnLayout("weekday", "יום\nבשבוע", 330.0, 380.9, pad=13.5),
    ColumnLayout("entry", "שעת\nכניסה", 279.4, 330.0, align="center"),
    ColumnLayout("exit", "\nשעת יציאה", 222.0, 279.4, align="center"),
    ColumnLayout("total", 'סה"כ\nשעות', 170.4, 222.0, align="center"),
    ColumnLayout("note", "הערות", 119.0, 170.4, pad=2.0),   # right-aligned, long notes spill left
)

TYPE_B_LAYOUT = PageLayout(
    texts=(),
    redaction=Redaction(258.0, 139.6, 313.2, 150.6),
    table=TableLayout(
        columns=B_COLS, top=259.0, header_height=26.1, header_baselines=(268.5, 281.5),
        row_height=12.85, row_baseline=10.5, font_size=10,
        header_bold=False, body_bold=True, full_grid=True, line_width=0.9,
        shade_shabbat=("date", "weekday", "entry", "exit", "total"),
        date_style="d/m/yy", time_style="H:MM", weekday_style="short",
    ),
    boxes=(
        KeyValueBox(x0=225.1, divider=333.6, x1=385.2, top=138.7, row_height=13.2,
                    rows=(BoxRow("שם העובד:", "employee_name", style="plain"), BoxRow("", None, split=False)),
                    font_size=10, bold=True, line_width=1.1, baseline=10.0,
                    shade_label=True, shade_value=True),
        KeyValueBox(x0=222.7, divider=281.3, x1=434.4, top=165.1, row_height=13.6,
                    rows=(BoxRow('סה:"כ ימי עבודה לחודש', "days", style="plain"),
                          BoxRow('סה:"כ שעות חודשיות', "total", style="hours2"),
                          BoxRow("מחיר לשעה", "rate", style="money"),
                          BoxRow('סה"כ לתשלום', "pay", style="money")),
                    font_size=10, bold=True, line_width=1.1, baseline=10.3,
                    label_align="center", value_align="center"),
        KeyValueBox(x0=171.6, divider=280.1, x1=382.8, top=230.4, row_height=16.8,
                    rows=(BoxRow("כרטיס עובד לחודש:", "month_label", style="plain"),),
                    font_size=10, bold=True, line_width=1.1, baseline=12.0,
                    shade_label=True, shade_value=True),
    ),
)

LAYOUTS: dict[ReportType, PageLayout] = {
    ReportType.TYPE_A: TYPE_A_LAYOUT,
    ReportType.TYPE_B: TYPE_B_LAYOUT,
}
