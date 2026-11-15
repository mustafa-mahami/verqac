"""Platform templates seeded by the first migration and copied for every new organization.

Roles follow design doc section 3. Record type codes are the ones of section 4.
"""

RECORD_TYPES = ("submittal", "inspection", "rfi", "test", "ncr", "daily_report", "document")

VIEW_ONLY = ("view", "export")
AUTHOR = ("view", "create", "edit", "submit", "cancel", "export")

# code, party, name_ar, name_en, flags, [(record_type, actions, scope)]
PLATFORM_ROLES = [
    ("contractor_pm", "contractor", "مدير المشروع", "Project Manager",
     {"manage_project": True, "manage_team": True},
     [("*", ("view", "create", "edit", "submit", "cancel", "delete", "export"), "project")]),
    ("qa_engineer", "contractor", "مهندس الجودة", "QA/QC Engineer", {},
     [("*", AUTHOR, "disciplines")]),
    ("site_engineer", "contractor", "مهندس الموقع", "Site Engineer", {},
     [("*", ("view",), "disciplines"),
      ("daily_report", AUTHOR, "disciplines"),
      ("inspection", ("view", "create", "edit", "submit"), "disciplines")]),
    ("document_controller", "contractor", "مراقب الوثائق", "Document Controller", {},
     [("*", AUTHOR, "project")]),
    ("contractor_readonly", "contractor", "قراءة فقط", "Read Only", {},
     [("*", VIEW_ONLY, "project")]),
    ("consultant_pm", "consultant", "مدير مشروع الاستشاري", "Consultant Project Manager",
     {"manage_team": True, "act_on_behalf": True},
     [("*", ("view", "respond", "export"), "project"),
      ("ncr", AUTHOR, "project")]),
    ("consultant_engineer", "consultant", "مهندس استشاري", "Consultant Engineer", {},
     [("*", ("view", "respond", "export"), "disciplines"),
      ("ncr", AUTHOR, "disciplines")]),
    ("owner_rep", "owner", "ممثل المالك", "Owner's Representative", {},
     [("*", VIEW_ONLY, "project")]),
]

DEFAULT_DISCIPLINES = [
    ("C", "مدني", "Civil"),
    ("A", "معماري", "Architectural"),
    ("E", "كهرباء", "Electrical"),
    ("M", "ميكانيك", "Mechanical"),
    ("P", "صحي", "Plumbing"),
    ("G", "عام", "General"),
]
