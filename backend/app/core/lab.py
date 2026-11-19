"""Laboratory test results: templates, acceptance and AI reading (ported from the Odoo dr module).

One lab test record holds the certificate's details and its result lines:
    sample | parameter | value | min | max | unit  ->  line result (pass / fail / na)
Acceptance:
    all       every checked line within its limits
    concrete  28-day specimens: mean >= fck + mean margin AND lowest >= fck - margin (or >= X % of fck),
              and no other line failing
Concrete classes of the project (grade, fck, margins, the topics they are used in) decide fck.
"""
import base64
import json
import logging
import re
import urllib.request

from app.core.config import get_settings

log = logging.getLogger("verqac.lab")

MATERIALS = [("CON", "الباطون", "Concrete"), ("STL", "حديد التسليح", "Reinforcement steel"),
             ("BC", "البيسكورس والصبكورس", "Base course / Subbase"), ("SOIL", "التربة والردم", "Soil / Backfill"),
             ("ASP", "الأسفلت", "Asphalt"), ("BLK", "الطوب", "Blocks / Masonry"),
             ("TIL", "البلاط والحجر", "Tiles / Stone"), ("WP", "العزل", "Waterproofing / Insulation"),
             ("MEP", "مواد كهروميكانيكية", "MEP materials"), ("OTH", "أخرى", "Other")]
MATERIAL_CODES = {m[0] for m in MATERIALS}
DECISIONS = ("retest", "core", "accepted", "deduction", "repair", "rejected", "other")
PASS_WORDS = {"OK", "PASS", "PASSED", "YES", "Y", "C", "COMPLY", "COMPLIES", "✓", "مطابق", "ناجح"}
FAIL_WORDS = {"NOK", "NOT OK", "FAIL", "FAILED", "NO", "N", "NC", "X", "✗", "غير مطابق", "راسب"}


def _L(param, unit=None, mn=None, mx=None, sample=None, method=None, kind="number"):
    return {"sample": sample, "parameter": param, "unit": unit, "method": method, "kind": kind, "min": mn, "max": mx}


SIEVES = [('2" (50 mm)', 100, 100), ('1.5" (37.5 mm)', 100, 100), ('1" (25 mm)', 75, 100), ('3/4" (19.0 mm)', 60, 90),
          ('1/2" (12.5 mm)', 45, 80), ('3/8" (9.5 mm)', 40, 70), ("#4 (4.75 mm)", 30, 65), ("#10 (2.00 mm)", 20, 40),
          ("#40 (0.425 mm)", 8, 20), ("#200 (0.075 mm)", 5, 10)]


def _steel(fy_min, fy_max, ft_min, el_min, ratio):
    return [_L("Unit weight", "kg/m"), _L("Yield stress fy", "N/mm²", fy_min, fy_max), _L("Tensile strength ft", "N/mm²", ft_min),
            _L("Elongation (L0 = 10d)", "%", el_min), _L("Ratio TS/YS", None, ratio),
            _L("Bend test", kind="okng"), _L("Rebend test", kind="okng")]


