"""
data_processing.py
-------------------
Person 1 (Absher RAG improvement) — Step 1: raw data inspection + structuring.

What this module does
======================
1. `load_raw_documents()` walks `data/raw/text/*.txt` (faithful plain-text
   transcriptions of the official Absher PDFs Jawaher uploaded) and returns
   them with their provenance metadata (source filename, service name,
   document type). This is the audit trail: every fact used anywhere
   downstream can be traced back to one of these files, which can in turn be
   traced back to the original PDF in `data/raw/pdfs/`.

2. `SERVICES` is the curated, structured knowledge base built FROM those raw
   files. The corpus is small and fixed (4 services, 7 source documents), so
   structuring was done by direct editorial review of the raw text rather
   than by a regex/NLP parser — this keeps the pipeline simple, transparent,
   and easy for a teammate to audit line-by-line against
   `data/raw/text/*.txt`, per the project's "keep the MVP simple, do not
   over-engineer" constraint. Nothing in `SERVICES` was invented: every
   string is copied or lightly reformatted from a raw text file, and every
   record names its `source_files`.

3. `save_processed_documents()` writes `data/processed/documents.json`, the
   input `chunking.py` consumes.

UPDATED with the new Absher dataset: all 6 services Jawaher originally
scoped are now in `SERVICES` (previously only 4 — lost/stolen plate report
and firearm transport permit had no accessible official source and were
excluded; both now have real official source pages, see
`data/raw/SOURCES_MANIFEST.md`). The exit/reentry-or-final-exit-visa service
was previously `data_completeness="faq_only"` (FAQ page only, no steps); the
new source includes its full detailed service page, so it is now "full"
like the others. Nothing here was invented: every string is copied or
lightly reformatted (steps grouped into logical phases, matching this
file's existing pattern) from the verified new Absher source data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_TEXT_DIR = BASE_DIR / "data" / "raw" / "text"
PROCESSED_DIR = BASE_DIR / "data" / "processed"


# --------------------------------------------------------------------------
# 1. Raw document loading (provenance / audit trail)
# --------------------------------------------------------------------------

@dataclass
class RawDocument:
    filename: str
    source_file: str = ""
    service_ar: str = ""
    service_en: str = ""
    doc_type: str = ""
    raw_text: str = ""


_HEADER_PATTERNS = {
    "source_file": re.compile(r"^SOURCE FILE:\s*(.+)$", re.MULTILINE),
    "service_ar": re.compile(r"^SERVICE \(AR\):\s*(.+)$", re.MULTILINE),
    "service_en": re.compile(r"^SERVICE \(EN\):\s*(.+)$", re.MULTILINE),
    "doc_type": re.compile(r"^DOCUMENT TYPE:\s*(.+)$", re.MULTILINE),
}


def load_raw_documents(raw_text_dir: Path = RAW_TEXT_DIR) -> List[RawDocument]:
    """Read every *.txt transcription and pull out its provenance header."""
    docs: List[RawDocument] = []
    for path in sorted(raw_text_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        doc = RawDocument(filename=path.name, raw_text=text)
        for field_name, pattern in _HEADER_PATTERNS.items():
            m = pattern.search(text)
            if m:
                setattr(doc, field_name, m.group(1).strip())
        docs.append(doc)
    return docs


def inspect_raw_documents(raw_text_dir: Path = RAW_TEXT_DIR) -> None:
    """Print a short inventory of what was found (used by evaluation/README)."""
    docs = load_raw_documents(raw_text_dir)
    print(f"Found {len(docs)} raw text sources in {raw_text_dir}\n")
    for d in docs:
        print(f"- {d.filename}")
        print(f"    source PDF : {d.source_file}")
        print(f"    service    : {d.service_ar} / {d.service_en}")
        print(f"    doc type   : {d.doc_type}")
        print(f"    length     : {len(d.raw_text)} chars")


# --------------------------------------------------------------------------
# 2. Curated structured knowledge base (built from the raw files above)
# --------------------------------------------------------------------------

@dataclass
class FaqItem:
    question_ar: str
    answer_ar: str
    question_en: str = ""
    answer_en: str = ""


@dataclass
class StepPhase:
    phase_id: str
    title_ar: str
    title_en: str
    text_ar: str


@dataclass
class ServiceRecord:
    service_id: str
    service_name_ar: str
    service_name_en: str
    category_ar: str
    category_en: str
    data_completeness: str  # "full" (guide+faq) or "faq_only"
    source_files: List[str]
    definition_ar: str
    platform: str = "Absher"  # which of the 4 MVP platforms (Absher /
        # Sakani / Najiz / Balady) this service belongs to. Defaults to
        # "Absher" since that's the only platform with real data today —
        # every ServiceRecord in SERVICES below is unaffected by this
        # default and needs no changes. Sakani/Najiz/Balady data would
        # set this explicitly once that data exists.
    conditions_ar: List[str] = field(default_factory=list)
    steps: List[StepPhase] = field(default_factory=list)
    fees_notes_ar: str = ""
    delivery_notes_ar: str = ""
    important_notes_ar: List[str] = field(default_factory=list)
    faq: List[FaqItem] = field(default_factory=list)


SERVICES: List[ServiceRecord] = [
    # ---------------------------------------------------------------- 1 --
    ServiceRecord(
        service_id='driving_license_renewal',
        service_name_ar='تجديد رخصة القيادة',
        service_name_en='Driving License Renewal',
        category_ar='المرور',
        category_en='Traffic',
        data_completeness='full',
        source_files=[
            'driving_license_renewal_guide.txt',
            'driving_license_renewal_faq.txt',
        ],
        definition_ar='تُتيح هذه الخدمة للأفراد تجديد رخصة القيادة إلكترونيًا بكل يسر وسرعة، دون الحاجة إلى زيارة مكاتب المرور، مما يوفّر الوقت والجهد. ويشترط للاستفادة من الخدمة استكمال المتطلبات النظامية، مثل سداد الرسوم وإجراء الفحص الطبي.',
        conditions_ar=[
            'تشمل هذه الخدمة تجديد رخصة القيادة من نوع خصوصي، والدراجات الآلية فقط.',
            'سداد رسوم تجديد الرخصة من خلال المدفوعات الحكومية عبر البنوك.',
            'سداد المخالفات المرورية؛ إن وجدت.',
            'أن تكون المدة المتبقية من صلاحية رخصة القيادة أقل من 365 يومًا.',
            'وجود فحص طبي من أحد المراكز الطبية المعتمدة.',
        ],
        steps=[
        StepPhase(
            'access', 'الوصول إلى الخدمة', 'Accessing the service',
            'الدخول إلى موقع منصة أبشر، ثم اختيار "خدماتي"، ثم اختيار "المرور" من قائمة الخدمات، ثم اختيار خدمة "تجديد رخصة القيادة".',
        ),
        StepPhase(
            'eligibility_confirm', 'الشروط ومدة التجديد والتأكيد', 'Reading conditions, selecting renewal duration, and confirming',
            'قراءة وصف الخدمة وشروطها وأحكامها، ثم اختيار "التالي"، ثم مراجعة البيانات الشخصية وتحديد عدد سنوات التجديد (سنتين أو 5 سنوات أو 10 سنوات)، ثم ثم اختيار "تأكيد التجديد".',
        ),
        StepPhase(
            'delivery_address', 'تعبئة عنوان التوصيل', 'Filling in the delivery address',
            'تعبئة بيانات العنوان الوطني لطلب توصيل الرخصة.',
        ),
        StepPhase(
            'payment_delivery', 'مراجعة البيانات ودفع أجور التوصيل', 'Reviewing data and paying delivery fees',
            'مراجعة البيانات المدخلة، ثم دفع أجور التوصيل باستخدام بطاقة (فيزا أو مدى أو ماستركارد)، ثم تُجدَّد رخصة القيادة عند إتمام ذلك بنجاح.',
        ),
    ],
        fees_notes_ar='40 ريالاً عن كل سنة لرخصة القيادة الخاصة. 200 ريال لرخصة سير الدراجات النارية (مدة 10 سنوات). لا يحدد المصدر الرسمي المرفق قيمة أجور التوصيل بشكل منفصل عن رسوم التجديد نفسها.',
        delivery_notes_ar='يتم توصيل الرخصة المطبوعة إلى العنوان الوطني المسجّل بعد تعبئة بيانات العنوان ودفع أجور التوصيل؛ لا يحدد المصدر الرسمي المرفق اسم شركة الشحن ولا القيمة الدقيقة لأجور التوصيل (بيانات متغيرة/غير مذكورة في المصدر).',
        important_notes_ar=[
            'الخدمة مخصّصة لرخصة القيادة الخصوصية ورخصة قيادة الدراجة النارية الآلية فقط.',
            'يشترط التجديد وجود فحص طبي من أحد المراكز المعتمدة.',
        ],
        faq=[
        FaqItem(
            'كيف يتم احتساب رسوم التجديد مع التأخير؟',
            'يتم احتسابها تلقائيًا بشكل آلي في سداد.',
            'How are late renewal fees calculated?',
            'They are automatically calculated in the SADAD system.',
        ),
        FaqItem(
            'هل يلزم وجود فحص طبي جديد عند التجديد؟',
            'نعم.',
            'Is a new medical examination required for renewal?',
            'Yes.',
        ),
        FaqItem(
            'ما هي المدة المتوقعة لتسليم الوثيقة؟',
            'من 5 إلى 7 أيام.',
            'What is the expected delivery time for the document?',
            'Between 5 to 7 days.',
        ),
    ],
    ),
    # ---------------------------------------------------------------- 2 --
    ServiceRecord(
        service_id='vehicle_registration_renewal',
        service_name_ar='تجديد رخصة سير المركبة (تجديد الاستمارة)',
        service_name_en='Vehicle Registration Renewal',
        category_ar='المرور',
        category_en='Traffic',
        data_completeness='full',
        source_files=[
            'vehicle_registration_renewal_guide.txt',
            'vehicle_registration_renewal_faq.txt',
        ],
        definition_ar='تتيح هذه الخدمة للمستفيد تجديد رخصة سير المركبة (تجديد الاستمارة) إلكترونيًا بكل سهولة ويسر، في أي وقت ومن أي مكان، بخطوات سهلة وبسيطة عبر منصة أبشر دون الحاجة إلى زيارة مقار الإدارة العامة للمرور.',
        conditions_ar=[
            'وثيقة تأمين سارية على المركبة.',
            'شهادة الفحص الفني سارية المفعول.',
            'سداد رسوم التجديد ومخالفة التأخير إن وجدت.',
            'سداد المخالفات المرورية إن وجدت.',
            'ألا تقل صلاحية رخصة سير المركبة عن 180 يومًا.',
        ],
        steps=[
        StepPhase(
            'access', 'الوصول إلى الخدمة واختيار المركبة', 'Accessing the service and selecting the vehicle',
            'الدخول إلى منصة أبشر، ثم اختيار "المركبات"، ثم اختيار "إدارة المركبات" من قائمة الخدمات، ثم اختيار المركبة المراد تجديد رخصتها.',
        ),
        StepPhase(
            'eligibility_confirm', 'التجديد والتأكيد', 'Renewing and confirming',
            'اختيار "تجديد رخصة سير"، ثم يتحقّق النظام آليًا من أهلية المستفيد للتجديد وفقًا لشروط ومتطلبات الخدمة، ثم اختيار "تأكيد التجديد" لإتمام تجديد رخصة السير بنجاح.',
        ),
    ],
        fees_notes_ar='100 ريال لكل سنة لا يذكر المصدر الرسمي المرفق أي رسوم توصيل مستندات منفصلة لهذه الخدمة.',
        delivery_notes_ar='لا ينطبق — خدمة إلكترونية بالكامل، رخصة السير رقمية ولا يوجد توصيل مستند مطبوع مذكور في المصدر الرسمي المرفق.',
        important_notes_ar=[
            'تجديد رخصة السير الرقمي إلكتروني بالكامل ولا يحتاج زيارة مقار المرور.',
            'قناة تقديم الخدمة (منصة أبشر تحديدًا مقابل تطبيق الجوال) غير محددة بوضوح في المصدر الرسمي المرفق لهذه الخدمة.',
        ],
        faq=[
        FaqItem(
            'كيف يتم احتساب تاريخ انتهاء رخصة السير بعد التجديد؟',
            '3 سنوات من بعد تاريخ الانتهاء للرخصة السابقة في حال تم التجديد بعد انتهاء تاريخ الرخصة السابقة أو عند تاريخ التجديد في حال تم التجديد قبل تاريخ الانتهاء.',
            'How is the expiry date of the vehicle registration (Istimara) calculated after renewal?',
            "3 years from the previous registration's expiry date if renewed after expiry, or from the renewal date if renewed before expiry.",
        ),
        FaqItem(
            'رخصة المركبة منتهية، وبعد التجديد تم احتساب تاريخ الانتهاء من تاريخ الاستمارة السابقة، لماذا؟',
            'في حال تم التجديد بعد انتهاء تاريخ الرخصة فإن التجديد يتم احتسابه من تاريخ انتهاء الاستمارة السابقة.',
            "My vehicle registration was expired, and after renewal the expiry date was calculated based on the previous registration's date. Why?",
            "If the renewal is done after the registration expires, the new expiry date is calculated from the previous registration's expiry date.",
        ),
        FaqItem(
            'كيف يتم احتساب رسوم التجديد مع التأخير؟',
            'يتم احتسابها تلقائيًا بشكل آلي في سداد.',
            'How are late renewal fees calculated?',
            'They are automatically calculated in the SADAD system.',
        ),
    ],
    ),
    # ---------------------------------------------------------------- 3 --
    ServiceRecord(
        service_id='exit_reentry_final_exit_visa',
        service_name_ar='إصدار تأشيرة الخروج والعودة أو الخروج النهائي',
        service_name_en='Issuance of Exit/Reentry or Final Exit Visa',
        category_ar='الجوازات',
        category_en='Passports (Residency & Visas)',
        data_completeness='full',
        source_files=[
            'exit_reentry_final_exit_visa_guide.txt',
        ],
        definition_ar='تتيح هذه الخدمة للمستفيد إصدار تأشيرة خروج وعودة أو تأشيرة خروج نهائي لأفراد الأسرة أو العمالة المنزلية إلكترونيًا.',
        conditions_ar=[
            'أن يكون المستفيد داخل المملكة عند إصدار التأشيرة.',
            'يمكن تحديد تاريخ العودة قبل 7 أيام من تاريخ انتهاء الإقامة (تُطبق الشروط الأخرى للخدمة).',
            'عند اختيار المدة "بالأشهر" لتأشيرة خروج وعودة (سفرة واحدة)، يجب أن تكون صلاحية الإقامة 90 يومًا على الأقل إضافة إلى المدة المطلوبة.',
            'في حال تحديد "تاريخ العودة قبل"، يعتبر التاريخ المدخل هو آخر موعد لدخول المملكة.',
            'يُعتمد التاريخ الميلادي في حال اختلافه عن الهجري.',
            'توفر بصمة للمستفيد (للذكور والإناث من عمر 15 عام فأعلى).',
            'عند السفر إلى إحدى دول الخليج، يجب أن تكون الإقامة سارية لمدة لا تقل عن 3 أشهر من تاريخ السفر.',
        ],
        steps=[
        StepPhase(
            'access_domestic', 'الوصول إلى الخدمة (للعمالة المنزلية)', 'Accessing the service (for domestic workers)',
            'الدخول إلى منصة أبشر، ثم اختيار "خدمات العمالة"، ثم اختيار "التأشيرات"، ثم اختيار العامل المطلوب إصدار التأشيرة له.',
        ),
        StepPhase(
            'confirm_domestic', 'اختيار نوع التأشيرة والتأكيد (للعمالة المنزلية)', 'Selecting visa type and confirming (for domestic workers)',
            'اختيار نوع التأشيرة: "خروج وعودة" أو "خروج نهائي"، ثم التأكد من توفر الشروط وسداد الرسوم المطلوبة، ثم الموافقة على الشروط والأحكام، ثم اختيار "إصدار التأشيرة".',
        ),
        StepPhase(
            'access_family', 'الوصول إلى الخدمة (للمرافقين)', 'Accessing the service (for accompanying family members)',
            'الدخول إلى منصة أبشر، ثم اختيار "خدمات أفراد الأسرة"، ثم اختيار "التأشيرات"، ثم اختيار الفرد المطلوب إصدار التأشيرة له.',
        ),
        StepPhase(
            'confirm_family', 'اختيار نوع التأشيرة والتأكيد (للمرافقين)', 'Selecting visa type and confirming (for accompanying family members)',
            'اختيار نوع التأشيرة: "خروج وعودة" أو "خروج نهائي"، ثم التأكد من توفر الشروط وسداد الرسوم المطلوبة، ثم الموافقة على الشروط والأحكام، ثم اختيار "إصدار التأشيرة".',
        ),
    ],
        fees_notes_ar='تكلفة الخدمة متغيرة؛ لا يحدد المصدر الرسمي المرفق قيمة رسم ثابت بالريال.',
        delivery_notes_ar='لا ينطبق (خدمة تأشيرة إلكترونية، لا توصيل مستندات).',
        important_notes_ar=[
            'توجد إجراءان بديلان بحسب المستفيد من التأشيرة: العمالة المنزلية (عبر «خدمات العمالة») أو أفراد الأسرة المرافقين (عبر «خدمات أفراد الأسرة») — نفس نوعي التأشيرة (خروج وعودة / خروج نهائي) متاحان في كلا المسارين.',
            'هذه الخدمة كانت مصنّفة سابقًا faq_only (بيانات جزئية من الأسئلة الشائعة فقط)؛ مصدر البيانات الجديد يتضمن صفحة الخدمة التفصيلية الكاملة، فتم ترقية data_completeness إلى full.',
        ],
        faq=[
        FaqItem(
            'كيف يمكن طلب تأشيرة الخروج النهائي للتابعين؟',
            'عن طريق الدخول إلى أبشر أفراد والبدء بخدمة "إصدار تأشيرة خروج وعودة أو تأشيرة خروج نهائي".',
            'How can a final exit visa be requested for dependents?',
            'By logging into Absher Individuals and starting the "Issue Exit/Return Visa or Final Exit Visa" service.',
        ),
        FaqItem(
            'هل يشترط وجود بصمة للفرد المراد إصدار التأشيرة له؟',
            'نعم، يشترط.',
            'Is a fingerprint required for the individual for whom the visa is being issued?',
            'Yes, it is required.',
        ),
        FaqItem(
            'إذا كانت الإقامة منتهية، هل يمكنني إصدار تأشيرة خروج وعودة أو تأشيرة خروج نهائي؟',
            'لا، يعتبر سريان الإقامة متطلبًا لاستخراج التأشيرة.',
            'If the residency is expired, can I issue an exit/re-entry visa or a final exit visa?',
            'No, valid (in-effect) residency is a requirement for issuing the visa.',
        ),
    ],
    ),
    # ---------------------------------------------------------------- 4 --
    ServiceRecord(
        service_id='lost_passport_replacement',
        service_name_ar='إصدار جواز بدل مفقود',
        service_name_en='Lost Passport Replacement Service',
        category_ar='الجوازات',
        category_en='Passports',
        data_completeness='full',
        source_files=[
            'lost_passport_replacement_guide.txt',
            'lost_passport_replacement_faq.txt',
        ],
        definition_ar='تتيح هذه الخدمة الإلكترونية للمواطنين والمواطنات تقديم طلب إصدار جواز بدل مفقود إلكترونيًا، إضافة إلى توصيله إلى عنوان المستفيد المسجل دون الحاجة لمراجعة مكاتب الجوازات.',
        conditions_ar=[
            'إذا كان عمر المستفيد أقل من 21 سنة، يتم إصدار الجواز لمدة 5 سنوات فقط.',
            'إذا كان عمر المستفيد 21 سنة أو أكثر، يمكنه اختيار صلاحية الجواز (5 أو 10 سنوات).',
            'أن تكون هوية المواطن/المواطنة سارية المفعول.',
            'توفر بصمة وصورة للمستفيد في أنظمة وزارة الداخلية.',
            'سيتم اعتماد الصورة المسجلة في الأنظمة في الجواز الصادر.',
            'أن يكون المستفيد متواجدًا داخل المملكة العربية السعودية عند تقديم الطلب.',
            'ألا يكون لدى المستفيد جواز سفر ساري آخر أو مرافقًا في جواز سفر شخص آخر.',
            'أن يتم الإبلاغ عن فقدان أو سرقة الجواز.',
        ],
        steps=[
        StepPhase(
            'access', 'الوصول إلى الخدمة واختيارها', 'Accessing and selecting the service',
            'تسجيل الدخول إلى أبشر، ثم اختيار "خدماتي"، ثم اختيار "خدمات جواز السفر السعودي"، ثم اختيار "طلب جديد"، ثم اختيار "إصدار جواز بدل مفقود".',
        ),
        StepPhase(
            'delivery_address', 'بيانات عنوان التوصيل', 'Delivery address data',
            'مراجعة معلومات عنوان التوصيل، ثم تعبئة بيانات عنوان التوصيل.',
        ),
        StepPhase(
            'carrier_payment', 'اختيار الناقل والدفع', 'Choosing a carrier and paying',
            'اختيار الناقل، ثم مراجعة المعلومات ودفع أجور التوصيل.',
        ),
    ],
        fees_notes_ar='تكلفة الخدمة متغيرة؛ لا يحدد المصدر الرسمي المرفق قيمة رسم ثابت بالريال ولا اسم شركة الشحن تحديدًا (يُطلب من المستفيد اختيار الناقل أثناء الإجراء).',
        delivery_notes_ar='بعد اختيار الناقل ودفع أجور التوصيل، يُرسل الجواز الجديد إلى عنوان التوصيل الذي تمت تعبئته؛ لا يحدد المصدر الرسمي المرفق اسم الناقل بالتحديد ولا مدة التسليم بالأيام.',
        important_notes_ar=[
            'الخدمة مخصّصة للمواطنين والمواطنات (جواز السفر السعودي).',
            'يشترط الإبلاغ المسبق عن فقدان أو سرقة الجواز قبل تقديم الطلب.',
            'إذا كانت الهوية الوطنية منتهية الصلاحية، يجب تجديدها أولًا قبل إصدار الجواز البديل.',
        ],
        faq=[
        FaqItem(
            'هل يشترط الإبلاغ عن فقدان الجواز لإصدار جواز جديد؟',
            'نعم، يشترط الإبلاغ عن فقدان الجواز أولاً قبل طلب إصدار جواز جديد.',
            'Is it required to report a lost passport in order to issue a new one?',
            'Yes, reporting the loss or theft of the passport is required before issuing a new one.',
        ),
        FaqItem(
            'هل يمكن إصدار جواز بدل مفقود لأحد أفراد الأسرة؟',
            'نعم، يمكن للمستفيد إصدار جواز بدل مفقود لأحد أفراد أسرته.',
            'Can a replacement passport be issued for a lost one on behalf of family members?',
            'Yes, the beneficiary can issue a replacement passport for a lost one on behalf of a family member.',
        ),
        FaqItem(
            'هويتي منتهية، هل بإمكاني إصدار جواز بدل مفقود؟',
            'لا، لا يمكن إصدار الجواز والهوية منتهية، ويجب تجديد الهوية أولاً قبل إصدار الجواز.',
            'My ID is expired — can I issue a replacement passport for a lost one?',
            'No, you cannot issue a passport if your ID is expired. You must renew your ID first before issuing a passport.',
        ),
    ],
    ),
    # ---------------------------------------------------------------- 5 --
    ServiceRecord(
        service_id='lost_stolen_plate_report',
        service_name_ar='الإبلاغ عن سرقة أو فقدان لوحة مركبة',
        service_name_en='Report Stolen/Lost Vehicle Plate',
        category_ar='المرور',
        category_en='Traffic',
        data_completeness='full',
        source_files=[
            'lost_stolen_plate_report_guide.txt',
        ],
        definition_ar='تتيح هذه الخدمة للأفراد الإبلاغ عن سرقة أو فقدان لوحة مركبة إلكترونيًا، وذلك بعد الاطلاع على شروط الخدمة، وتعبئة الطلب، والإقرار على التعهد.',
        conditions_ar=[
            'عند تقديم البلاغ، سيتم التعميم على المركبة.',
            'لا يمكن تقديم أكثر من طلب لنفس المركبة.',
            'يجب أن تكون حالة المركبة "صالحة" في النظام.',
            'تقتصر الخدمة على مالك المركبة فقط.',
        ],
        steps=[
        StepPhase(
            'access', 'الوصول إلى الخدمة', 'Accessing the service',
            'تسجيل الدخول إلى موقع منصة أبشر، ثم اختيار "المركبات"، ثم اختيار "خدمات"، ثم اختيار "إدارة المركبات"، ثم اختيار "الإبلاغ عن سرقة أو فقدان لوحة مركبة".',
        ),
        StepPhase(
            'submit_report', 'تقديم البلاغ', 'Submitting the report',
            'مراجعة شروط الخدمة، ثم تعبئة نموذج البلاغ وتقديمه.',
        ),
    ],
        fees_notes_ar='لا يذكر المصدر الرسمي المرفق أي رسوم لهذه الخدمة.',
        delivery_notes_ar='لا ينطبق (بلاغ إلكتروني، لا توصيل مستندات).',
        important_notes_ar=[
            'عند تقديم البلاغ يتم التعميم على المركبة في النظام.',
            'لا يمكن تقديم أكثر من بلاغ واحد لنفس المركبة؛ يجب متابعة البلاغ الحالي قبل تقديم طلب جديد.',
            'الخدمة تقتصر على مالك المركبة فقط، ويجب أن تكون حالة المركبة "صالحة" في النظام.',
            'هذه الخدمة لم يكن لها أي مصدر رسمي متاح في النسخة السابقة من قاعدة المعرفة (كانت مستبعدة بالكامل)؛ أصبح الآن لديها مصدر رسمي كامل.',
        ],
        faq=[
        FaqItem(
            'ما هي المتطلبات الأساسية لتقديم بلاغ عن سرقة أو فقدان لوحة مركبة؟',
            'يجب أن تكون حالة المركبة "صالحة" في النظام، وأن يكون مقدم الطلب هو مالك المركبة، مع عدم وجود بلاغ سابق لنفس المركبة.',
            'What are the basic requirements for submitting a report about theft or loss of a vehicle plate?',
            'The vehicle status must be "valid" in the system, and the applicant must be the vehicle owner, with no existing prior report for the same vehicle.',
        ),
        FaqItem(
            'هل يمكن تقديم أكثر من بلاغ عن نفس المركبة؟',
            'لا، لا يمكن تقديم أكثر من بلاغ عن نفس المركبة. يجب متابعة البلاغ الحالي قبل تقديم أي طلب جديد.',
            'Can more than one report be submitted for the same vehicle?',
            'No, more than one report cannot be submitted for the same vehicle. The current report must be followed up on before submitting any new request.',
        ),
    ],
    ),
    # ---------------------------------------------------------------- 6 --
    ServiceRecord(
        service_id='firearm_transport_permit',
        service_name_ar='إذن التنقل بالسلاح الناري',
        service_name_en='Firearm Transport Permit',
        category_ar='الأمن العام',
        category_en='Public Security',
        data_completeness='full',
        source_files=[
            'firearm_transport_permit_guide.txt',
        ],
        definition_ar='تتيح هذه الخدمة للمواطن إصدار إذن إلكتروني لحمل السلاح المسجل تحت رخصة الاقتناء لغرض التنقل من منطقة إلى منطقة.',
        conditions_ar=[
            'أن يكون لدى المستفيد هوية رقمية في منصة أبشر.',
            'عدم وجود ملاحظات أمنية.',
            'أن يكون السلاح المراد إصدار إذن التنقل له ضمن رخصة الاقتناء فقط.',
            'لا يمكن حمل أكثر من سلاح واحد واقتناء أكثر من عشرة أسلحة.',
            'يمكن شراء الأسلحة من الملاك أو المراكز المعتمدة.',
        ],
        steps=[
        StepPhase(
            'access', 'الوصول إلى الخدمة', 'Accessing the service',
            'تسجيل الدخول إلى منصة أبشر، ثم اختيار "خدماتي"، ثم اختيار "الأمن العام"، ثم اختيار "إدارة الأسلحة".',
        ),
        StepPhase(
            'select_submit', 'اختيار الخدمة وتقديم الطلب', 'Selecting the service and submitting the request',
            'استعراض الخدمات المتاحة، ثم اختيار الخدمة المطلوبة، ثم تعبئة البيانات المطلوبة حسب نوع الخدمة (مسار التنقل، المنطقة، تاريخ بداية التصريح، عدد الذخائر)، ثم تأكيد الطلب.',
        ),
    ],
        fees_notes_ar='57.5 ريال (تُدفع عند تقديم الطلب).',
        delivery_notes_ar='لا ينطبق (إذن إلكتروني، لا توصيل مستندات).',
        important_notes_ar=[
            'لا يُسمح بحمل أكثر من سلاح واحد في كل إذن تنقل.',
            'يُمنع حمل السلاح داخل الحرمين الشريفين والمناطق الحكومية والأمنية.',
            'هذه الخدمة لم يكن لها أي مصدر رسمي متاح في النسخة السابقة من قاعدة المعرفة (كانت مستبعدة بالكامل)؛ أصبح الآن لديها مصدر رسمي كامل.',
        ],
        faq=[
        FaqItem(
            'هل توجد رسوم لهذه الخدمة؟',
            'نعم، يجب دفع رسوم عند التقديم على الخدمة.',
            'Are there fees for this service?',
            'Yes, fees must be paid upon submitting the service request.',
        ),
        FaqItem(
            'هل يمكن إصدار إذن لأكثر من سلاح؟',
            'لا، لا يُسمح بحمل أكثر من سلاح واحد في كل إذن تنقل.',
            'Can a permit be issued for more than one weapon?',
            'No, it is not allowed to carry more than one weapon per transport permit.',
        ),
        FaqItem(
            'ما المناطق التي يُمنع التنقل فيها بالسلاح؟',
            'يُمنع حمل السلاح داخل الحرمين الشريفين والمناطق الحكومية والأمنية.',
            'What are the areas where weapon transport is prohibited?',
            'Carrying weapons is prohibited inside the two Holy Mosques and government and security areas.',
        ),
    ],
    ),
]


def get_services() -> List[Dict[str, Any]]:
    return [asdict(s) for s in SERVICES]


def save_processed_documents(out_path: Path = PROCESSED_DIR / "documents.json") -> Path:
    """As of the Absher data refresh (see data/raw/SOURCES_MANIFEST.md),
    official source material is now available for all 6 Absher services
    Jawaher originally scoped — the `excluded_services` block that used to
    list the 2 unreachable services (lost/stolen plate report, firearm
    transport permit) has been removed because it is no longer true; both
    now have full ServiceRecords in SERVICES above, same as the other 4."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"services": get_services()}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    inspect_raw_documents()
    path = save_processed_documents()
    print(f"\nWrote structured services to {path}")
