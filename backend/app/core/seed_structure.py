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
        ("الحفريات", "Excavation", W, 1), ("القواعد", "Foundations", W, 3),
        ("الهيكل الإنشائي", "Structure", P, 20), ("الطوب", "Block walls", P, 7),
        ("التمديدات الكهروميكانيكية الأولى", "MEP first fix", P, 5), ("القصارة", "Plaster", P, 8),
        ("العزل", "Insulation", P, 1), ("البلاط", "Tiles", P, 9),
        ("الأسقف المستعارة / الجبس", "False ceiling / Gypsum", P, 4),
        ("أعمال الألمنيوم والحديد", "Aluminum & Steel works", P, 4), ("الأبواب", "Doors", P, 3),
        ("الدهان", "Paint", P, 4), ("التشطيبات الكهروميكانيكية النهائية", "MEP second / final fix", P, 10),
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


# subjects under each building stage, by the stage's English name (template and existing projects)
TOPICS = {
    "Excavation": [("حفريات", "Excavation"), ("ردم ودك", "Backfill & compaction"), ("تسوية الموقع", "Site levelling")],
    "Foundations": [("خرسانة نظافة", "Blinding concrete"), ("قواعد", "Footings"), ("جسور أرضية", "Grade beams"),
                    ("عزل الأساسات", "Foundation waterproofing")],
    "Structure": [("حفريات", "Excavation"), ("قواعد", "Footings"), ("جسور أرضية", "Grade beams"),
                  ("جدران تسوية", "Basement walls"), ("خرسانة جاهزة", "Ready-mix concrete"),
                  ("حديد تسليح", "Reinforcement steel"), ("جدران خرسانية", "Concrete walls"), ("أعمدة", "Columns"),
                  ("أسقف", "Slabs"), ("جسور", "Beams"), ("أرضيات", "Ground slabs")],
    "Block walls": [("طوب إسمنتي", "Concrete blocks"), ("طوب جبس", "Gypsum blocks"),
                    ("طوب معزول", "Insulated blocks"), ("طوب أحمر", "Clay bricks")],
    "MEP first fix": [("تمديدات كهربائية", "Electrical conduits"), ("تمديدات صحية", "Plumbing pipes"),
                      ("مجاري تكييف", "HVAC ducts"), ("تمديدات إطفاء", "Fire-fighting pipes"),
                      ("تمديدات تيار خفيف", "Low-current conduits")],
    "Plaster": [("تأسيس القصارة", "Plaster base coat"), ("طبقة خشنة", "Scratch coat"),
                ("طبقة ناعمة", "Finish coat"), ("زوايا وشبك", "Corner beads & mesh")],
    "Insulation": [("عزل مائي", "Waterproofing"), ("عزل حراري", "Thermal insulation"), ("عزل صوتي", "Acoustic insulation")],
    "Tiles": [("بلاط بورسلان", "Porcelain tiles"), ("سيراميك", "Ceramic tiles"), ("رخام", "Marble"),
              ("بلاط خارجي", "External paving"), ("لاصق وروبة", "Adhesive & grout")],
    "False ceiling / Gypsum": [("جبس بورد", "Gypsum board"), ("بلاطات أسقف معلقة", "Ceiling tiles"),
                               ("هيكل معدني", "Metal framing")],
    "Aluminum & Steel works": [("شبابيك ألمنيوم", "Aluminum windows"), ("أبواب ألمنيوم", "Aluminum doors"),
                               ("درابزين", "Handrails"), ("حمايات", "Grilles")],
    "Doors": [("أبواب خشب", "Wooden doors"), ("أبواب حديد", "Steel doors"),
              ("أبواب مقاومة للحريق", "Fire-rated doors"), ("إكسسوارات الأبواب", "Ironmongery")],
    "Paint": [("معجون", "Putty"), ("دهان داخلي", "Interior paint"), ("دهان خارجي", "External paint"),
              ("دهان إيبوكسي", "Epoxy paint")],
    "MEP second / final fix": [("أدوات صحية", "Sanitary fixtures"), ("مفاتيح وأباريز", "Switches & sockets"),
                               ("وحدات إنارة", "Lighting fixtures"), ("لوحات كهرباء", "Distribution boards"),
                               ("وحدات تكييف", "HVAC units")],
    "Facade stone cladding": [("حجر الواجهات", "Facade stone"), ("تثبيت ميكانيكي", "Mechanical anchoring"),
                              ("ترويب الحجر", "Stone grouting")],
    "Curtain wall & Alucobond": [("واجهات زجاجية", "Curtain wall"), ("ألوكوبوند", "Alucobond cladding"), ("زجاج", "Glazing")],
    "Elevator": [("مصاعد", "Elevators"), ("سلالم متحركة", "Escalators")],
    "Site & external works": [("أسوار", "Fences"), ("ممرات وأرصفة", "Walkways"), ("تنسيق حدائق", "Landscaping"),
                              ("شبكات خارجية", "External networks")],
    "Fit-out (counters, partitions, joinery)": [("كاونترات", "Counters"), ("قواطع", "Partitions"),
                                                ("نجارة", "Joinery"), ("خزائن", "Cabinets")],
    "Staircases (finishes)": [("تكسية الأدراج", "Stair cladding"), ("درابزين الأدراج", "Stair handrails")],
}