# code, ar, en, material, standard, acceptance, samples hint, lines
DEFAULT_TEMPLATES = [
    ("concrete_cubes", "مكعبات الباطون – مقاومة الضغط", "Concrete cubes – compressive strength", "CON",
     "P.S. 55 / BS EN 12390-3", "concrete", "", []),
    ("concrete_slump", "الباطون الطازج – الهبوط والحرارة", "Fresh concrete – slump and temperature", "CON",
     "ASTM C143 / C1064", "all", "", [_L("Slump", "mm", 75, 125), _L("Concrete temperature", "°C", None, 32)]),
    ("steel_s500", "حديد التسليح S500", "Steel bars – S500 (P.S. 821-3)", "STL", "P.S. 821-3", "all", "Ø32,Ø25,Ø20,Ø16,Ø12",
     _steel(500, 600, 600, 10, 1.1)),
    ("steel_s400", "حديد التسليح S400", "Steel bars – S400 (P.S. 821-3)", "STL", "P.S. 821-3", "all", "Ø25,Ø20,Ø16,Ø12",
     _steel(400, 500, 500, 12, 1.25)),
    ("base_course", "مواد البيسكورس – مواصفات الأشغال", "Base course materials – MPWH", "BC",
     "ASTM C136, D4318, D2419 – MPWH", "all", "",
     [_L("Liquid limit", "%", None, 25, "Atterberg limits", "ASTM D4318"),
      _L("Plastic limit", "%", None, None, "Atterberg limits", "ASTM D4318"),
      _L("Plasticity index", "%", 2, 6, "Atterberg limits", "ASTM D4318"),
      _L("Sand equivalent", "%", 30, None, "Sand equivalent", "ASTM D2419")]
     + [_L(f"Passing {s}", "%", a, b, "Sieve analysis", "ASTM C136") for s, a, b in SIEVES]),
    ("field_compaction", "الدمك الحقلي (مخروط الرمل / النووي)", "Field compaction (sand cone / nuclear)", "BC",
     "ASTM D1556 / D6938", "all", "1,2,3",
     [_L("Dry density", "g/cm³"), _L("Moisture content", "%"), _L("Degree of compaction", "%", 98)]),
    ("soil_proctor_cbr", "التربة – بروكتر وCBR", "Soil – Proctor and CBR", "SOIL", "ASTM D1557 / D1883", "all", "",
     [_L("Maximum dry density", "g/cm³"), _L("Optimum moisture content", "%"), _L("CBR at 95% MDD", "%", 30)]),
    ("asphalt_marshall", "الأسفلت – مارشال واستخلاص", "Asphalt – Marshall and extraction", "ASP",
     "ASTM D6927 / D2172 – MPWH", "all", "",
     [_L("Bitumen content", "%", 4.5, 6.0), _L("Marshall stability", "kN", 8), _L("Flow", "mm", 2, 4),
      _L("Air voids", "%", 3, 5), _L("Voids in mineral aggregate (VMA)", "%", 13), _L("Voids filled with bitumen (VFB)", "%", 65, 75)]),
    ("asphalt_cores", "الأسفلت – عينات اللب (السماكة والدمك)", "Asphalt cores – thickness and compaction", "ASP",
     "ASTM D2726", "all", "1,2,3", [_L("Thickness", "cm", 5), _L("Degree of compaction", "%", 97)]),
    ("blocks", "الطوب الإسمنتي – مقاومة الضغط", "Concrete blocks – compressive strength", "BLK", "P.S. 4 / ASTM C140",
     "all", "1,2,3,4,5,6", [_L("Compressive strength", "N/mm²", 3.5), _L("Water absorption", "%", None, 10)]),
    ("tiles_bia", "بلاط البورسلان – ISO 13006 BIa", "Porcelain tiles – ISO 13006 Group BIa", "TIL", "ISO 13006 BIa", "all", "",
     [_L("Water absorption E", "%", None, 0.5), _L("Modulus of rupture", "MPa", 35), _L("Breaking strength", "N", 1300),
      _L("Deep abrasion", "mm³", None, 175)]),
    ("tiles_terrazzo", "بلاط الموزاييك والتيرازو", "Terrazzo tiles", "TIL", "P.S. 31 / EN 13748", "all", "",
     [_L("Water absorption", "%", None, 8), _L("Breaking strength", "N", 3000), _L("Abrasion (wear) depth", "mm", None, 2)]),
]


def default_templates() -> list[dict]:
    return [{"code": c, "name_ar": ar, "name_en": en, "material": m, "standard": std, "acceptance": acc,
             "samples": smp, "lines": lines} for c, ar, en, m, std, acc, smp, lines in DEFAULT_TEMPLATES]


