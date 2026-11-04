# Decision Log

🇬🇧 **English** · 🇮🇱 [עברית](DECISIONS.he.md)

For every decision: the options, the choice, and why.

## Data and model

| Decision | Options | Chosen | Why |
|---|---|---|---|
| How to store hours | string `"08:00"` / `datetime.time` / number of minutes | `time` for clock times, `int` minutes for durations (break), `Decimal` for printed hours (6.50) | Parse once, format once. `Decimal`, not `float`, so sums come out exact |
| Changing objects | plain dataclass / `frozen` | `frozen` | The transformation must build a new object, so the source cannot be damaged by mistake. There is a test for it |
| Fields that exist in only one type | two row classes / one class with defaults | One class: `break_minutes`, `location`, `buckets` (A) and `note` (B). In the summary: `bonus`, `travel` (A) and `hourly_rate`, `total_pay` (B) | The rest of the code works on a single type |
| Days without work in type B | skip / keep | Keep as a row without hours | They are part of type B's structure (every day of the month is printed) |
| Day of the week | store the text / derive from the date | Derive from the date when printing | This way they can never contradict each other. During parsing, the printed text is only used to check, and to repair a date that OCR garbled |

## OCR

| Decision | Options | Chosen | Why |
|---|---|---|---|
| Resolution | 150 dpi like the scan / 300 | 300 | The scans are 150 dpi JPEGs. Upscaled, Tesseract gets larger glyphs and reads better |
| Language | `heb` / `heb+eng` | `heb+eng` | Tested: `heb` alone garbled almost every number |
| Page segmentation mode (psm) | psm 4 / 6 / 11; one for everything or per page | Decided by what the page looks like: a page with a full grid gets psm 4, any other page psm 11 | Tested on all four scans. On the Feb 2023 type A scan, psm 4 read 13 of 15 dates as `3`, while psm 11 read all of them. But psm 11 broke the type B pay box (hourly rate read as `5`). The choice depends on the page, not on the report type, so the OCR doesn't need to know the type. psm 11 loses Tesseract's own line grouping, which is fine because the parsers work from word positions |
| A second look at suspicious words | accept the result / fix later in the parser / read the word again on its own | Read again: a word in Latin letters with the Hebrew model only; a number in a box far too wide for it with the English model only | The combined model is good at digits but sometimes turns Hebrew into Latin letters (`כח אדם` → `ND DTN`, `שבת` → `naw`) and swallows numbers next to Hebrew and ₪ (`45.50` → `0`). Reading the word alone with the right model fixed every case. In an all-Hebrew report, a Latin word is always a mistake |
| Table lines | keep / always erase / erase only on a full-grid table | Erase only when at least 5 long vertical lines are detected (B: 7, A: 3) | In B the lines touch the digits, and OCR read whole rows as garbage. In A, erasing "ate" parts of the digits. The detection is automatic, so the OCR station doesn't need to know the report type |
| OCR each cell separately | crop each grid cell / whole page | Whole page | Tested: per cell was slower (20 seconds) and worse, because empty cells produced noise like `So` and `--%` |
| Confidence | ignore / keep per word | Keep (`conf`) | Used to break ties between two equally good repairs, and to filter noise in notes and in the name |
| How many pages | first page / refuse long files / all pages | All pages. Every word remembers its page number, and lines are only built within a page | Reading only the first page silently loses rows. At first the code refused long files; now it reads them |

## Parsing and repairing OCR errors

The principle: the report contains redundant information, and that is what the repairs use. Every repair is reported as a warning, never hidden.

