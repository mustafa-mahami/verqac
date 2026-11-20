"""Default suggestion lists of the daily report (Arabic / English), given to every new project and addable to an
existing one: supervision and contractor positions, labour trades and teams, equipment.

The English names include those used in Odoo's dr module, so a list imported from it gets its Arabic names."""
import re

SUPERVISION = [
    ("مدير المشروع (الإشراف)", "Supervision Project Manager"), ("المهندس المقيم", "Resident Engineer"),
    ("مهندس مدني", "Civil Engineer"), ("مهندس معماري", "Architect"), ("مهندس كهرباء", "Electrical Engineer"),
    ("مهندس ميكانيك", "Mechanical Engineer"), ("مهندس كهرباء أول", "Electrical Senior Engineer"),
    ("مهندس ميكانيك أول", "Mechanical Senior Engineer"), ("مهندس موقع", "Site Engineer"), ("مهندس كميات", "Quantity Surveyor"),
    ("مهندس سلامة", "Safety Engineer"), ("مراقب موقع", "Site Inspector"), ("مساح", "Surveyor"),
    ("مهندس جودة", "QA/QC Engineer"), ("مراقب كهرباء", "Electrical Inspector"), ("مراقب ميكانيك", "Mechanical Inspector"),
]
CONTRACTOR = [
    ("مدير المشروع", "Project Manager"), ("مهندس الموقع", "Site Engineer"), ("مهندس مدني", "Civil Engineer"),
    ("مهندس كهرباء", "Electrical Engineer"), ("مهندس ميكانيك", "Mechanical Engineer"),
    ("مهندس كهرباء أول", "Electrical Senior Engineer"), ("مهندس ميكانيك أول", "Mechanical Senior Engineer"),
    ("مهندس كميات", "Quantity Surveyor"), ("مهندس تخطيط", "Planning Engineer"), ("مهندس جودة", "QA/QC Engineer"),
    ("مهندس سلامة", "Safety Engineer"), ("مهندس مكتب فني", "Technical Office Engineer"), ("رسام", "Draftsman"),
    ("مساح", "Surveyor"), ("مشرف عمال (فورمن)", "Foreman"), ("أمين مستودع", "Storekeeper"),
    ("إداري / سكرتير", "Administrator"), ("مراسل", "Office Boy"), ("حارس", "Guard"),
]
LABOUR = [
    ("عمال عاديون", "Labourers"), ("عمال الشركة", "Company Labors"), ("عمال مهرة", "Skilled Labors"),
    ("حدّادو مسلح", "Steel Fixers"), ("فريق الحديد", "Steel Team"), ("نجّارو طوبار", "Carpenters"),
    ("فريق الهيكل (مقاول فرعي)", "Skeleton Subcontractor"), ("فريق الحفريات", "Excavation Team"), ("فريق الردم", "Backfilling works"),
    ("بنّاؤو طوب", "Block Masons"), ("قصّارون", "Plaster Masons"), ("فريق القصارة", "Plaster Team"),
    ("بلّيطون", "Tile Masons"), ("فريق الحجر", "Stone Masons"), ("فريق كوبينغ الحجر", "Stone coping team"),
    ("فريق العزل", "Insulation Team"), ("عمال العزل", "Insulation labours"), ("فريق المدّة (السكريد)", "Screed Team"),
    ("فريق الجبس والأسقف المستعارة", "False Ceiling Team"), ("فريق الجبس بورد", "Gypsum team"), ("فريق الدهان", "Painting team"),
    ("فريق الإيبوكسي", "Flooring Epoxy"), ("فريق الألمنيوم", "Aluminum Team"), ("فريق الحدادة", "Steel works team"),
    ("فريق الدرابزين", "Handrail Team"), ("فريق الأبواب", "Doors Team"), ("فريق HPL", "HPL team"),
    ("فريق الكهرباء", "Electrical Team"), ("مقاول الكهرباء الفرعي", "Electrical Subcontractor"),
    ("فريق الميكانيك", "Mechanical Team"), ("مقاول الميكانيك الفرعي", "Mechanical Subcontractor"),
    ("فريق التكييف VRF", "VRF Team"), ("فريق إطفاء الحريق", "Fire Fighting Team"), ("فريق عازل الحريق", "Fire stop team"),
    ("فريق المصاعد", "Elevator Installation Team"), ("فريق السقالات", "Scaffolding"), ("فريق المساحة", "Surveying team"),
    ("فريق السلامة", "Safety team"), ("فريق التنظيف", "Cleaning"), ("فريق الرش بالفوم", "Spray Foam Team"),
    ("فريق تنسيق الحدائق والطرق", "Landscape and Street"), ("فريق الأثاث", "Furnituring"),
]
EQUIPMENT = [
    ("رافعة برجية", "Tower Crane"), ("رافعة متحركة (كرين)", "Mobile Crane"), ("مضخة باطون", "Concrete pump"),
    ("هزاز باطون", "Concrete vibrator"), ("حفارة", "Excavator"), ("جرافة (بلدوزر)", "Bulldozer"), ("جي سي بي", "JCB"),
    ("بوب كات", "BobCAT"), ("شاحنة قلاب", "Dump Truck"), ("مدحلة", "Roller Compactor"), ("خلاطة باطون", "Concrete mixer truck"),
    ("مولد كهرباء", "Generator"), ("ضاغط هواء", "Air compressor"), ("رافعة شوكية", "Forklift"), ("سقالات", "Scaffolding"),
    ("شاحنة نفايات", "Garbage truck"), ("فنشر", "Finisher"),
]
DEFAULTS = {"supervision_desc": SUPERVISION, "contractor_desc": CONTRACTOR, "labour_desc": LABOUR, "equipment": EQUIPMENT}


