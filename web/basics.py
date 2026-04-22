"""Chapter 1 basic-concept helpers: longitude parsing and sidereal lookups.

Used by /api/longitude_lookup and related feature endpoints.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

RAASI_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
RAASI_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karkataka", "Simha", "Kanya",
    "Thula", "Vrischika", "Dhanus", "Makara", "Kumbha", "Meena",
]
RAASI_ABBR = ["Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi"]

_ABBR_INDEX = {a.lower(): i for i, a in enumerate(RAASI_ABBR)}
_NAME_INDEX = {n.lower(): i for i, n in enumerate(RAASI_NAMES)}
_SKT_INDEX = {n.lower(): i for i, n in enumerate(RAASI_SANSKRIT)}

# 27 nakshatras. Vimsottari lords cycle: Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn, Mercury x 3.
# Deities from Ch 1 Table 2 (Narasimha Rao).
NAKSHATRAS = [
    ("Aswini",          "Ketu",    "Aswini Kumara"),
    ("Bharani",         "Venus",   "Yama"),
    ("Krittika",        "Sun",     "Agni"),
    ("Rohini",          "Moon",    "Brahma"),
    ("Mrigasira",       "Mars",    "Moon"),
    ("Aardra",          "Rahu",    "Shiva"),
    ("Punarvasu",       "Jupiter", "Aditi"),
    ("Pushyami",        "Saturn",  "Jupiter"),
    ("Aasresha",        "Mercury", "Rahu"),
    ("Makha",           "Ketu",    "Sun"),
    ("Poorva Phalguni", "Venus",   "Aryaman"),
    ("Uttara Phalguni", "Sun",     "Sun"),
    ("Hasta",           "Moon",    "Viswakarma"),
    ("Chitra",          "Mars",    "Vaayu"),
    ("Swaati",          "Rahu",    "Indra"),
    ("Visaakha",        "Jupiter", "Mitra"),
    ("Anooraadha",      "Saturn",  "Indra"),
    ("Jyeshtha",        "Mercury", "Nirriti"),
    ("Moola",           "Ketu",    "Varuna"),
    ("Poorvaashaadha",  "Venus",   "Viswadeva"),
    ("Uttaraashaadha",  "Sun",     "Brahma"),
    ("Sravanam",        "Moon",    "Vishnu"),
    ("Dhanishtha",      "Mars",    "Vasu"),
    ("Satabhishak",     "Rahu",    "Varuna"),
    ("Poorvaabhaadra",  "Jupiter", "Ajacharana"),
    ("Uttaraabhaadra",  "Saturn",  "Ahirbudhanya"),
    ("Revati",          "Mercury", "Pooshan"),
]

NAKSHATRA_ARC_DEG = 360.0 / 27.0  # 13°20'
PADA_ARC_DEG = NAKSHATRA_ARC_DEG / 4.0  # 3°20'


def _deg_to_dms(deg: float) -> str:
    sign = "-" if deg < 0 else ""
    deg = abs(deg)
    d = int(deg)
    m_full = (deg - d) * 60
    m = int(m_full)
    s = int(round((m_full - m) * 60))
    if s == 60:
        s = 0
        m += 1
    if m == 60:
        m = 0
        d += 1
    return f"{sign}{d}°{m:02d}'{s:02d}\""


def _rasi_index_from_token(tok: str) -> Optional[int]:
    t = tok.strip().lower().rstrip(".")
    if not t:
        return None
    if t in _ABBR_INDEX:
        return _ABBR_INDEX[t]
    if t in _NAME_INDEX:
        return _NAME_INDEX[t]
    if t in _SKT_INDEX:
        return _SKT_INDEX[t]
    # partial name match (case-insensitive prefix)
    for name, idx in _NAME_INDEX.items():
        if name.startswith(t):
            return idx
    return None


def parse_longitude(text: str) -> float:
    """Accepts many formats and returns a longitude in [0, 360).

    Supported forms (case-insensitive):
      * "94.316"                    pure decimal degrees
      * "94°19'"                    deg°min' (and optional seconds)
      * "25 Li 31"                  deg <rasi-abbr> min
      * "Li 25 31"                  <rasi> deg min
      * "5s 17 45"                  N-signs-style (5s = 150°)
      * "7s 17° 45' 30\""           signs + d°m's"
    """
    if text is None:
        raise ValueError("empty longitude")
    s = str(text).strip()
    if not s:
        raise ValueError("empty longitude")

    # Normalize: replace fancy symbols with ascii spaces
    normalized = re.sub(r"[°'\"‘’“”]", " ", s)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    # Case A: signs form "<N>s <deg> [min [sec]]"
    m = re.match(r"^(\d+)\s*s\b\s*(.*)$", normalized, flags=re.IGNORECASE)
    if m:
        n_signs = int(m.group(1))
        rest = m.group(2).strip()
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", rest)]
        d = nums[0] if nums else 0.0
        mn = nums[1] if len(nums) > 1 else 0.0
        sc = nums[2] if len(nums) > 2 else 0.0
        total = n_signs * 30.0 + d + mn / 60.0 + sc / 3600.0
        return total % 360.0

    # Case B: contains a rasi token
    tokens = normalized.split()
    rasi_idx: Optional[int] = None
    num_parts = []
    for tok in tokens:
        if rasi_idx is None:
            idx = _rasi_index_from_token(tok)
            if idx is not None:
                rasi_idx = idx
                continue
        # strip trailing punctuation before float parse
        try:
            num_parts.append(float(tok))
        except ValueError:
            # fallback: try stripping non-numeric chars
            clean = re.sub(r"[^0-9.\-]", "", tok)
            if clean not in ("", "-", "."):
                num_parts.append(float(clean))

    if rasi_idx is not None:
        d = num_parts[0] if num_parts else 0.0
        mn = num_parts[1] if len(num_parts) > 1 else 0.0
        sc = num_parts[2] if len(num_parts) > 2 else 0.0
        total = rasi_idx * 30.0 + d + mn / 60.0 + sc / 3600.0
        return total % 360.0

    # Case C: plain numbers -> deg [min [sec]]
    if num_parts:
        d = num_parts[0]
        mn = num_parts[1] if len(num_parts) > 1 else 0.0
        sc = num_parts[2] if len(num_parts) > 2 else 0.0
        total = d + mn / 60.0 + sc / 3600.0
        return total % 360.0

    raise ValueError(f"could not parse longitude: {text!r}")


def describe_longitude(longitude: float) -> dict:
    """Break a longitude into rasi / advancement / nakshatra / pada / lord / deity."""
    lon = longitude % 360.0
    rasi_idx = int(lon // 30)
    rasi_advance = lon - rasi_idx * 30

    nak_idx = int(lon // NAKSHATRA_ARC_DEG)
    if nak_idx > 26:
        nak_idx = 26
    nak_start = nak_idx * NAKSHATRA_ARC_DEG
    nak_advance = lon - nak_start
    pada = int(nak_advance // PADA_ARC_DEG) + 1
    if pada > 4:
        pada = 4
    pada_advance = nak_advance - (pada - 1) * PADA_ARC_DEG

    nak_name, nak_lord, nak_deity = NAKSHATRAS[nak_idx]

    # "Ns D°M'S''" short form
    n_signs = rasi_idx
    d = int(rasi_advance)
    m_full = (rasi_advance - d) * 60
    m_ = int(m_full)
    sec_val = int(round((m_full - m_) * 60))
    if sec_val == 60:
        sec_val = 0
        m_ += 1
    if m_ == 60:
        m_ = 0
        d += 1
    signs_form = f"{n_signs}s {d}° {m_:02d}' {sec_val:02d}\""

    return {
        "longitude": round(lon, 6),
        "longitude_dms": _deg_to_dms(lon),
        "signs_form": signs_form,
        "rasi": {
            "index": rasi_idx,
            "number": rasi_idx + 1,
            "name": RAASI_NAMES[rasi_idx],
            "sanskrit": RAASI_SANSKRIT[rasi_idx],
            "abbr": RAASI_ABBR[rasi_idx],
            "advance_deg": round(rasi_advance, 6),
            "advance_dms": _deg_to_dms(rasi_advance),
        },
        "nakshatra": {
            "index": nak_idx,
            "number": nak_idx + 1,
            "name": nak_name,
            "vimsottari_lord": nak_lord,
            "deity": nak_deity,
            "start_deg": round(nak_start, 6),
            "start_dms": _deg_to_dms(nak_start),
            "advance_deg": round(nak_advance, 6),
            "advance_dms": _deg_to_dms(nak_advance),
        },
        "pada": {
            "number": pada,
            "advance_deg": round(pada_advance, 6),
            "advance_dms": _deg_to_dms(pada_advance),
        },
    }


def lookup(text: str) -> Tuple[dict, str]:
    """Parse free-form input and return a lookup payload plus a canonical string."""
    lon = parse_longitude(text)
    data = describe_longitude(lon)
    canonical = f"{data['longitude_dms']} · {data['signs_form']}"
    return data, canonical