# ----------------------------------------------------------------------------- results
def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def line_result(line: dict) -> str:
    """'pass' / 'fail' / 'na' (no limit or no value)."""
    if line.get("kind") == "okng":
        txt = (line.get("text") or "").strip().upper()
        if not txt:
            return "na"
        if txt in FAIL_WORDS:
            return "fail"
        return "pass" if txt in PASS_WORDS else "na"
    v, mn, mx = _num(line.get("value")), _num(line.get("min")), _num(line.get("max"))
    if v is None or (mn is None and mx is None):
        return "na"
    if (mn is not None and v < mn) or (mx is not None and v > mx):
        return "fail"
    return "pass"


def evaluate(lab: dict) -> dict:
    """Result of a certificate: per line, overall, and the concrete summary."""
    lines = lab.get("lines") or []
    results = [line_result(x) for x in lines]
    checked = [r for r in results if r in ("pass", "fail")]
    failed = results.count("fail")
    out = {"line_results": results, "result": None, "note": "", "checked": len(checked), "failed": failed,
           "strength_avg": None, "strength_min": None, "below": 0}
    s28 = [_num(x.get("value")) for x in lines if x.get("role") == "strength28" and _num(x.get("value")) is not None]
    fck = _num(lab.get("fck"))
    if lab.get("acceptance") == "concrete" and s28 and fck:
        avg, low = sum(s28) / len(s28), min(s28)
        mean_req = fck + (_num(lab.get("mean_margin")) or 0)
        marg = _num(lab.get("individual_margin"))
        marg = 4.0 if marg is None else marg
        ind_req = fck * marg / 100 if lab.get("individual_rule") == "percent" else fck - marg
        others = [r for x, r in zip(lines, results) if x.get("role") not in ("strength28", "strength7")]
        ok = avg >= mean_req and low >= ind_req and "fail" not in others
        below = len([v for v in s28 if v < fck])
        out.update(result="pass" if ok else "fail", strength_avg=round(avg, 1), strength_min=round(low, 1), below=below,
                   note=f"mean {avg:.1f} {'≥' if avg >= mean_req else '<'} {mean_req:.1f} · lowest {low:.1f} "
                        f"{'≥' if low >= ind_req else '<'} {ind_req:.1f} MPa" + (f" · {below} below {fck:g}" if below else ""))
    elif lab.get("acceptance") in ("all", "concrete") and checked:
        out.update(result="fail" if failed else "pass", note=f"{failed} / {len(checked)}")
    return out


def norm_grade(g: str | None) -> str:
    return re.sub(r"[\s\-_.]", "", (g or "").upper())


def grade_strength(g: str | None) -> float | None:
    """'B450' / 'B 300' (kg/cm² cube grades) -> 45 / 30 MPa."""
    m = re.match(r"^\s*B\s*-?\s*(\d{3})\s*$", g or "", re.I)
    return int(m.group(1)) / 10 if m else None


def match_class(classes: list, grade=None, fck=None, element=None, topic_id=None):
    """(class, how) for a concrete certificate: grade, then the request's topic, then fck, then element words."""
    if not classes:
        return None, ""
    g = norm_grade(grade)
    if g:
        hit = [c for c in classes if g in [norm_grade(c.grade)] + [norm_grade(x) for x in (c.aliases or "").split(",") if x.strip()]]
        if len(hit) == 1:
            return hit[0], "grade"
    if topic_id:
        hit = [c for c in classes if str(topic_id) in [str(t) for t in (c.topic_ids or [])]]
        if len(hit) == 1:
            return hit[0], "topic"
    cand = classes
    if fck:
        cand = [c for c in classes if abs(float(c.fck) - float(fck)) < 0.01]
        if len(cand) == 1:
            return cand[0], "strength"
    if element and cand:
        el = element.lower()
        hit = [c for c in cand if any(k.strip() and k.strip().lower() in el for k in (c.elements or "").split(","))]
        if len(hit) == 1:
            return hit[0], "element"
    if len(classes) == 1:
        return classes[0], "only"
    return None, ""


# ----------------------------------------------------------------------------- AI reading
def ai_enabled() -> bool:
    return bool(get_settings().ai_api_key)