def topics_for(name_en: str) -> list[dict]:
    return [{"name_ar": a, "name_en": e, "checklist": checklist_for(e)} for a, e in TOPICS.get(name_en, [])]


def default_types(org_id: uuid.UUID) -> list[ProjectType]:
    return [
        ProjectType(org_id=org_id, code=code, name_ar=ar, name_en=en, group_label_ar=g[0], group_label_en=g[1],
                    unit_label_ar=u[0], unit_label_en=u[1], sort=(i + 1) * 10,
                    stages=[{"name_ar": a, "name_en": e, "scope": sc, "weight": w, "topics": topics_for(e)}
                            for a, e, sc, w in stages],
                    units=[{"name_ar": a, "name_en": e} for a, e in units])
        for i, (code, ar, en, g, u, stages, units) in enumerate(PROJECT_TYPES)
    ]


def seed_project_types(db: Session, org_id: uuid.UUID) -> None:
    """Templates a new organization starts with: project types and laboratory test templates."""
    if db.scalar(select(ProjectType.id).where(ProjectType.org_id == org_id).limit(1)) is None:
        db.add_all(default_types(org_id))
    from app.core.lab import default_templates
    from app.models.lab import LabTemplate
    if db.scalar(select(LabTemplate.id).where(LabTemplate.org_id == org_id).limit(1)) is None:
        db.add_all([LabTemplate(org_id=org_id, sort=(i + 1) * 10, **{**t, "samples": t["samples"] or None})
                    for i, t in enumerate(default_templates())])


# inspection checklists by topic (English name): what the supervising engineer checks before accepting
_FORM = [("نظافة الشدّات ودهانها بالزيت", "Formwork clean and oiled"),
         ("الأبعاد والمناسيب حسب المخططات", "Dimensions and levels as per drawings"),
         ("استقامة الشدّات وثباتها ودعماتها", "Formwork aligned, rigid and propped")]
_REBAR = [("أقطار الحديد وأعداده حسب المخططات", "Bar sizes and numbers as per drawings"),
          ("المسافات بين القضبان", "Bar spacing"),
          ("أطوال التراكب والتثبيت", "Lap and anchorage lengths"),
          ("الكانات: القطر والمسافات والأكتاف", "Stirrups: size, spacing and hooks"),
          ("الغطاء الخرساني والكراسي (البسكوت)", "Concrete cover and spacers"),
          ("ربط الحديد ونظافته من الصدأ والزيوت", "Bars tied and free of rust and oil")]
_POUR = [("التمديدات والفتحات والجلب (sleeves) قبل الصب", "Sleeves, openings and embedded MEP before casting"),
         ("نظافة المكان من الأتربة والمخلفات", "Area clean of debris"),
         ("جاهزية الهزاز ومعدات الصب", "Vibrator and casting equipment ready")]
