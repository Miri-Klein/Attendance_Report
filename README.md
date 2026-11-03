# מחולל וריאציות לדו"ח נוכחות

מקבל דו"ח נוכחות סרוק (PDF), מזהה את סוגו (A או B), קורא אותו ב-OCR, משנה את
שעות העבודה לפי כללים דטרמיניסטיים ששומרים על דו"ח הגיוני, ומפיק PDF חדש (וגם
HTML) באותו מבנה כמו המקור. קובץ המקור נקרא בלבד ואף פעם לא משתנה.

| | סוג A | סוג B |
|---|---|---|
| מה זה | דו"ח חברת כוח אדם ("נ.ע. הנשר") | כרטיס עובד חודשי |
| שורות | רק ימים שעבדו | כל ימי החודש (סופ"ש ריקים, שבת מוצללת) |
| עמודות | תאריך, יום, מקום, כניסה, יציאה, הפסקה, סה"כ, 100%, 125%, 150%, שבת | תאריך, יום בשבוע, שעת כניסה, שעת יציאה, סה"כ שעות, הערות |
| סיכומים | שורת סה"כ + תיבת סיכום מתחת לטבלה | תיבה מעל הטבלה: ימי עבודה, שעות, מחיר לשעה, סה"כ לתשלום |
| פורמט | `02/10/2022`, `08:00` | `1/1/23`, `8:01` |

## התקנה

דרוש Python 3.10 ומעלה.

```bash
pip install -e ".[dev]"
```

הקבצים סרוקים, ולכן צריך גם תוכנות מערכת ל-OCR:

| מערכת | פקודה |
|---|---|
| Ubuntu / Debian | `sudo apt install tesseract-ocr tesseract-ocr-heb poppler-utils` |
| macOS | `brew install tesseract tesseract-lang poppler` |
| Windows | להתקין Tesseract (כולל Hebrew) ו-Poppler, ולהוסיף את שניהם ל-PATH |

או בלי להתקין כלום על המחשב: Docker (בהמשך).

## הרצה

```bash
# קובץ אחד -> output/type_a_scan_variant.pdf + .html
attendance-report samples/input/type_a_scan.pdf -o output/

# שני הסוגים, רק PDF, seed אחר
attendance-report samples/input/*.pdf -o output/ --pdf-only --seed 7

# לוג מפורט: מה זוהה, אילו תיקוני OCR בוצעו
attendance-report samples/input/type_b_scan.pdf -v
```

אפשר גם בלי התקנה: `PYTHONPATH=src python -m attendance_report ...`

| אפשרות | משמעות |
|---|---|
| `-o DIR` | תיקיית פלט (ברירת מחדל `output`) |
| `--seed N` | אותו קובץ + אותו seed = אותו פלט בדיוק. seed אחר = וריאציה אחרת |
| `--extract auto/text/ocr` | auto: שכבת טקסט אם יש, אחרת OCR |
| `--pdf-only` / `--html-only` | פורמט פלט אחד בלבד |
| `-v` | לוג מפורט |

כל תיקון שבוצע בקריאת ה-OCR (תאריך שבור, `3:02` במקום `8:02` וכו') מודפס כאזהרה.

## בדיקות

```bash
pytest
```

194 בדיקות, כ-35 שניות (OCR על שתי הסריקות). בין השאר:

* **כל ערך בסוג B נבדק מול הסריקה**: 21 ימי עבודה, כניסה, יציאה וסה"כ. בנוסף, השכר שמחושב מהשעות שנקראו יוצא בדיוק ₪2,038.59 כמו שמודפס.
* כל האינווריאנטים נבדקים על 150 ערכי seed לכל סוג.
* קריאה חוזרת: הפרסר קורא את ה-PDF שנוצר ומקבל בדיוק את הדו"ח אחרי השינוי.
* השוואת מיקום: ה-PDF שנוצר עובר OCR כמו סריקה, והכותרות נמצאות באותו מקום כמו בסריקה.
* דטרמיניזם (שתי הרצות נותנות קבצים זהים בייט לבייט), והמקור לא משתנה.

בלי Tesseract הבדיקות שצריכות OCR מדולגות.

## Docker

```bash
docker build -t attendance-report .
docker run --rm -v "$(pwd)/samples/input:/in" -v "$(pwd)/output:/out" \
    attendance-report /in/type_a_scan.pdf -o /out
docker run --rm --entrypoint pytest attendance-report
```

ה-image כולל את Tesseract, חבילת העברית ו-Poppler.

## מבנה הקוד: צינור של שלבים

```
PDF ─OCR─> RawDocument ─classify─> TYPE_A/B ─parse─> AttendanceReport
    ─transform─> AttendanceReport חדש ─render─> PDF / HTML חדש
```

| שלב | נכנס | יוצא | קובץ |
|---|---|---|---|
| OCR / שכבת טקסט | PDF | מילים + מיקום + ביטחון (`RawDocument`) | `parsing/ocr.py`, `parsing/text_layer.py`, `parsing/extraction.py` |
| ניקוי | טוקן | ערך טיפוסי (time, date, Decimal) | `parsing/cleaning.py` |
| תיקון | כניסה/יציאה/סה"כ שנקראו | שורה עקבית | `parsing/repair.py` |
| זיהוי סוג | טקסט גולמי | `ReportType` | `parsing/classifier.py` |
| פרסור | `RawDocument` | `AttendanceReport` | `parsing/base_parser.py` + `type_a_parser.py`, `type_b_parser.py`, `factory.py` |
| **החוזה** | | | `domain/models.py`, `domain/validation.py` |
| טרנספורמציה | `AttendanceReport` | `AttendanceReport` חדש | `transformation/` |
| גנרוט | `AttendanceReport` | קובץ | `generation/` |

שלוש מחלקות בסיס:

| שכבה | בסיס | יורשים | מפצלים לפי | תבנית |
|---|---|---|---|---|
| פרסור | `BaseParser` | `TypeAParser`, `TypeBParser` | סוג הדו"ח | Template Method |
| טרנספורמציה | `BaseTransformationStrategy` | `TypeA…`, `TypeB…Strategy` | סוג הדו"ח | Strategy |
| גנרוט | `BaseRenderer` | `PdfRenderer`, `HtmlRenderer` | פורמט הפלט | |

**הוספת סוג C:** מחלקת פרסר, מחלקת אסטרטגיה (עם הכללים שלה) ופריסת עמוד (נתונים),
ושורה אחת בכל אחד משלושת המילונים (`factory.py`, `service.py`, `layouts.py`), ואותות
זיהוי ב-`classifier.py`. לא נוגעים בקוד של A או B.

## כללי השינוי

הערכים ב-`transformation/rules.py`, סט נפרד לכל סוג:

| | סוג A | סוג B |
|---|---|---|
| הזזת כניסה | עד ±30 דק', בצעדים של 5 | עד ±8 דק', בצעדים של דקה (כמו שעון נוכחות) |
| שינוי זמן העבודה | עד ±30 דק' | עד ±10 דק' |
| טווח יומי | 3 עד 12 שעות | 2 עד 12 שעות |
| חלון שעות | 06:00 עד 22:00 | 06:00 עד 22:00 |
| מה מחושב מחדש | סה"כ, 100/125/150/שבת, שורת סה"כ, תיבת סיכום | סה"כ, ימי עבודה, שעות חודשיות, סה"כ לתשלום |
| מה נשמר | תאריכים, מקום, הפסקה, בונוס, נסיעות, סוג התעריף של כל יום | תאריכים, ימים ריקים, הערות, מחיר לשעה |

* סוג A: ביום רגיל 8 שעות ראשונות 100%, 2 הבאות 125%, השאר 150%. בשבת הכל בעמודת שבת. יום שבמקור שולם כולו ב-150% (חג, למשל 17/10/2022) נשאר כזה.
* סוג B: השכר מחושב מסכום הדקות כפול מחיר לשעה, בדיוק כמו במקור.

כל וריאציה נבדקת מול האינווריאנטים (`domain/validation.py`), ואם אחד מהם נשבר
התוכנית עוצרת ולא כותבת קובץ.

החלטות התכנון ונימוקיהן: `DECISIONS.md`.
