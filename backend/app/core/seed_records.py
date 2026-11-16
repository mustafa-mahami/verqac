"""Platform workflow and record type templates (design doc section 4, categories = dr status codes)."""

# state code, ar, en, category, colour, initial
REVIEW_STATES = [
    ("draft", "مسودة", "Draft", "draft", "gray", True),
    ("submitted", "مقدَّم", "Submitted", "submitted", "blue", False),
    ("approved", "معتمد", "Approved", "approved", "green", False),
    ("approved_as_noted", "معتمد مع ملاحظات", "Approved as noted", "approved_as_noted", "teal", False),
    ("revise_and_resubmit", "تعديل وإعادة تقديم", "Revise and resubmit", "revise_and_resubmit", "orange", False),
    ("rejected", "مرفوض", "Rejected", "rejected", "red", False),
    ("cancelled", "ملغى", "Cancelled", "cancelled", "dark", False),
]

# from, to, action, ar, en, permission, effect, requires_comment, style
REVIEW_TRANSITIONS = [
    ("draft", "submitted", "submit", "تقديم", "Submit", "submit", "submit", False, "primary"),
    ("submitted", "approved", "approve", "اعتماد", "Approve", "respond", "respond", False, "green"),
    ("submitted", "approved_as_noted", "approve_as_noted", "اعتماد مع ملاحظات", "Approve as noted", "respond",
     "respond", True, "teal"),
    ("submitted", "revise_and_resubmit", "revise", "تعديل وإعادة تقديم", "Revise and resubmit", "respond",
     "respond", True, "orange"),
    ("submitted", "rejected", "reject", "رفض", "Reject", "respond", "respond", True, "red"),
    ("draft", "cancelled", "cancel", "إلغاء", "Cancel", "cancel", "cancel", False, "subtle"),
    ("submitted", "cancelled", "cancel", "سحب وإلغاء", "Withdraw", "cancel", "cancel", True, "subtle"),
]

# inspection requests: the consultant inspects on site and accepts or asks for a re-inspection
INSPECTION_STATES = [
    ("draft", "مسودة", "Draft", "draft", "gray", True),
    ("submitted", "مقدَّم", "Submitted", "submitted", "blue", False),
    ("accepted", "مقبول", "Accepted", "approved", "green", False),
    ("accepted_with_comments", "مقبول مع ملاحظات", "Accepted with comments", "approved_as_noted", "teal", False),
    ("rejected", "مرفوض – يُعاد الفحص", "Rejected – re-inspect", "rejected", "red", False),
    ("cancelled", "ملغى", "Cancelled", "cancelled", "dark", False),
]
INSPECTION_TRANSITIONS = [
    ("draft", "submitted", "submit", "تقديم", "Submit", "submit", "submit", False, "primary"),
    ("submitted", "accepted", "accept", "قبول", "Accept", "respond", "respond", False, "green"),
    ("submitted", "accepted_with_comments", "accept_with_comments", "قبول مع ملاحظات", "Accept with comments",
     "respond", "respond", True, "teal"),
    ("submitted", "rejected", "reject", "رفض – يُعاد الفحص", "Reject – re-inspect", "respond", "respond", True, "red"),
    ("draft", "cancelled", "cancel", "إلغاء", "Cancel", "cancel", "cancel", False, "subtle"),
    ("submitted", "cancelled", "cancel", "سحب وإلغاء", "Withdraw", "cancel", "cancel", True, "subtle"),
]

# code, prefix, ar, en, workflow, review days (dr defaults), sort
RECORD_TYPES = [
    ("submittal", "SUB", "طلب اعتماد", "Submittal", "review", 14, 10),
]
INSPECTION_TYPE = ("inspection", "IR", "طلب فحص", "Inspection request", "inspection", 0, 20)

# default periods in hours: (consultant reply, contractor resubmission); projects change them in settings
DEFAULT_PERIODS = {"submittal": (7 * 24, 7 * 24), "inspection": (2, 2)}
