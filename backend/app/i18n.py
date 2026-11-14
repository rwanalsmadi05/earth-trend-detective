"""English / Arabic strings for the AI partner and templates. Arabic uses Western digits (0-9), as is usual in Jordan."""
import re

LABEL_AR = {
    "T2M": "درجة الحرارة", "T2M_MAX": "الحرارة العظمى", "PRECTOTCORR": "الأمطار",
    "GWETROOT": "رطوبة التربة (منطقة الجذور)", "GWETTOP": "رطوبة سطح التربة", "RH2M": "الرطوبة النسبية",
    "ALLSKY_SFC_SW_DWN": "الإشعاع الشمسي", "NDVI": "الغطاء النباتي (NDVI)", "HOT_DAYS": "الأيام شديدة الحرارة",
}
REASON_AR = {
    "T2M": "الهواء الأكثر حرارة يسحب مزيداً من الماء من التربة والمياه المكشوفة.",
    "T2M_MAX": "الذروات اليومية للحرارة تكشف إجهاداً حرارياً قد تخفيه المتوسطات.",
    "PRECTOTCORR": "المطر هو ما يعيد ملء الأرض بالماء، وإذا كان المكان يجفّ فالمطر هو المشتبه الأول.",
    "GWETROOT": "رطوبة التربة تُظهر إن كانت الأرض ما زالت تحتفظ بالماء لجذور النباتات.",
    "GWETTOP": "الطبقة السطحية من التربة تتأثر أسرع بالمطر والحرارة.",
    "RH2M": "الهواء الجاف يزيد التبخر.",
    "ALLSKY_SFC_SW_DWN": "ضوء الشمس يقود التسخين والتبخر.",
    "NDVI": "النباتات هي الشاهد المرئي: يبهت اللون الأخضر عندما يشحّ الماء. (سجل الأقمار الصناعية يبدأ عام 2000.)",
    "HOT_DAYS": "عدّ الأيام شديدة الحرارة يُظهر كم مرة تشتد الحرارة.",
}
# short noun phrases for Arabic headlines ("<noun> أقل بنسبة 34% منذ 1981")
NOUN_AR = {
    "PRECTOTCORR": "الأمطار", "GWETROOT": "رطوبة التربة تحت الجذور", "GWETTOP": "رطوبة التربة السطحية",
    "RH2M": "الرطوبة النسبية", "ALLSKY_SFC_SW_DWN": "الإشعاع الشمسي", "NDVI": "الغطاء النباتي",
    "T2M": "درجة الحرارة", "T2M_MAX": "الحرارة العظمى", "HOT_DAYS": "الأيام فوق 35 °م",
}
PHRASE_AR = {  # (up, down) for the case headline
    "T2M": ("أكثر حرارة", "أبرد"), "T2M_MAX": ("ذروات حرارة أعلى", "ذروات حرارة أدنى"),
    "HOT_DAYS": ("أيام حر شديد أكثر", "أيام حر شديد أقل"), "PRECTOTCORR": ("أمطار أكثر", "أمطار أقل"),
    "GWETROOT": ("تربة أرطب", "تربة أجفّ"), "GWETTOP": ("تربة سطحية أرطب", "تربة سطحية أجفّ"),
    "RH2M": ("هواء أرطب", "هواء أجفّ"), "ALLSKY_SFC_SW_DWN": ("شمس أكثر", "شمس أقل"),
    "NDVI": ("نباتات أكثر", "نباتات أقل"),
}
VERDICT_AR = {"CONFIRMED": "مؤكَّد", "NOT PROVEN": "غير مثبت"}

_AR = re.compile(r"[؀-ۿ]")
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def detect_language(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    return "ar" if letters and sum(1 for c in letters if _AR.match(c)) / len(letters) > 0.3 else "en"


def ascii_digits(text: str) -> str:
    return text.translate(_ARABIC_INDIC)


def headline_ar(vid, direction, total_change, pct_change, first_year, verdict, reason=None):
    more = direction == "up"
    if reason:
        return f"تعذّر إجراء اختبار الاتجاه لـ{NOUN_AR[vid]}: غير مثبت"
    if verdict == "NOT PROVEN":
        return f"لا يوجد تغيّر واضح في {NOUN_AR[vid]} منذ {first_year} (قد يكون صدفة)"
    if vid in ("T2M", "T2M_MAX"):
        return f"{'أدفأ' if more else 'أبرد'} بمقدار {abs(total_change):.1f} °م منذ {first_year}"
    if vid == "HOT_DAYS":
        return f"{abs(total_change):.0f} يوماً {'أكثر' if more else 'أقل'} فوق 35 °م في السنة منذ {first_year}"
    return f"{NOUN_AR[vid]} {'أكثر' if more else 'أقل'} بنسبة {abs(pct_change):.0f}% منذ {first_year}"


def _join_ar(items):
    return items[0] if len(items) == 1 else "، ".join(items[:-1]) + " و" + items[-1]


def case_headline_ar(witnesses, expert, place_ar):
    total = len(witnesses)
    sig_w = [w for w in witnesses if w["verdict"] == "CONFIRMED"]
    if not sig_w:
        return f"لا يُظهر أي شاهد تغيّراً ذا دلالة إحصائية في {place_ar} (0 من {total})"
    phr = [PHRASE_AR[w["variable"]][0 if w["direction"] == "up" else 1] for w in sig_w]
    out = f"{len(sig_w)} من {total} شهود يُظهرون تغيّراً ذا دلالة إحصائية في {place_ar}: {_join_ar(phr)}"
    border = [f"{PHRASE_AR[w['variable']][0 if w['direction'] == 'up' else 1]} (p = {w['stats']['p']:.2g})"
              for w in sig_w if expert[w["variable"]]["borderline"]]
    return out + (f". حدّيّ: {_join_ar(border)}" if border else "")