def ai_prompt(template: dict | None, acceptance: str) -> str:
    known = ""
    if template and template.get("lines") and acceptance != "concrete":
        known = "\n".join(f'- sample "{x.get("sample") or ""}" | parameter "{x["parameter"]}" | unit "{x.get("unit") or ""}"'
                          for x in template["lines"][:300])
    name = template["name_en"] if template else "unknown"
    return f"""You are reading a construction-materials laboratory test certificate (scanned PDF, English and/or Arabic).
Extract the data EXACTLY as printed. Never invent values; use null when a value is not printed or not legible.

Test type in our system: {name}  (acceptance method: {acceptance})

The PDF may contain SEVERAL certificates (e.g. one per page, each with its own report number).
Return ALL of them, in page order, as ONLY one JSON object, no comments, with this structure:
{{"certificates": [ {{
  "page": int|null,
  "header": {{
    "lab_name": str|null, "lab_report_no": str|null, "report_date": "YYYY-MM-DD"|null,
    "sampling_date": "YYYY-MM-DD"|null, "test_date": "YYYY-MM-DD"|null,
    "grade": str|null, "specified_strength": number|null,
    "element": str|null, "quantity": number|null, "quantity_uom": str|null,
    "specimen_count": int|null, "specification": str|null,
    "lab_conclusion": "PASS"|"FAIL"|null
  }},
  "lines": [
    {{"sample": str|null, "parameter": str, "age_days": int|null, "value": number|null,
      "value_text": str|null, "unit": str|null, "min": number|null, "max": number|null, "legible": true|false}}
  ],
  "remarks": str|null
}} ]}}

Rules:
- Dates: the certificate uses day/month/year (e.g. 10-12-2024 = 2024-12-10).
- grade: exactly as printed (e.g. "B300", "B 450", "C30/37"); specified_strength in MPa (B450 -> 45).
- One line per measured value. "legible": false when you are not sure of a number.
- min / max: the specification limits printed on the certificate for that parameter (null if none).
- Concrete cube / cylinder certificates: one line per specimen AND per age. sample = specimen no. as printed
  (e.g. "1-1"), parameter = "Compressive strength 7-day" or "Compressive strength 28-day", age_days = 7 or 28,
  value = strength in MPa. Do not include the MINIMUM / MAXIMUM / AVERAGE summary rows.
- Results like OK / NOK / PASS: put them in value_text and leave value null.
- Steel: one line per bar diameter and parameter, sample = "Ø<diameter>" (e.g. "Ø32"); use the average row.
- lab_conclusion: only if the laboratory prints an overall conclusion / compliance statement.
- When a parameter matches one of the expected parameters below, use EXACTLY the same sample and parameter text:
{known or '(no expected list - use the parameter names printed on the certificate)'}
"""


def ai_call(pdf: bytes, prompt: str) -> tuple[dict, str]:
    s = get_settings()
    body = {"model": s.ai_model, "max_tokens": 16000, "messages": [{"role": "user", "content": [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                        "data": base64.b64encode(pdf).decode()}},
        {"type": "text", "text": prompt}]}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": s.ai_api_key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:  # noqa: S310 - fixed https URL
        data = json.loads(r.read())
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return parse_ai_json(text), s.ai_model


def parse_ai_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("ai_unreadable")
    return json.loads(m.group(0))


def _date(v):
    return v if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", v) else None


def drafts_from_ai(data: dict, lab: dict, classes: list, topic_id) -> list[dict]:
    """One draft per certificate found in the PDF (older single-certificate answers too)."""
    certs = data.get("certificates") if isinstance(data.get("certificates"), list) else [data]
    out = []
    for i, c in enumerate(certs):
        d = draft_from_ai(c, lab, classes, topic_id)
        d["page"] = c.get("page") or i + 1
        out.append(d)
    return out


def _class_names(c) -> list[str]:
    return [norm_grade(c.grade)] + [norm_grade(x) for x in (c.aliases or "").split(",") if x.strip()]