| Decision | Options | Chosen | Why |
|---|---|---|---|
| Assigning a value to a column | by word order / by horizontal position | Position: each word goes to the column whose header centre is closest | In type A's totals row there are no values under entry and exit. Reading in order would shift every value by one column |
| A column title OCR didn't read | fail / estimate | Estimate from the neighbours (the order is known). It's enough that half the titles were recognised | In practice: `שבת` was read as `naw`, `כניסה` as `non` |
| Matching a title | fuzzy only / exact first, then fuzzy | Exact first | `שעות` (total hours) is 86% similar to `שעת` (entry time), which is a different column |
| Two-line titles (B) | one line / a two-line window | A two-line window, only if both lines contain titles | Otherwise the company-name line in A got "swallowed" into the header |
| Entry/exit/total that don't agree | trust / repair | exit − entry − break must equal the total. If not, repair the value that needs the fewest digit changes, among repairs that give a plausible row. On a tie, the value OCR was least confident about | In the type B scan: `3:02` for `8:02` (twice), `41:01` for `11:01`, `8:04` for `8:01`, `11:04` for `11:01`, and `8:02` read as two words. All repaired correctly |
| A broken date in type B | drop / repair by weekday / by position | By position: every day of the month is printed at a fixed height, so a straight line is fitted between height and day on the dates that were read well, and every line is placed by it. **Per page**, since each page has its own margins. A page with a single readable date borrows the line spacing of another page. A page with no readable date at all is a clear error, not a guess | 10 dates were garbled in the scan (`5/1123`, `13`, `29/14/23` and more). All placed correctly |
| A short month in type B | stop at the month's end / keep the following lines | Keep: the printed card always has 31 lines, so lines up to 31 belong to the table, even from the next month. A rule makes sure no **worked** day falls outside the month | September 2022 ends with a shaded `1/10/22` line. OCR read it as `225%`, so it can't confirm its own date. The position is enough |
| A value in a summary box | use the table's cleaning rules / strip `\|` at the edge | Strip a `\|` at the edge of a box value | In a box the value touches the border, and OCR glues it on as `\|0`. In the table a `\|` may be a misread 1 (`\|5:00`), so the general cleaning turns it into 1, but at the edge of a box value it is always the border. Without this, `\|0` became `10` |
| A name glued to its label | look for the label as a separate word / split at `:` | Split: `העובד:ישראל` → label + `ישראל` | When reading the output back, the label and the name came out as one word. A scan can do the same |
| A broken date in type A | by position / by weekday | The next date after the previous row that matches the printed weekday | Type A lists only work days, so position doesn't tell which day it is |
| A broken total in type A | trust / cross-check | The total is printed twice (the total column and the sum of the rate columns). If one copy is implausible, take the other | |
| An unreadable location | keep / replace | Replace with the most frequent value in the document, with a warning | `גליליון` was read as `jr"`. Locations are a short list of sites |
| Monthly hours in B | trust / cross-check | hours × rate should be about the pay. If not, hours = pay ÷ rate | `63.02` was read as `2` |
| Employee name | whatever OCR read / filter | Only high-confidence Hebrew words. Otherwise the name is empty | In both scans the name is blacked out, and OCR produced noise from it |
| Type detection | one word / a set of signals | A set of signals per type; the type with the most signals wins; below 50% the page is rejected | One garbled word can't flip the decision |

## Transformation

| Decision | Options | Chosen | Why |
|---|---|---|---|
| Rules | one set / a set per type | A set per type, held inside the strategy | In A the hours are round (08:00) and a shift is 6.5 hours. In B they are clock punches (8:01) and a shift is about 3 hours. One rule would give B unbelievable round hours, or fail on a 3-hour daily minimum |
| Baseline for worked time | exit − entry / the printed total | The printed total; if missing, the computed value | The total carries the day-to-day variety |
| A holiday in type A | holiday calendar / infer from the source | Infer from the source: a weekday paid entirely at 150% stays that way | 17/10/2022 (Simchat Torah) was paid at 150%. No holiday calendar needed, and the employer's own decision is kept |
| Pay in type B | sum of rounded rows / sum of minutes | Sum of minutes, rounded once | Checked against the source: 3,781 minutes = 63.0167 hours. 63.0167 × 32.35 = 2,038.59, exactly as printed. With the rounded 63.02 it would be 2,038.70 |
| Totals in type A | sum of minutes / sum of rounded rows as printed | Sum of the rows as printed | This way, someone adding up the column on paper gets exactly the total |
| Randomness | global `random` / a seed per row | `Random(f"{seed}:{date}")` per row | Deterministic, and changing one row doesn't change the others |
| Splitting by type | `if type ==` / Strategy | Strategy, chosen once before the loop | Each type is tested on its own, and a fix in B doesn't touch A |
| When to check | only in tests / also at runtime | After every transformation. A violation stops that file | A violation is a bug in the rules, and it's better not to write a wrong file |
| Work days in type B | copy from the source / count from the rows | Count from the rows | The September 2022 card says 20 work days, but lists 24 days with hours (24 × 3.50 = 84.00, exactly the printed hours). The source itself is inconsistent; the output is consistent. The code reports it as a note |

