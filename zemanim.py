#!/usr/bin/env python3
"""
Full-year Zmanim PDF for Pleasantville, NJ (2026)
GRA / standard opinion — uses python-zmanim for all calendar and solar math

Copyright (c) 2026 Leonard Rosenthol
SPDX-License-Identifier: MIT
"""

import argparse
import datetime
import calendar
import json
import os
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from zmanim.zmanim_calendar import ZmanimCalendar
from zmanim.util.geo_location import GeoLocation
from zmanim.hebrew_calendar.jewish_calendar import JewishCalendar
from zmanim.hebrew_calendar.jewish_date import JewishDate
from zmanim.limudim.calculators.parsha import Parsha

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Register fonts ────────────────────────────────────────────────────────────
# Latin/numeric columns use Source Sans 3; Hebrew cells use Noto Sans Hebrew
pdfmetrics.registerFont(TTFont('SourceSans',     'fonts/SourceSans3-Regular.ttf'))
pdfmetrics.registerFont(TTFont('SourceSansBold', 'fonts/SourceSans3-Bold.ttf'))
pdfmetrics.registerFont(TTFont('FreeSans',       'fonts/Shlomo.ttf'))
pdfmetrics.registerFont(TTFont('FreeSansBold',   'fonts/ShlomoBold.ttf'))

# ── Hebrew bidi reordering (no external library needed) ───────────────────────
import unicodedata as _ud

# Paired characters that Unicode BiDi-mirrors when embedded in RTL text
_BIDI_MIRROR = str.maketrans('()[]{}', ')(][}{')

def _is_rtl(c):
    cp = ord(c)
    return 0x0590 <= cp <= 0x05FF

def _is_combining(c):
    return _ud.category(c) in ('Mn', 'Mc', 'Me')

def _graphemes(text):
    clusters, cur = [], ''
    for c in text:
        if cur and not _is_combining(c):
            clusters.append(cur)
            cur = c
        else:
            cur += c
    if cur:
        clusters.append(cur)
    return clusters

def h(text):
    """Reorder Hebrew (RTL) string into visual LTR order for ReportLab."""
    if not text:
        return text
    if '\n' in text:
        return '\n'.join(h(line) for line in text.split('\n'))
    gs = _graphemes(text)
    if not any(_is_rtl(g[0]) for g in gs):
        return text
    runs, cur_rtl, cur = [], True, []
    for g in gs:
        base = g[0]
        if base == ' ':
            cur.append(g)
        elif _is_rtl(base):
            if not cur_rtl:
                runs.append((False, cur)); cur_rtl = True; cur = []
            cur.append(g)
        else:
            if cur_rtl:
                runs.append((True, cur)); cur_rtl = False; cur = []
            cur.append(g)
    if cur:
        runs.append((cur_rtl, cur))
    runs.reverse()
    result = []
    for is_rtl_run, gs_run in runs:
        for g in (reversed(gs_run) if is_rtl_run else gs_run):
            if is_rtl_run and len(g) > 1:
                # Hebrew nikud glyphs are left-anchored in LTR rendering:
                # emit combining marks before their base so both land at the
                # same x-position and the marks overlay the letter correctly.
                result.append(g[1:] + g[0])
            elif not is_rtl_run:
                # Mirror paired brackets embedded in RTL text (Unicode BiDi rule).
                result.append(g.translate(_BIDI_MIRROR))
            else:
                result.append(g)
    return ''.join(result)

# ── Geocoding ─────────────────────────────────────────────────────────────────
_DEFAULT_CITY = "Pleasantville, NJ"
_DEFAULT_LAT  = 39.3901
_DEFAULT_LON  = -74.5218
_DEFAULT_TZ   = "America/New_York"