def draft_from_ai(data: dict, lab: dict, classes: list, topic_id) -> dict:
    """The values read, in our format, ready for review: header, lines with limits and roles, class found."""
    h = data.get("header") or {}
    raw = [x for x in (data.get("lines") or []) if (x.get("parameter") or "").strip()]
    has_strength = any("strength" in (x.get("parameter") or "").lower() and x.get("age_days") for x in raw)
    acceptance = "concrete" if has_strength else (lab.get("acceptance") or "all")
    cert_fck = _num(h.get("specified_strength")) or grade_strength(h.get("grade"))
    cls, how = (None, "")
    warnings = []
    if acceptance == "concrete":
        cls, how = match_class(classes, h.get("grade"), cert_fck, h.get("element"), topic_id)
        g = norm_grade(h.get("grade"))
        if g and cls and g not in _class_names(cls):
            # the certificate states a grade the project does not define: the topic must not decide silently
            cls, how = None, ""
        if g and not cls and classes:
            warnings.append("grade_unknown")
        if cls and cert_fck and abs(float(cls.fck) - cert_fck) > 0.01:
            warnings.append("strength_mismatch")
    fck = float(cls.fck) if cls else (cert_fck or _num(lab.get("fck")))
    known = {((x.get("sample") or "").strip().lower(), x["parameter"].strip().lower()): x for x in (lab.get("lines") or [])}
    lines = []
    for x in raw:
        param = x["parameter"].strip()
        age = int(_num(x.get("age_days")) or 0) or None
        role = None
        if acceptance == "concrete" and "strength" in param.lower():
            role = "strength28" if age == 28 else ("strength7" if age == 7 else None)
        mn, mx = _num(x.get("min")), _num(x.get("max"))
        match = known.get(((x.get("sample") or "").strip().lower(), param.lower()))
        if match and mn is None and mx is None:  # the project's limits when the certificate prints none
            mn, mx = _num(match.get("min")), _num(match.get("max"))
        if role == "strength28":
            mn, mx = fck, None
        elif role == "strength7":
            mn, mx = None, None
        text = x.get("value_text") or None
        lines.append({"sample": x.get("sample"), "parameter": param, "unit": x.get("unit") or (match or {}).get("unit"),
                      "method": (match or {}).get("method"), "age": age,
                      "kind": "okng" if text and _num(x.get("value")) is None else (match or {}).get("kind", "number"),
                      "value": _num(x.get("value")), "text": text, "min": mn, "max": mx, "role": role,
                      "legible": x.get("legible", True) is not False})
    concl = (h.get("lab_conclusion") or "").strip().lower()
    # the certificate names a grade the project has no class for: say so instead of judging silently
    g = norm_grade(h.get("grade"))
    known_grade = not g or any(g in [norm_grade(c.grade)] + [norm_grade(x) for x in (c.aliases or "").split(",") if x.strip()]
                               for c in classes)
    out = {"acceptance": acceptance, "lab_name": h.get("lab_name"), "grade_unknown": not known_grade, "lab_report_no": h.get("lab_report_no"),
           "report_date": _date(h.get("report_date")), "sampling_date": _date(h.get("sampling_date")),
           "test_date": _date(h.get("test_date")), "grade": cls.grade if cls else h.get("grade"),
           "cert_grade": h.get("grade"), "cert_strength": cert_fck, "fck": fck, "element": h.get("element"),
           "quantity": _num(h.get("quantity")), "quantity_uom": h.get("quantity_uom"),
           "specimen_count": int(_num(h.get("specimen_count")) or 0) or None, "specification": h.get("specification"),
           "lab_conclusion": concl if concl in ("pass", "fail") else None,
           "class_id": str(cls.id) if cls else None, "class_match": how, "warnings": warnings, "lines": lines,
           "remarks": data.get("remarks")}
    if cls:
        out.update(mean_margin=float(cls.mean_margin), individual_rule=cls.individual_rule,
                   individual_margin=float(cls.individual_margin))
    return out
