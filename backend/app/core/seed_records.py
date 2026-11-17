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

# RFI: the contractor asks, the consultant answers (one answer; a new question is a new RFI)
RFI_STATES = [
    ("draft", "مسودة", "Draft", "draft", "gray", True),
    ("submitted", "مقدَّم", "Submitted", "submitted", "blue", False),
    ("answered", "تمت الإجابة", "Answered", "approved", "green", False),
    ("cancelled", "ملغى", "Cancelled", "cancelled", "dark", False),
]
RFI_TRANSITIONS = [
    ("draft", "submitted", "submit", "تقديم", "Submit", "submit", "submit", False, "primary"),
    ("submitted", "answered", "answer", "إرسال الإجابة", "Send answer", "respond", "respond", True, "green"),
    ("draft", "cancelled", "cancel", "إلغاء", "Cancel", "cancel", "cancel", False, "subtle"),
    ("submitted", "cancelled", "cancel", "سحب وإلغاء", "Withdraw", "cancel", "cancel", True, "subtle"),
]

# NCR: the consultant issues it, the contractor proposes the corrective action, the consultant
# verifies it on site and closes it or reopens it
NCR_STATES = [
    ("draft", "مسودة", "Draft", "draft", "gray", True),
    ("open", "مفتوح – بانتظار الإجراء", "Open – awaiting action", "submitted", "red", False),
    ("action_proposed", "تم الرد – بانتظار التحقق", "Action proposed – to verify", "responded", "orange", False),
    ("closed", "مغلق", "Closed", "approved", "green", False),
    ("cancelled", "ملغى", "Cancelled", "cancelled", "dark", False),
]
NCR_TRANSITIONS = [
    ("draft", "open", "issue", "إصدار", "Issue", "submit", "submit", False, "primary"),
    ("open", "action_proposed", "propose_action", "إرسال الإجراء التصحيحي", "Send corrective action", "respond",
     "respond", True, "orange"),
    ("action_proposed", "closed", "close", "تحقق وإغلاق", "Verify and close", "submit", "none", False, "green"),
    ("action_proposed", "open", "reopen", "إعادة فتح", "Reopen", "submit", "submit", True, "red"),
    ("draft", "cancelled", "cancel", "إلغاء", "Cancel", "cancel", "cancel", False, "subtle"),
    ("open", "cancelled", "cancel", "سحب وإلغاء", "Withdraw", "cancel", "cancel", True, "subtle"),
]

# code, prefix, ar, en, workflow, creator, responder, has revisions, sort
MORE_TYPES = [
    ("material", "MIR", "فحص مواد موردة", "Material inspection", "inspection", "contractor", "consultant", True, 25),
    ("rfi", "RFI", "طلب استيضاح", "Request for information", "rfi", "contractor", "consultant", False, 30),
    ("ncr", "NCR", "تقرير عدم مطابقة", "Non-conformance report", "ncr", "consultant", "contractor", False, 40),
]

# default periods in hours: (reply, resubmission); projects change them in settings
DEFAULT_PERIODS = {"submittal": (7 * 24, 7 * 24), "inspection": (2, 2), "material": (24, 48),
                   "rfi": (3 * 24, 3 * 24), "ncr": (3 * 24, 3 * 24)}

# types with an inspection time (asked for / performed) and that link approved submittals
TIMED_TYPES = ("inspection", "material")

# extra fields kept in records.custom, per type
CUSTOM_FIELDS = {"rfi": ("proposed", "impact"), "material": ("delivery_note", "storage"),
                 "ncr": ("severity", "required_action")}
