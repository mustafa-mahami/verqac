"""Default project types and their templates, given to every organization (editable afterwards)."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.structure import ProjectType

W = "whole"
P = "per_location"
FLOORS = [("التسوية", "Basement"), ("الطابق الأرضي", "Ground floor"), ("الطابق الأول", "First floor"),
          ("الطابق الثاني", "Second floor"), ("الطابق الثالث", "Third floor"), ("السطح", "Roof")]

# code, ar, en, (group ar, en), (unit ar, en), stages [(ar, en, scope, weight)], units
PROJECT_TYPES = [
    ("buildings", "أبنية", "Buildings", ("مبنى", "Building"), ("طابق", "Floor"), [
        ("الهيكل الإنشائي", "Structure", P, 20), ("الطوب", "Block walls", P, 8),
        ("التمديدات الكهروميكانيكية الأولى", "MEP first fix", P, 6), ("القصارة", "Plaster", P, 8),
        ("العزل", "Insulation", P, 4), ("البلاط", "Tiles", P, 9),
        ("الأسقف المستعارة / الجبس", "False ceiling / Gypsum", P, 4),
        ("أعمال الألمنيوم والحديد", "Aluminum & Steel works", P, 5), ("الأبواب", "Doors", P, 3),
        ("الدهان", "Paint", P, 4), ("التشطيبات الكهروميكانيكية النهائية", "MEP second / final fix", P, 8),
        ("تكسية الحجر للواجهات", "Facade stone cladding", P, 4),
        ("الواجهات الزجاجية والألوكوبوند", "Curtain wall & Alucobond", P, 4), ("المصاعد", "Elevator", W, 2),
        ("الموقع والأعمال الخارجية", "Site & external works", W, 3),
        ("التجهيزات الداخلية (كاونترات، قواطع، نجارة)", "Fit-out (counters, partitions, joinery)", P, 3),
        ("تشطيبات الأدراج", "Staircases (finishes)", W, 5),
    ], FLOORS),
    ("roads", "طرق", "Roads", ("طريق", "Road"), ("مقطع", "Section"), [
        ("المساحة والتوقيع", "Survey & setting out", P, 5), ("الحفريات والردم", "Earthworks", P, 15),
        ("طبقة الأساس الترابية", "Subgrade", P, 15), ("طبقة الأساس الحصوية", "Base course", P, 20),
        ("الإسفلت", "Asphalt", P, 25), ("الأرصفة والأطاريف", "Curbs & sidewalks", P, 10),
        ("الإشارات والدهانات الأرضية", "Road furniture & marking", P, 10),
    ], [("0+000 – 0+500", "0+000 – 0+500"), ("0+500 – 1+000", "0+500 – 1+000")]),
    ("water_sewage", "مياه ومجاري", "Water & sewage", ("منطقة", "Zone"), ("خط", "Line"), [
        ("الحفريات", "Excavation", P, 20), ("تمديد الأنابيب", "Pipe laying", P, 35), ("المناهل", "Manholes", P, 15),
        ("الفحص والاختبار", "Testing", P, 10), ("الردم", "Backfill", P, 10), ("إعادة الوضع", "Reinstatement", P, 10),
    ], []),
    ("electromechanical", "كهرباء وميكانيك", "Electromechanical", ("مبنى", "Building"), ("طابق", "Floor"), [
        ("التمديدات الأولى", "First fix", P, 30), ("تركيب المعدات", "Equipment installation", P, 40),
        ("التشطيبات النهائية", "Second fix", P, 15), ("الفحص والتشغيل", "Testing & commissioning", W, 15),
    ], FLOORS),
    ("steel_works", "أعمال معدنية", "Steel works", ("منطقة", "Zone"), ("قسم", "Part"), [
        ("التصنيع", "Fabrication", P, 40), ("التركيب", "Installation", P, 40), ("الدهان والحماية", "Painting & coating", P, 20),
    ], []),
    ("solar", "طاقة شمسية", "Solar energy", ("موقع", "Site"), ("مصفوفة", "Array"), [
        ("الهياكل الحاملة", "Mounting structure", P, 25), ("الألواح", "Panels", P, 30),
        ("المحولات والأعمال الكهربائية", "Inverters & electrical", P, 25), ("الفحص والتشغيل", "Testing & commissioning", W, 20),
    ], []),
]


def default_types(org_id: uuid.UUID) -> list[ProjectType]:
    return [
        ProjectType(org_id=org_id, code=code, name_ar=ar, name_en=en, group_label_ar=g[0], group_label_en=g[1],
                    unit_label_ar=u[0], unit_label_en=u[1], sort=(i + 1) * 10,
                    stages=[{"name_ar": a, "name_en": e, "scope": sc, "weight": w} for a, e, sc, w in stages],
                    units=[{"name_ar": a, "name_en": e} for a, e in units])
        for i, (code, ar, en, g, u, stages, units) in enumerate(PROJECT_TYPES)
    ]


def seed_project_types(db: Session, org_id: uuid.UUID) -> None:
    if db.scalar(select(ProjectType.id).where(ProjectType.org_id == org_id).limit(1)) is None:
        db.add_all(default_types(org_id))