def norm(s: str | None) -> str:
    """For comparing names: case, spaces, punctuation and a plural "s" do not make a different item."""
    s = re.sub(r"[\s\-_./()]+", " ", (s or "").casefold()).strip()
    s = re.sub(r"\b(sub) contractor\b", r"\1contractor", s)
    s = s.replace("labors", "labours").replace("labor", "labour")
    return re.sub(r"(?<=\w)s\b", "", s)


def item(ar: str, en: str) -> dict:
    return {"ar": ar, "en": en, "role_ar": None, "role_en": None, "active": True}


def initial_lists() -> dict:
    return {k: [item(ar, en) for ar, en in v] for k, v in DEFAULTS.items()}


def merge(lists: dict) -> tuple[dict, dict]:
    """The project's lists with the defaults added: an item already there (by either name) is not added again;
    an imported item with only an English name gets its Arabic one. Returns (lists, {"added": n, "translated": n})."""
    out = {k: [dict(x) for x in v] for k, v in (lists or {}).items()}
    rep = {"added": 0, "translated": 0}
    for key, rows in DEFAULTS.items():
        cur = out.setdefault(key, [])
        for ar, en in rows:
            hit = next((x for x in cur if norm(x.get("en")) == norm(en) or norm(x.get("ar")) == norm(ar)), None)
            if hit is None:
                cur.append(item(ar, en))
                rep["added"] += 1
            elif (hit.get("ar") or "") == (hit.get("en") or "") and norm(hit.get("en")) == norm(en):
                hit["ar"] = ar  # English only (as Odoo had it): now in Arabic too
                rep["translated"] += 1
    return out, rep


def dedupe(rows: list[dict]) -> list[dict]:
    """One item per name: the first wins, active ones before inactive ones."""
    seen, out = set(), []
    for x in sorted(rows, key=lambda x: not x.get("active", True)):
        keys = {k for k in (norm(x.get("ar")), norm(x.get("en"))) if k}
        if keys & seen:
            continue
        seen |= keys
        out.append(x)
    return out