## Errors

| Decision | Options | Chosen | Why |
|---|---|---|---|
| Where they are defined | in each station's file / one file | `domain/exceptions.py`: a base `AttendanceReportError` with one class per station (`ExtractionError`, `UnknownReportType`, `ParseError`, `EmptyReportError`, `MissingRateError`) | Anyone reading the code sees in one place what can go wrong. You can catch one station, or all of them at once |
| Bug vs. bad input | one `Exception` for everything / two families | `InternalError` (e.g. `InvariantViolation`) does **not** inherit from `AttendanceReportError` | The CLI tells them apart: a bad file gets ✗ and exit code 1, and the program moves on to the next file. A bug gets "INTERNAL ERROR" and exit code 2, with a traceback under `-v`. Before, everything was caught as one `Exception` |

## Tests

| Decision | Options | Chosen | Why |
|---|---|---|---|
| What to test on | the real scans / fixtures | **Synthetic** fixtures: two invented reports, drawn in the source layout, "scanned" (a 150 dpi JPEG image, like the scans) and run through real OCR once (`tools/build_fixtures.py`). The words and the true report are saved | The scans belong to another person, so their OCR output can't be in the repository either. Without fixtures, someone downloading the repository ran 16 tests and 178 were skipped. Now 205 run, even without Tesseract, in about a second |
| OCR errors in the fixtures | only what came out / add some on purpose | Add, on purpose, errors found in the real scans (`3:02`, `43:12`, a date read as `13`, location `jr"`). They are listed inside the JSON file | This way the repair code is tested for everyone too. The test requires rebuilding the invented report **exactly** |
| The real scans | delete those tests / skip when missing | Skip with an explanation. Whoever has them also runs the tests against every value read by eye | |

## Generation

| Decision | Options | Chosen | Why |
|---|---|---|---|
| How to produce a PDF "like the source" | the scan as a template: erase cells and write over them / build from scratch | Build from scratch in ReportLab, using measurements taken from the scans (`layouts.py`) | A template would keep the look of the scan (handwriting, blacked-out name), but generation would need the original image and the cell positions from OCR. That is exactly what the worksheet says to avoid: generation receives only the report object. Also, the output is clean and readable, and has a text layer |
| Measuring the layout | by eye / measurement | Lines and separators measured with OpenCV, text positions from the OCR boxes, font size from the date width (51.2 points for `02/10/2022` gives 10.2pt) | A test runs OCR on the output and checks that the titles are where they are in the scan |
| Hebrew in a PDF | ReportLab as is / bidi | `python-bidi` with an RTL base direction, then aligned drawing | ReportLab doesn't know RTL. The RTL base direction is needed for `32.35 ₪` to show as in the source |
| Font | Arial / Liberation Sans | Liberation Sans regular and bold, bundled with the project | Arial can't be freely redistributed. Liberation matches its metrics, supports Hebrew, and is OFL-licensed |
| A blacked-out name | leave empty / draw a black bar | Draw a black bar in place of the name when the name is unknown | This way the output looks like the source, and no name is invented |
| Rendering per type | a renderer per type / a renderer per format + layout as data | Per format (PDF, HTML). The layout, including date and time style and number formatting in the boxes, is data | One drawing code; a new type is just another layout definition |
| Verifying the output | by eye / reading it back | The parser reads the generated PDF and must get exactly the varied report | If the parser built for the source format can read the output, the structure is the same |

## Assumptions and known gaps

* **The real scans are not in the repository.** They are attendance reports of another person, so `samples/input/*.pdf` is in `.gitignore`. Instead, the repository has invented reports (`samples/synthetic/`) and fixtures.
* **The output is clean, not "scanned".** No handwriting in the margins, no scan noise, no slight tilt. Structure, positions, fonts and shading are as in the source.
* **Overtime rules** (8 hours at 100%, 2 at 125%) are a simplification for the exercise. No day in the real samples reaches them.
* **Bonus and travel in A** are not read by OCR (the box is cramped), so they are taken as 0 with a warning. In both scans they really are 0.
* **The output is always one page.** A longer report is read in full but drawn on one page. In all the samples, at most 31 lines fit on a page.
* **The scans are slightly shifted relative to each other** (the Sept 2022 B card is shifted right and up compared with the Jan 2023 one). The output is always drawn at the position measured on the first scan of each type.