def geocode_city(city_name):
    """Return (display_name, lat, lon) using OpenStreetMap Nominatim."""
    params = urllib.parse.urlencode({'q': city_name, 'format': 'json', 'limit': 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={'User-Agent': 'zemanim-sheet/1.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        results = json.loads(resp.read())
    if not results:
        raise SystemExit(f"Error: city not found: {city_name!r}")
    r = results[0]
    return r['display_name'], float(r['lat']), float(r['lon'])

def get_timezone(lat, lon):
    """Return IANA timezone string for coordinates using timezonefinder."""
    try:
        from timezonefinder import TimezoneFinder
    except ImportError:
        raise SystemExit("Error: run 'pip3 install timezonefinder' to look up timezones by city.")
    tz = TimezoneFinder().timezone_at(lat=lat, lng=lon)
    if tz is None:
        raise SystemExit(f"Error: could not determine timezone for {lat:.4f}, {lon:.4f}")
    return tz

def city_slug(name):
    """Convert city name to a filename-safe lowercase slug."""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

# ── Location & timezone (set in __main__, defaults to Pleasantville NJ) ───────
LOCATION = GeoLocation(_DEFAULT_CITY, _DEFAULT_LAT, _DEFAULT_LON, _DEFAULT_TZ, elevation=0)
NJ_TZ    = ZoneInfo(_DEFAULT_TZ)

# ── Time formatting ───────────────────────────────────────────────────────────
def fmt_time(t):
    if t is None:
        return "—"
    local = t.astimezone(NJ_TZ)
    return f"{local.hour}:{local.minute:02d}"

# ── Zmanim calculations (GRA opinion) ────────────────────────────────────────
def compute_zmanim(year, month, day):
    zc = ZmanimCalendar(geo_location=LOCATION, date=datetime.date(year, month, day))
    return {
        "alot":    zc.alos(),
        "sunrise": zc.sunrise(),
        "szs":     zc.sof_zman_shma_gra(),
        "szt":     zc.sof_zman_tfila_gra(),
        "chatzot": zc.chatzos(),
        "mg":      zc.mincha_gedola(),
        "mk":      zc.mincha_ketana(),
        "plag":    zc.plag_hamincha(),
        "sunset":  zc.sunset(),
        "tzait":   zc.tzais(),
    }

# ── Hebrew numerals ───────────────────────────────────────────────────────────
_ONES = ['', 'א', 'ב', 'ג', 'ד', 'ה', 'ו', 'ז', 'ח', 'ט']
_TENS = ['', 'י', 'כ', 'ל', 'מ', 'נ', 'ס', 'ע', 'פ', 'צ']
_SPEC = {15: 'ט״ו', 16: 'ט״ז'}

def num_to_heb(n):
    if n in _SPEC:
        return _SPEC[n]
    tens, ones = n // 10, n % 10
    result = (_TENS[tens] if tens else '') + (_ONES[ones] if ones else '')
    if len(result) >= 2:
        result = result[:-1] + '״' + result[-1]
    elif len(result) == 1:
        result = result + '׳'
    return result

# ── Hebrew month names ────────────────────────────────────────────────────────
_MONTH_HEB = {
    1:  "נִיסָן",   2:  "אִיָּר",    3:  "סִיוָן",
    4:  "תַּמּוּז",  5:  "אָב",      6:  "אֱלוּל",
    7:  "תִּשְׁרֵי", 8:  "חֶשְׁוָן", 9:  "כִּסְלֵו",
    10: "טֵבֵת",   11: "שְׁבָט",    12: "אֲדָר",
    13: "אֲדָר ב׳",
}

def _jc(year, month, day):
    return JewishCalendar.from_date(datetime.date(year, month, day))

def _is_leap(jewish_year):
    return JewishDate.from_jewish_date(jewish_year, 7, 1).months_in_jewish_year() == 13

def _month_name(jc):
    name = _MONTH_HEB.get(jc.jewish_month, '?')
    if jc.jewish_month == 12 and _is_leap(jc.jewish_year):
        name = "אֲדָר א׳"
    return name

def heb_date_str(year, month, day):
    jc = _jc(year, month, day)
    return h(f"{num_to_heb(jc.jewish_day)} {_month_name(jc)}")

# ── Holiday / significant-day detection ───────────────────────────────────────
_SIG_HEB = {
    'erev_rosh_hashana':  "עֶרֶב רֹאשׁ הַשָּׁנָה",
    'erev_yom_kippur':    "עֶרֶב יוֹם כִּפּוּר",
    'erev_pesach':        "עֶרֶב פֶּסַח",
    'erev_shavuos':       "עֶרֶב שָׁבוּעוֹת",
    'erev_succos':        "עֶרֶב סֻכּוֹת",
    'yom_kippur':         "יוֹם כִּפּוּר",
    'hoshana_rabbah':     "הוֹשַׁעְנָא רַבָּה",
    'shemini_atzeres':    "שְׁמִינִי עֲצֶרֶת",
    'simchas_torah':      "שִׂמְחַת תּוֹרָה",
    'chol_hamoed_pesach': "חוֹל הַמּוֹעֵד פֶּסַח",
    'chol_hamoed_succos': "חוֹל הַמּוֹעֵד סֻכּוֹת",
    'taanis_esther':      "תַּעֲנִית אֶסְתֵּר",
    'purim':              "פּוּרִים",
    'shushan_purim':      "שׁוּשַׁן פּוּרִים",
    'tzom_gedalyah':      "צוֹם גְּדַלְיָה",
    'tisha_beav':         "תִּשְׁעָה בְּאָב",
    'seventeen_of_tammuz':"י״ז בְּתַמּוּז",
    'tenth_of_teves':     "עֲשָׂרָה בְּטֵבֵת",
}

_PESACH_DAY = {15: "א׳", 16: "ב׳", 21: "ז׳", 22: "ח׳"}
_SUCCOS_DAY = {15: "א׳", 16: "ב׳"}
_RH_YEAR    = {5786: "תשפ״ו", 5787: "תשפ״ז"}

def get_holiday_heb(jc):
    """Return Hebrew holiday/observance label for this day, or ''."""
    sig = jc.significant_day()

    if sig == 'rosh_hashana':
        suffix = "ב׳" if jc.jewish_day == 2 else _RH_YEAR.get(jc.jewish_year, "")
        return f"רֹאשׁ הַשָּׁנָה {suffix}"

    if sig == 'succos':
        return f"סֻכּוֹת {_SUCCOS_DAY.get(jc.jewish_day, '')}"

    if sig == 'pesach':
        return f"פֶּסַח {_PESACH_DAY.get(jc.jewish_day, '')}"

    if sig == 'shavuos':
        return f"שָׁבוּעוֹת {'ב׳' if jc.jewish_day == 7 else 'א׳'}"

    if sig == 'chanukah':
        base = f"חֲנֻכָּה {num_to_heb(jc.day_of_chanukah())}"
        if jc.is_rosh_chodesh():
            if jc.jewish_day == 30:
                # First day of 2-day RC: new month is tomorrow
                next_jc = JewishCalendar.from_date(
                    jc.gregorian_date + datetime.timedelta(days=1))
                return f"{base} / ר״ח {_month_name(next_jc)} א׳"
            else:
                prev_jc = JewishCalendar.from_date(
                    jc.gregorian_date - datetime.timedelta(days=1))
                suffix = " ב׳" if prev_jc.is_rosh_chodesh() else ""
                return f"{base} / ר״ח {_month_name(jc)}{suffix}"
        return base

    if sig in _SIG_HEB:
        return _SIG_HEB[sig]

    if jc.is_rosh_chodesh():
        if jc.jewish_day == 30:
            # First day of a 2-day RC: the new month is tomorrow
            next_jc = JewishCalendar.from_date(
                jc.gregorian_date + datetime.timedelta(days=1))
            return f"ר״ח {_month_name(next_jc)} א׳"
        # jewish_day == 1
        prev_jc = JewishCalendar.from_date(
            jc.gregorian_date - datetime.timedelta(days=1))
        suffix = " ב׳" if prev_jc.is_rosh_chodesh() else ""
        return f"ר״ח {_month_name(jc)}{suffix}"

    return ""

# ── Parsha (Torah portion) ────────────────────────────────────────────────────
_PARSHA_HEB = {
    'bereishis':           'בְּרֵאשִׁית',
    'noach':               'נֹחַ',
    'lech_lecha':          'לֶךְ-לְךָ',
    'vayeira':             'וַיֵּרָא',
    'chayei_sarah':        'חַיֵּי שָׂרָה',
    'toldos':              'תּוֹלְדֹת',
    'vayeitzei':           'וַיֵּצֵא',
    'vayishlach':          'וַיִּשְׁלַח',
    'vayeishev':           'וַיֵּשֶׁב',
    'mikeitz':             'מִקֵּץ',
    'vayigash':            'וַיִּגַּשׁ',
    'vayechi':             'וַיְחִי',
    'shemos':              'שְׁמוֹת',
    'vaeirah':             'וָאֵרָא',
    'bo':                  'בֹּא',
    'beshalach':           'בְּשַׁלַּח',
    'yisro':               'יִתְרוֹ',
    'mishpatim':           'מִשְׁפָּטִים',
    'terumah':             'תְּרוּמָה',
    'tetzaveh':            'תְּצַוֶּה',
    'ki_sisa':             'כִּי תִשָּׂא',
    'vayakheil':           'וַיַּקְהֵל',
    'pikudei':             'פְּקוּדֵי',
    'vayikra':             'וַיִּקְרָא',
    'tzav':                'צַו',
    'shemini':             'שְׁמִינִי',
    'tazria':              'תַזְרִיעַ',
    'metzora':             'מְצֹרָע',
    'acharei':             'אַחֲרֵי מוֹת',
    'kedoshim':            'קְדֹשִׁים',
    'emor':                'אֱמֹר',
    'behar':               'בְּהַר',
    'bechukosai':          'בְּחֻקֹּתַי',
    'bamidbar':            'בְּמִדְבַּר',
    'naso':                'נָשׂוֹא',
    'behaalosecha':        'בְּהַעֲלֹתְךָ',
    'shelach':             'שְׁלַח',
    'korach':              'קֹרַח',
    'chukas':              'חֻקַּת',
    'balak':               'בָּלָק',
    'pinchas':             'פִּינְחָס',
    'matos':               'מַטּוֹת',
    'masei':               'מַסְעֵי',
    'devarim':             'דְּבָרִים',
    'vaeschanan':          'וָאֶתְחַנַּן',
    'eikev':               'עֵקֶב',
    'reei':                'רְאֵה',
    'shoftim':             'שֹׁפְטִים',
    'ki_seitzei':          'כִּי תֵצֵא',
    'ki_savo':             'כִּי תָבוֹא',
    'nitzavim':            'נִצָּבִים',
    'vayeilech':           'וַיֵּלֶךְ',
    'haazinu':             'הַאֲזִינוּ',
    'vezos_haberacha':     'וְזֹאת הַבְּרָכָה',
}

def _slug_to_heb(slug):
    """Convert a parsha slug (possibly 'a - b') to Hebrew."""
    if ' - ' in slug:
        parts = [p.strip() for p in slug.split(' - ')]
        return '-'.join(_PARSHA_HEB.get(p, p) for p in parts)
    return _PARSHA_HEB.get(slug, slug)

# ── Special Shabbatot ─────────────────────────────────────────────────────────
def _last_shabbat_on_or_before(d):
    days_back = (d.weekday() - 5) % 7
    return d - datetime.timedelta(days=days_back)

def _next_shabbat_after(d):
    days_fwd = (5 - d.weekday()) % 7
    if days_fwd == 0:
        days_fwd = 7
    return d + datetime.timedelta(days=days_fwd)

def _compute_special_shabbatot():
    purim   = JewishDate.from_jewish_date(5786, 12, 14).gregorian_date
    pesach  = JewishDate.from_jewish_date(5786, 1,  15).gregorian_date
    rc_nis  = JewishDate.from_jewish_date(5786, 1,   1).gregorian_date
    rc_adar = JewishDate.from_jewish_date(5786, 12,  1).gregorian_date
    tav     = JewishDate.from_jewish_date(5786, 5,   9).gregorian_date
    rh_5787 = JewishDate.from_jewish_date(5787, 7,   1).gregorian_date
    yk_5787 = JewishDate.from_jewish_date(5787, 7,  10).gregorian_date

    hachodesh = _last_shabbat_on_or_before(rc_nis)
    shuva     = _next_shabbat_after(rh_5787)

    special = {
        _last_shabbat_on_or_before(rc_adar):              "שַׁבָּת שְׁקָלִים",
        _last_shabbat_on_or_before(purim - datetime.timedelta(days=1)): "שַׁבָּת זָכוֹר",
        hachodesh - datetime.timedelta(days=7):            "שַׁבָּת פָּרָה",
        hachodesh:                                         "שַׁבָּת הַחֹדֶשׁ",
        _last_shabbat_on_or_before(pesach - datetime.timedelta(days=1)): "שַׁבָּת הַגָּדוֹל",
        _last_shabbat_on_or_before(tav - datetime.timedelta(days=1)):    "שַׁבָּת חֲזוֹן",
        _next_shabbat_after(tav):                          "שַׁבָּת נַחֲמוּ",
    }
    if shuva < yk_5787:
        special[shuva] = "שַׁבָּת שׁוּבָה"
    return special

_SPECIAL_SHABBATOT = _compute_special_shabbatot()

def get_parsha_heb(year, month, day):
    """Return Hebrew parsha string for a Shabbat (with special label if applicable)."""
    dt = datetime.date(year, month, day)
    if dt.weekday() != 5:
        return ""
    jc = JewishCalendar.from_date(dt)
    p  = Parsha(jc)
    r  = p.limud(jc)
    if not r:
        return ""
    parsha_heb = _slug_to_heb(str(r.unit))
    special    = _SPECIAL_SHABBATOT.get(dt, "")
    # Shabbat Shira is always Beshalach
    if str(r.unit) == 'beshalach':
        special = "שַׁבָּת שִׁירָה"
    if special:
        return f"{parsha_heb} — {special}"
    return parsha_heb

# ── Candle lighting ───────────────────────────────────────────────────────────
def candle_lighting_time(year, month, day):
    """Return candle-lighting time string for Erev Shabbat / Erev Yom Tov, else ''."""
    dt = datetime.date(year, month, day)
    jc = JewishCalendar.from_date(dt)
    if not jc.has_candle_lighting():
        return ""
    zc = ZmanimCalendar(geo_location=LOCATION, date=dt)
    return fmt_time(zc.candle_lighting())

# ── Molad & Shabbat Mevarchim ─────────────────────────────────────────────────
def _build_molad_table():
    """
    Return {shabbat_date: (rc_heb_str, molad_display_str)} for every
    Shabbat Mevarchim (last Shabbat before each Rosh Chodesh) in 2026,
    skipping Tishrei (no Shabbat Mevarchim).
    """
    table = {}
    # RC months whose 1st day falls in calendar year 2026
    months_rc = [
        (5786, 11), (5786, 12),
        (5786,  1), (5786,  2), (5786, 3), (5786, 4), (5786, 5), (5786, 6),
        # Tishrei 5787 skipped
        (5787,  8), (5787,  9), (5787, 10),
    ]
    for hy, hm in months_rc:
        rc_date = JewishDate.from_jewish_date(hy, hm, 1).gregorian_date
        if rc_date.year != 2026:
            continue

        # Last Shabbat strictly before RC
        days_back = (rc_date.weekday() - 5) % 7
        if days_back == 0:
            days_back = 7
        shab_date = rc_date - datetime.timedelta(days=days_back)
        if shab_date.year != 2026:
            continue

        jc = JewishCalendar.from_date(rc_date)
        m_dt_nj = jc.molad_as_datetime().astimezone(NJ_TZ)

        month_name = _MONTH_HEB.get(hm, '?')
        if hm == 12 and _is_leap(hy):
            month_name = "אֲדָר א׳"

        rc_heb    = h(f"ר״ח {month_name}")
        dow_en    = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
        chalak    = (m_dt_nj.second * 18 + m_dt_nj.microsecond * 18 // 1_000_000) // 60
        molad_str = (
            h(f"מולד {month_name}") + ": " +
            f"{dow_en[m_dt_nj.weekday()]} {m_dt_nj.hour}:{m_dt_nj.minute:02d}+{chalak}ch NJ"
        )
        table[shab_date] = (rc_heb, molad_str)
    return table

MOLAD_TABLE = {}  # populated in build_pdf after location is set

# ── PDF colours & styles ──────────────────────────────────────────────────────
HEADER_BG   = colors.HexColor("#1a3a5c")
ALT_ROW     = colors.HexColor("#eef4fb")
SHABBAT_BG  = colors.HexColor("#fff3cd")
SHABBAT_TXT = colors.HexColor("#7b4a00")
HOLIDAY_BG  = colors.HexColor("#fce8e8")
HOLIDAY_TXT = colors.HexColor("#8b0000")
HEADER_TXT  = colors.white
BORDER_CLR  = colors.HexColor("#94b8d8")

MONTHS_EN = ["January","February","March","April","May","June",
             "July","August","September","October","November","December"]

def heb_para(text, fontsize=9, bold=False, color=colors.black, align=TA_RIGHT):
    fname = 'FreeSansBold' if bold else 'FreeSans'
    style = ParagraphStyle(
        'heb_cell', fontName=fname, fontSize=fontsize,
        textColor=color, alignment=align, leading=fontsize + 2,
    )
    return Paragraph(text, style)

# ── Monthly table ─────────────────────────────────────────────────────────────
def make_month_table(year, month):
    hdr_style = ParagraphStyle(
        'HdrHeb', fontName='FreeSans', fontSize=8.5,
        textColor=colors.white, alignment=TA_CENTER, leading=12,
    )
    def hdr(txt):
        return Paragraph(txt, hdr_style)

    col_headers = [
        hdr("Date\nDay"),
        hdr(h("תאריך\nעברי")),
        hdr(h("חג / פרשה / מולד")),
        hdr(h("עלות\nהשחר")),
        hdr(h("נץ\nהחמה")),
        hdr(h("סוף זמן\nק״ש (גר״א)")),
        hdr(h("סוף זמן\nתפילה")),
        hdr(h("חצות")),
        hdr(h("מנחה\nגדולה")),
        hdr(h("מנחה\nקטנה")),
        hdr(h("פלג\nהמנחה")),
        hdr(h("שקיעה")),
        hdr(h("הדלקת\nנרות")),
        hdr(h("צאת\nהכוכבים")),
    ]

    data      = [col_headers]
    day_names = ["Mon","Tue","Wed","Thu","Fri","Shab","Sun"]
    num_days  = calendar.monthrange(year, month)[1]

    for day in range(1, num_days + 1):
        dt  = datetime.date(year, month, day)
        jc  = JewishCalendar.from_date(dt)
        dn  = day_names[dt.weekday()]
        hd  = heb_date_str(year, month, day)

        holiday_str = h(get_holiday_heb(jc))
        parsha_str  = h(get_parsha_heb(year, month, day))

        # Primary annotation: holiday > parsha (only on Shabbat)
        if holiday_str:
            annot_main = holiday_str
        elif dt.weekday() == 5:
            annot_main = parsha_str
        else:
            annot_main = ""

        # Shabbat Mevarchim: append molad info
        molad_extra = ""
        if dt in MOLAD_TABLE:
            rc_heb, molad_str = MOLAD_TABLE[dt]
            molad_extra = h("מברכים ") + " " + rc_heb + "\n" + molad_str

        if annot_main and molad_extra:
            annot = annot_main + "\n" + molad_extra
        elif molad_extra:
            annot = molad_extra
        else:
            annot = annot_main

        cl_time = candle_lighting_time(year, month, day)

        z = compute_zmanim(year, month, day)
        times = ["—"] * 10 if z is None else [
            fmt_time(z["alot"]),    fmt_time(z["sunrise"]),
            fmt_time(z["szs"]),     fmt_time(z["szt"]),
            fmt_time(z["chatzot"]), fmt_time(z["mg"]),
            fmt_time(z["mk"]),      fmt_time(z["plag"]),
            fmt_time(z["sunset"]),  fmt_time(z["tzait"]),
        ]
        times.insert(-1, cl_time)   # candle lighting before tzait

        is_shabbat = dt.weekday() == 5
        is_holiday = bool(get_holiday_heb(jc)) and not is_shabbat
        is_mev     = dt in MOLAD_TABLE
        txt_color  = SHABBAT_TXT if is_shabbat else (HOLIDAY_TXT if is_holiday else colors.black)

        hd_para    = heb_para(hd,    fontsize=9, bold=is_shabbat, color=txt_color)
        annot_para = heb_para(annot, fontsize=8, bold=bool(annot_main), color=txt_color)

        row = [f"{month}/{day}\n{dn}", hd_para, annot_para] + times
        data.append(row)

    col_widths = [0.48*inch, 0.72*inch, 1.35*inch] + [0.67*inch]*11

    t = Table(data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ('BACKGROUND', (0,0),  (-1,0),  HEADER_BG),
        ('VALIGN',     (0,0),  (-1,0),  'MIDDLE'),
        ('FONTNAME',   (0,1),  (0,-1),  'SourceSans'),
        ('FONTNAME',   (3,1),  (-1,-1), 'SourceSans'),
        ('FONTSIZE',   (0,1),  (-1,-1), 9),
        ('ALIGN',      (0,1),  (0,-1),  'CENTER'),
        ('ALIGN',      (3,1),  (-1,-1), 'CENTER'),
        ('ALIGN',      (1,1),  (2,-1),  'RIGHT'),
        ('VALIGN',     (0,1),  (-1,-1), 'MIDDLE'),
        ('ROWHEIGHT',  (0,1),  (-1,-1), 21),
        ('ROWHEIGHT',  (0,0),  (-1,0),  19),
        ('BACKGROUND', (12,1), (12,-1), colors.HexColor("#fffbea")),
        ('FONTNAME',   (12,1), (12,-1), 'SourceSansBold'),
        ('TEXTCOLOR',  (12,1), (12,-1), colors.HexColor("#7b4a00")),
        ('GRID',       (0,0),  (-1,-1), 0.3, BORDER_CLR),
        ('LINEAFTER',  (2,0),  (2,-1),  0.8, colors.HexColor("#4a7aaa")),
        ('LINEBEFORE', (12,0), (12,-1), 0.8, colors.HexColor("#4a7aaa")),
    ]

    num_days = calendar.monthrange(year, month)[1]
    for i, day in enumerate(range(1, num_days + 1)):
        ri = i + 1
        dt = datetime.date(year, month, day)
        jc = JewishCalendar.from_date(dt)
        is_shabbat = dt.weekday() == 5
        is_holiday = bool(get_holiday_heb(jc)) and not is_shabbat
        is_mev     = dt in MOLAD_TABLE

        if is_mev:
            style_cmds += [('ROWHEIGHT', (0,ri), (-1,ri), 44)]

        if is_shabbat:
            style_cmds += [
                ('BACKGROUND', (0,ri),  (-1,ri),  SHABBAT_BG),
                ('TEXTCOLOR',  (0,ri),  (0,ri),   SHABBAT_TXT),
                ('TEXTCOLOR',  (3,ri),  (11,ri),  SHABBAT_TXT),
                ('TEXTCOLOR',  (13,ri), (13,ri),  SHABBAT_TXT),
                ('FONTNAME',   (0,ri),  (0,ri),   'SourceSansBold'),
                ('FONTNAME',   (3,ri),  (11,ri),  'SourceSansBold'),
                ('FONTNAME',   (13,ri), (13,ri),  'SourceSansBold'),
            ]
        elif is_holiday:
            style_cmds += [
                ('BACKGROUND', (0,ri), (-1,ri), HOLIDAY_BG),
                ('TEXTCOLOR',  (0,ri), (0,ri),  HOLIDAY_TXT),
                ('TEXTCOLOR',  (3,ri), (-1,ri), HOLIDAY_TXT),
            ]
        elif i % 2 == 0:
            style_cmds += [('BACKGROUND', (0,ri), (-1,ri), ALT_ROW)]

        if not is_shabbat and not is_holiday:
            cl = candle_lighting_time(year, month, day)
            if cl:
                style_cmds += [
                    ('BACKGROUND', (12,ri), (12,ri), colors.HexColor("#fff3cd")),
                    ('TEXTCOLOR',  (12,ri), (12,ri), SHABBAT_TXT),
                    ('FONTNAME',   (12,ri), (12,ri), 'SourceSansBold'),
                ]

    t.setStyle(TableStyle(style_cmds))
    return t

# ── PDF assembly ──────────────────────────────────────────────────────────────
def build_pdf(output_path, city_label=_DEFAULT_CITY, lat=_DEFAULT_LAT, lon=_DEFAULT_LON):
    global MOLAD_TABLE
    MOLAD_TABLE = _build_molad_table()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(letter),
        leftMargin=0.35*inch, rightMargin=0.35*inch,
        topMargin=0.25*inch,  bottomMargin=0.25*inch,
    )

    title_style = ParagraphStyle(
        'ZTitle', fontSize=13, fontName='SourceSansBold',
        textColor=HEADER_BG, alignment=TA_CENTER, spaceAfter=1
    )
    heb_title_style = ParagraphStyle(
        'ZTitleHeb', fontSize=13, fontName='FreeSansBold',
        textColor=HEADER_BG, alignment=TA_CENTER, spaceAfter=1,
    )
    heb_sub_style = ParagraphStyle(
        'ZSubHeb', fontSize=7.5, fontName='FreeSans',
        textColor=colors.HexColor("#555555"), alignment=TA_CENTER, spaceAfter=4,
    )
    legend_style = ParagraphStyle(
        'Legend', fontSize=6, fontName='FreeSans',
        textColor=colors.HexColor("#666666"), alignment=TA_CENTER, spaceAfter=0,
    )

    story = []

    for month_idx, month_name in enumerate(MONTHS_EN):
        month_num = month_idx + 1

        story.append(Paragraph(
            h("זמנים") + f" — {month_name} 2026  |  {city_label}",
            heb_title_style
        ))

        story.append(Spacer(1, 4))
        
        story.append(Paragraph(
            f"Lat: {abs(lat):.2f}°{'N' if lat >= 0 else 'S'}  •  Lon: {abs(lon):.2f}°{'E' if lon >= 0 else 'W'}  •  {h('שיטת הגר״א')}  •  "
            f"Times are local EST/EDT  •  {h('תשפ״ו')} / {h('תשפ״ז')}",
            heb_sub_style
        ))

        story.append(make_month_table(2026, month_num))
        story.append(Spacer(1, 3))

        legend_text = (
            h("צהוב = שבת") + "  •  " +
            h("ורוד = חג") + "  •  " +
            h("עמודת הדלקת נרות = 18 דקות לפני השקיעה") + "  •  " +
            h("עלות") + " = 16.1°  •  " +
            h("צאת") + " = 8.5°  •  " +
            h("יש לברר עם רב לפני מעשה")
        )
        story.append(Paragraph(legend_text, legend_style))

        if month_num < 12:
            story.append(PageBreak())

    doc.build(story)
    print(f"✓ Saved: {output_path}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate a full-year zmanim PDF.')
    parser.add_argument('--city', default=None,
                        help=f'City name to geocode (default: "{_DEFAULT_CITY}")')
    args = parser.parse_args()

    if args.city:
        print(f'Geocoding "{args.city}"...')
        display_name, lat, lon = geocode_city(args.city)
        tz_name = get_timezone(lat, lon)
        # Use a short label: everything before the first comma in display_name
        city_label = display_name.split(',')[0].strip()
        print(f"  → {city_label}  {lat:.4f}, {lon:.4f}  ({tz_name})")
        LOCATION = GeoLocation(city_label, lat, lon, tz_name, elevation=0)
        NJ_TZ    = ZoneInfo(tz_name)
        slug = city_slug(args.city)
    else:
        city_label = _DEFAULT_CITY
        lat, lon   = _DEFAULT_LAT, _DEFAULT_LON
        slug       = city_slug(_DEFAULT_CITY)

    os.makedirs('./output', exist_ok=True)
    out = f"./output/zmanim_{slug}_2026.pdf"
    build_pdf(out, city_label=city_label, lat=lat, lon=lon)
