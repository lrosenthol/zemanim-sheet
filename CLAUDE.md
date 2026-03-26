# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Script

```bash
python3 zemanim.py
```

Output is written to `/mnt/user-data/outputs/zmanim_pleasantville_2026_final.pdf`.

## Dependencies

```bash
pip3 install reportlab zmanim
```

Fonts are bundled in `./fonts/`: `SourceSans3-Regular.ttf` and `SourceSans3-Bold.ttf` (registered as `FreeSans`/`FreeSansBold` internally).

## Architecture

A pure-Python script that generates a full-year halachic times (zmanim) PDF
for Pleasantville, NJ (39.39°N, 74.52°W). GRA/standard opinion. Uses ReportLab
for PDF generation, `python-zmanim` for all calendar and solar math, and a custom
Hebrew bidi renderer (no external bidi library).

### Architecture Notes
- Solar math: `ZmanimCalendar` from `python-zmanim` (KosherJava port), GRA opinion
- Hebrew calendar: `JewishCalendar.from_date()` — do NOT use hardcoded lookup tables
- Hebrew bidi: custom grapheme-cluster RTL reordering via `h()` function
- DST/timezone: handled automatically by `GeoLocation('America/New_York')` + `ZoneInfo`
- Zmanim opinions: GRA (sha'ot zmaniyot from sunrise to sunset)
- Depression angles: alot = 16.1° (`alos()`), tzait = 8.5° (`tzais()`)
- Candle lighting: `ZmanimCalendar.candle_lighting()` (18 min before sunset by default)

### Do Not
- Do not replace `python-zmanim` with custom solar math — the original had 2-day date errors
- Do not introduce external Hebrew/bidi libraries (python-bidi, etc.)
- Do not change the `h()` reordering function without testing Hebrew rendering
- Do not use pytz — use `zoneinfo.ZoneInfo` (stdlib, Python 3.9+)

### Key Sections

**Hebrew text rendering** (`h()` function): ReportLab doesn't handle RTL text, so `h()`
manually reorders Hebrew Unicode into visual LTR order for display. Handles grapheme
clusters and bidirectional runs.

**Zmanim calculations** (`compute_zmanim()`): Delegates entirely to `ZmanimCalendar`
with `LOCATION = GeoLocation('Pleasantville, NJ', ...)`. Returns a dict of
timezone-aware datetimes; `fmt_time()` converts to local NJ time strings.

**Holiday detection** (`get_holiday_heb(jc)`): Uses `JewishCalendar.significant_day()`
which returns strings like `'pesach'`, `'rosh_hashana'`, `'chanukah'`, etc. These are
mapped to Hebrew strings via `_SIG_HEB`. Rosh Chodesh uses `is_rosh_chodesh()`.

**Special Shabbatot** (`_compute_special_shabbatot()`): Programmatically derives the
8 special Shabbatot (Shira, Shekalim, Zachor, Parah, HaChodesh, HaGadol, Chazon,
Nachamu, Shuva) from holiday anchor dates via `JewishDate.from_jewish_date()`.
Shabbat Shira is detected by parsha slug (`beshalach`).

**Parsha** (`get_parsha_heb()`): Uses `Parsha(jc).limud(jc)` to get the weekly
portion slug (e.g. `'beshalach'`, `'vayakheil - pikudei'`), then maps to Hebrew
via `_PARSHA_HEB` dict. Special Shabbat annotations appended from `_SPECIAL_SHABBATOT`.

**Molad & Shabbat Mevarchim** (`_build_molad_table()`): For each Rosh Chodesh in 2026
(except Tishrei), finds the preceding Shabbat and computes molad via
`JewishCalendar.molad_as_datetime()` converted to NJ local time.

**Candle lighting** (`candle_lighting_time()`): Uses `JewishCalendar.has_candle_lighting()`
to detect Erev Shabbat and Erev Yom Tov, then `ZmanimCalendar.candle_lighting()` for the time.

**PDF generation** (`make_month_table()`, `build_pdf()`): 14-column ReportLab table per
month. Color scheme: dark blue headers, yellow for Shabbat, pink for holidays/fasts/RC,
light blue for alternating rows, gold for candle lighting column.

### Adapting for Other Years/Locations

To change location: update `LOCATION` (GeoLocation) — timezone, DST, and solar math
adjust automatically.

To change year: update the output filename and the `months_rc` list in `_build_molad_table()`.
All holidays, parshiot, and Hebrew dates are computed dynamically from `python-zmanim`.
The `_RH_YEAR` dict may need a new entry for the new year's Hebrew name.

## Common Tasks
- Add a zman: add a `ZmanimCalendar` method call to `compute_zmanim()`, insert into `make_month_table()` cols
- Adjust candle offset: set `ZmanimCalendar.candle_lighting_offset` on the `zc` instance
- Add a holiday label: add entry to `_SIG_HEB` matching `significant_day()` return value