CHECKLISTS = {
    "Excavation": [("مناسيب الحفر حسب المخططات", "Excavation levels as per drawings"),
                   ("أبعاد الحفر والميول الجانبية", "Excavation dimensions and side slopes"),
                   ("طبيعة التربة وصلاحيتها للتأسيس", "Soil bearing stratum suitable"),
                   ("تسوية القاع ودكّه وخلوّه من المياه", "Bottom levelled, compacted and dry")],
    "Footings": [("صبّة النظافة: السماكة والمنسوب", "Blinding: thickness and level"),
                 ("محاور القواعد وتوقيعها", "Footing axes and setting out"), *_FORM, *_REBAR,
                 ("أشاير الأعمدة: العدد والمواقع والطول", "Column starter bars: number, position and length"),
                 ("العزل أسفل وجوانب القواعد", "Waterproofing under and around footings")],
    "Grade beams": [*_FORM, *_REBAR, ("العزل حسب المواصفات", "Waterproofing as specified")],
    "Basement walls": [*_FORM, *_REBAR, ("مانع تسرب المياه (water stop) في الفواصل", "Water stops at joints"),
                       ("براغي الشدّات والجلب", "Form ties and sleeves")],
    "Ready-mix concrete": [("مطابقة درجة الخرسانة لسند التوريد", "Concrete grade matches delivery note"),
                           ("فحص الهبوط (slump)", "Slump test"),
                           ("أخذ المكعبات وترقيمها", "Cubes taken and labelled"),
                           ("زمن النقل والصب ضمن الحدود", "Transit and placing time within limits"),
                           ("درجة الحرارة وإجراءات الطقس", "Temperature and weather precautions"),
                           ("طريقة الصب والدمك بالهزاز", "Placing method and vibration"),
                           ("خطة المعالجة بعد الصب", "Curing arrangements")],
    "Reinforcement steel": _REBAR,
    "Concrete walls": [*_FORM, *_REBAR, ("براغي الشدّات والجلب", "Form ties and sleeves")],
    "Columns": [("محاور الأعمدة وتوقيعها", "Column axes and setting out"),
                ("الشاقولية وأبعاد المقطع", "Plumb and section dimensions"), *_REBAR[:2], *_REBAR[3:],
                ("التراكب مع الأشاير", "Lap with starter bars"), ("نظافة القاعدة من الأسفل قبل الصب", "Base cleaned before casting")],
    "Slabs": [*_FORM, ("الطوبار الخشبي/المعدني والدعامات حسب التصميم", "Shoring and props as designed"),
              ("الطوب الهوردي: المواقع والاتجاه", "Hollow blocks: layout and direction"), *_REBAR, *_POUR,
              ("منسوب السقف وميوله", "Slab level and falls")],
    "Beams": [*_FORM, *_REBAR, *_POUR[:2]],
    "Ground slabs": [("دكّ الردم وفحص الكثافة", "Fill compaction and density test"),
                     ("البولي إيثيلين / العزل أسفل البلاطة", "Polythene / membrane under slab"),
                     ("شبك الحديد والغطاء", "Mesh and cover"), ("المناسيب والفواصل", "Levels and joints")],
    "Concrete blocks": [("نوع الطوب وأبعاده حسب المعتمد", "Block type and size as approved"),
                        ("الاستقامة والشاقولية", "Line and plumb"), ("تعاشق الصفوف وسماكة المونة", "Bond and mortar joints"),
                        ("الربط مع الأعمدة (شبك/أشاير)", "Ties to columns"), ("الأعتاب فوق الفتحات", "Lintels over openings"),
                        ("أبعاد الفتحات ومواقعها", "Opening sizes and positions")],
    "Electrical conduits": [("أقطار المواسير ونوعها حسب المعتمد", "Conduit size and type as approved"),
                            ("مسارات التمديد حسب المخططات", "Routes as per drawings"),
                            ("العلب ومناسيبها", "Boxes and their heights"), ("التثبيت والحماية قبل الصب/القصارة", "Fixing and protection before casting/plaster"),
                            ("سحب السلك الدليل", "Draw wire installed")],
    "Plumbing pipes": [("نوع الأنابيب وأقطارها حسب المعتمد", "Pipe type and size as approved"),
                       ("الميول للصرف", "Drainage falls"), ("التثبيت والدعامات", "Fixing and supports"),
                       ("فحص الضغط/الامتلاء", "Pressure / water test"), ("مواقع المخارج ومناسيبها", "Outlet positions and heights")],
    "HVAC ducts": [("أبعاد المجاري ومساراتها", "Duct sizes and routes"), ("العزل وإحكام الوصلات", "Insulation and sealed joints"),
                   ("التعليقات والدعامات", "Hangers and supports")],
    "Plaster base coat": [("استلام التمديدات قبل القصارة", "MEP signed off before plaster"),
                          ("ترطيب الجدران وتنظيفها", "Walls cleaned and wetted"),
                          ("الزوايا والشبك عند تلاقي المواد", "Beads and mesh at material joints"),
                          ("الأوتار والقِدّات (المسطرة)", "Screeds and guides")],
    "Finish coat": [("الاستقامة والشاقولية (القدة 2م)", "Flatness and plumb (2 m straightedge)"),
                    ("الزوايا حادة ومستقيمة", "Sharp straight corners"), ("خلو السطح من الشروخ", "Free of cracks"),
                    ("المعالجة بالرش", "Curing")],
    "Waterproofing": [("تنظيف السطح وجفافه", "Surface clean and dry"), ("البرايمر", "Primer applied"),
                      ("التراكبات وعدد الطبقات", "Overlaps and number of layers"),
                      ("الوزرات والقلبات عند الجدران", "Upturns at walls"), ("حول المصارف والفتحات", "Around drains and penetrations"),
                      ("فحص الغمر بالماء 48 ساعة", "48-hour flood test")],
    "Thermal insulation": [("نوع العازل وسماكته حسب المعتمد", "Insulation type and thickness as approved"),
                           ("التغطية الكاملة دون فراغات", "Full coverage without gaps"), ("التثبيت", "Fixing")],
    "Porcelain tiles": [("نوع البلاط ولونه حسب العينة المعتمدة", "Tile type and colour as approved sample"),
                        ("المناسيب والميول", "Levels and falls"), ("الاستواء وعدم وجود فراغات (طرق)", "Flatness and no hollows (tap test)"),
                        ("عرض الفواصل واستقامتها", "Joint width and alignment"), ("القص عند الأطراف والزوايا", "Cuts at edges and corners"),
                        ("الوزرة", "Skirting")],
    "Ceramic tiles": [("نوع البلاط ولونه حسب العينة المعتمدة", "Tile type and colour as approved sample"),
                      ("الشاقولية والاستواء", "Plumb and flatness"), ("عرض الفواصل واستقامتها", "Joint width and alignment"),
                      ("القص حول الأدوات الصحية والمخارج", "Cuts around fixtures and outlets")],
    "Gypsum board": [("الهيكل المعدني: المسافات والتعليقات", "Framing: spacing and hangers"),
                     ("استلام التمديدات فوق السقف", "Above-ceiling MEP signed off"),
                     ("المنسوب والاستواء", "Level and flatness"), ("فتحات الصيانة والإنارة", "Access panels and light openings"),
                     ("معالجة الفواصل والبراغي", "Joint and screw finishing")],
    "Aluminum windows": [("مطابقة القطاعات والزجاج للمعتمد", "Profiles and glass as approved"),
                         ("الأبعاد والشاقولية", "Dimensions and plumb"), ("التثبيت والمسافات بين البراغي", "Fixing and anchor spacing"),
                         ("السيليكون والإحكام", "Sealant and weather-tightness"), ("الحركة والإكسسوارات", "Operation and hardware")],
    "Interior paint": [("تجهيز السطح والمعجون والصنفرة", "Surface prep, putty and sanding"),
                       ("نوع الدهان ولونه حسب المعتمد", "Paint type and colour as approved"),
                       ("عدد الطبقات", "Number of coats"), ("خلو السطح من العيوب والتموجات", "Free of defects and waviness")],
}


def checklist_for(name_en: str) -> list[dict]:
    return [{"ar": a, "en": e} for a, e in CHECKLISTS.get(name_en, [])]
