أنت Codex داخل VS Code Terminal. المطلوب منك تنفيذ تطوير واجهة أمامية كاملة (Front-End) باستخدام Python + Streamlit لبرنامج “Pharmacy Inventory / Stock Count” يعتمد على ناتج الـ GS1 parser الموجود لدينا ويعرض بيانات المسح + إدخال كميات الجرد + تقارير نهائية. 

⚠️ قيود مهمة جدًا:
1) لا تغيّر منطق الـ GS1 parsing الداخلي الحالي إلا إذا اضطررت فقط للربط/الاستدعاء. 
2) التزم ببناء Frontend قوي ومرتب “شبيه بأنظمة جرد الصيدليات” مع كل الخصائص المذكورة أدناه (حتى الخصائص الاختيارية).
3) التزم بإنشاء نظام تسجيل دخول بسيط (Temporary) ببيانات:
   - username: admin
   - password: admin
   مع قابلية التغيير لاحقًا.
4) لا تستخدم أي خدمات خارجية. كل شيء محلي داخل المشروع.
5) ركّز على UX سريع جدًا (Scan → يظهر كارت → إدخال كمية → Add) وتقارير قابلة للطباعة والتصدير.
6) اجعل كل شيء قابل للحفظ والاسترجاع بعد Refresh أو إغلاق الصفحة (Persistence).

========================================
1) سياق البيانات (Input JSON Structure)
========================================
الـ parser الحالي يرجع JSON مشابه للأمثلة التالية (قد توجد حقول ناقصة في بعض المسحات):
{
  "GTIN": "08002660032249",
  "SERIAL": "486280077903",
  "Expiry Date": "31/07/2027",
  "BATCH/LOT": "729323",
  "Trade Name": "DUSPATALIN 200MG PROLONGED RELEASE CAPS",
  "Scientific Name": "MEBEVERINE HYDROCHLORIDE",
  "PRICE": 48.15,
  "SFDA Code": ["0604233492"],
  "GRANULAR_UNIT": 30,
  "UNIT_TYPE": "CAPSULE",
  "DOSAGE_FORM": "PROLONGED RELEASE CAPSULES",
  "ROA": "ORAL",
  "PACKAGE_TYPE": "BLISTER PACK",
  "PACKAGE_SIZE": "30'S",
  "STRENGTH": "200 MG",
  "CATEGORY": "PHARMACEUTICAL"
}

ويتم تشغيله مثل:
python -m gs1_parser "<SCAN_STRING>" --json --lookup

ملاحظة: بعض المسحات قد لا تحتوي SERIAL أو BATCH أو Expiry أو lookup fields. الواجهة يجب ألا تنهار عند غياب أي حقل.

========================================
2) أهداف واجهة Streamlit (High-Level)
========================================
أريد تطبيق Streamlit بصفحات/أقسام واضحة (يمكن tabs أو multipage):
A) Login
B) Inventory Session Setup (جلسة الجرد)
C) Scan & Count (المسح + إدخال الكميات)
D) Review & Reconcile (مراجعة/تعديلات/تسويات)
E) Finalize & Reports (إقفال الجرد + التقارير)
F) Audit & Logs (سجل التعديلات والأحداث)

ويجب أن تكون الواجهة “نظيفة واحترافية” قريبة من أنظمة جرد الصيدلية:
- تصميم بسيط
- كروت واضحة
- جدول قوي
- فلترة وبحث
- Badges للحالات (valid/warn/error)
- اختصارات UX (Enter=Add، auto focus)
- قابلية طباعة/تصدير تقارير

========================================
3) متطلبات تسجيل الدخول (Login)
========================================
- شاشة Login قبل أي شيء.
- تحقق من username/password (admin/admin).
- عند نجاح الدخول: خزّن المستخدم الحالي في session_state.
- واجهة Logout.
- اجعل بنية المصادقة قابلة للتوسعة لاحقًا (مثلا users.json أو SQLite) لكن الآن اكتفِ بـ admin/admin.

========================================
4) Session Header + Inventory Session Setup
========================================
قبل بدء المسح، المستخدم لازم ينشئ “جلسة جرد” Session تحتوي:
- session_id (UUID تلقائي)
- session_name (اختياري، مثل: “صيدلية الدور الأول – جرد صباحي”)
- counter_name (اسم القائم بالجرد) => إلزامي
- location (مكان الجرد: فرع/مستودع/رف/قسم) => إلزامي
- inventory_type (Full / Partial / Shelf / Department / Supplier) => اختيار
- start_datetime تلقائي
- device_id (اختياري)
- notes (اختياري)

بعد إنشاء الجلسة:
- يظهر Header ثابت أعلى كل الصفحات أثناء الجلسة:
  - Counter Name
  - Location
  - Session ID
  - Start time
  - Status: In Progress / Finalized
- زر “New Session” (بعد إقفال الجلسة فقط أو مع تحذير)

========================================
5) صفحة Scan & Count (أهم جزء UX)
========================================
الهدف: سرعة عالية.

المكونات المطلوبة:
1) Scan Input:
   - Text input كبير جدًا (Cashier style) لقراءة النص القادم من الـ scanner
   - زر “Parse” (اختياري) لكن الأفضل: Auto-Parse عند Enter/submit
   - بعد الإضافة يرجع focus تلقائيًا لحقل Scan

2) Scan Result Card (Card كبير بعد كل Parse):
   يعرض:
   - Trade Name (أكبر عنوان)
   - Scientific Name
   - GTIN (مع زر Copy)
   - Expiry Date + Badge الحالة:
       ✅ Valid
       ⚠️ Near Expiry (حدد threshold افتراضي: 6 أشهر)
       ❌ Expired
   - Batch/Lot
   - Serial (إذا موجود)
   - Strength
   - Dosage Form
   - Unit Type + Granular Unit
   - Package Type + Package Size
   - ROA
   - Price
   - SFDA Code: عرض مختصر (أول عنصر) + زر “Show all” لعرض القائمة كاملة

3) Count Input Area:
   - حقل “On-hand Count” (إلزامي)
   - Unit selector (اختياري):
       - default = UNIT_TYPE
       - خيارات: BOX / PACK / BLISTER / TABLET / CAPSULE / VIAL / AMPOULE / BOTTLE (إلخ)
   - زر “Add to Inventory”
   - Behavior:
       - Enter يضيف السطر (أو بسرعة قدر الإمكان)
       - بعد الإضافة: رسالة success + آخر عملية إضافة في شريط صغير “Last Added”
       - يعود focus لScan input

4) Duplicate Handling Rules (UI Behavior):
   - إذا تم مسح نفس (GTIN + Batch/Lot + Expiry Date):
       - Popup/Prompt: “Already exists. Aggregate quantity or add new line?”
       - Default: Aggregate (تجميع)
   - إذا Serial مكرر:
       - Warning أحمر قوي + منع الإضافة افتراضيًا (مع خيار override فقط إن فعل admin خيار Allow Override)
   - إذا GTIN موجود لكن بدون Lookup (Trade/Scientific فارغة):
       - ضع Badge “Unknown GTIN”
       - زر “Quick Add Minimal Info” (اسم يدوي مؤقت) لا يغيّر DB الأصلية لكن يضاف للجلسة.

5) Data Quality Panel (ملخص سريع):
   يعرض أرقام:
   - Total scans
   - Total unique items (حسب GTIN+Batch+Expiry)
   - Near expiry count
   - Expired count
   - Duplicate serial attempts
   - Unknown GTIN count
   - Parsing errors count

========================================
6) جدول Inventory Lines (سجل الجرد)
========================================
اعمل جدول تفاعلي قوي (DataFrame editor أو Grid component مناسب في Streamlit) مع:
- Search box
- Filters
- Sorting

الأعمدة المطلوبة في جدول السطور (Inventory Lines Table Columns):
- line_id (UUID)
- session_id
- scan_timestamp
- scanned_by (username)
- GTIN
- Trade Name
- Scientific Name
- BATCH/LOT
- Expiry Date
- SERIAL
- On-hand Count
- Count Unit
- UNIT_TYPE
- GRANULAR_UNIT
- DOSAGE_FORM
- STRENGTH
- ROA
- PACKAGE_TYPE
- PACKAGE_SIZE
- CATEGORY
- PRICE
- SFDA Code (as string joined) + option expand
- Status Badges: Valid/NearExpiry/Expired/Unknown/Warning
- Notes (optional per line)

عمليات الجدول:
- Edit inline (تعديل الكمية + ملاحظة)
- Delete line (مع تسجيل في Audit)
- Merge duplicates (يدوي + تلقائي حسب الإعدادات)
- Export current view (CSV/Excel)

========================================
7) صفحة Review & Reconcile
========================================
توفر:
- عرض “Aggregated view” مجمع حسب (GTIN + Batch + Expiry) مع مجموع الكميات
- عرض “Detailed view” لكل سطر
- قائمة تحذيرات:
   - Near expiry items
   - Expired items
   - Unknown GTIN
   - Duplicate serial lines
- أدوات:
   - Bulk edit (اختياري)
   - Add notes/remarks على مستوى الجلسة
- “Lock lines” option (اختياري): يمنع تعديل سطور معينة

========================================
8) صفحة Finalize & Reports
========================================
1) Finalize Session:
- زر “Finalize / Lock Session”
- بعد الإقفال:
   - لا تعديل/حذف إلا بإذن admin + سجل audit
   - يظهر Status = Finalized

2) Final Report (اقتراح أعمدة التقرير النهائي)
أريد تقريرين:
A) Detailed Report (مفصل) – كل سطر
B) Summary Report (ملخص/مجمّع) – حسب GTIN+Batch+Expiry

أعمدة التقرير النهائي المقترحة:

A) Detailed Report Columns:
- Report Title: “Inventory Stock Count Report”
- Session ID
- Session Name
- Location
- Counter Name
- Generated At
- Generated By
- Status
- Line No
- Scan Timestamp
- GTIN
- Trade Name
- Scientific Name
- Strength
- Dosage Form
- Unit Type
- Package Size
- Batch/Lot
- Expiry Date
- Serial
- Count
- Count Unit
- Price
- SFDA Code(s)
- Category
- Item Status (Valid/NearExpiry/Expired/Unknown)
- Line Notes

B) Summary Report Columns (Aggregated):
- GTIN
- Trade Name
- Scientific Name
- Strength
- Dosage Form
- Unit Type
- Package Size
- Batch/Lot
- Expiry Date
- Total Count
- Count Unit
- SFDA Code(s)
- Item Status
- Notes (optional)

3) Exports:
- PDF للطباعة (شكل رسمي: Header + جدول + Footer)
- Excel (xlsx) (Sheet1 Detailed, Sheet2 Summary, Sheet3 Warnings)
- CSV (Detailed و Summary)

4) Report Extras:
- Summary KPIs في أعلى التقرير:
   - Total unique items
   - Total lines
   - Total quantity
   - Near expiry count
   - Expired count
   - Unknown GTIN count
   - Duplicate serial blocked count
- Warnings & Exceptions Section

========================================
9) Audit & Logs (مهم)
========================================
كل إجراء يُسجَّل:
- login success/failure
- session create/finalize
- add line
- edit line (before/after)
- delete line
- merge lines
- override duplicate serial

Audit columns:
- audit_id
- timestamp
- username
- action_type
- session_id
- line_id (optional)
- old_value (json string)
- new_value (json string)
- reason/comment

واجهة Audit:
- جدول قابل للبحث والفلترة
- Export audit (csv/xlsx)

========================================
10) Settings / Configuration (كل الخصائص حتى الاختيارية)
========================================
أنشئ صفحة Settings (admin فقط) تشمل:
- Near Expiry threshold months (default 6)
- Allow override for duplicate serial (default false)
- Default duplicate handling mode: Aggregate vs New line
- Display mode: Light/Dark (اختياري)
- Auto-parse on Enter (true)
- Auto-focus on scan input (true)
- Persistence backend: SQLite (افتراضي) أو ملفات محلية JSON (Fallback)
- Data retention: keep N sessions locally (اختياري)

========================================
11) Persistence / Storage
========================================
مطلوب حفظ كل بيانات الجلسة محليًا:
- sessions table
- lines table
- audit table
- users table (لاحقًا، الآن minimal)
ملاحظة تنفيذية:
- التطبيق الحالي يستخدم MongoDB كخيار أساسي مع JSON fallback (`data/app.json`) عبر إعداد `PERSISTENCE_BACKEND`.
- إذا كنت تحتاج SQLite محليًا بدل MongoDB، يجب إضافة adapter منفصل لاحقًا.
يجب أن:
- إذا المستخدم عمل Refresh، يرجع لنفس الجلسة لو كانت In Progress.
- يوجد قائمة Sessions لإعادة فتح Session قديمة (read-only أو حسب الحالة).

========================================
12) بنية المشروع + تشغيل .venv
========================================
- افترض وجود .venv.
- أنشئ/حدّث:
  - requirements.txt (streamlit, pandas, python-dateutil, report libs…)
  - app.py (نقطة التشغيل)
  - modules/ (ui components, storage, auth, reporting)
  - data/ (db)
  - exports/ (reports output)
  - README.md (خطوات التشغيل)

README يجب يشرح:
- تفعيل venv
- pip install -r requirements.txt
- تشغيل: streamlit run app.py

========================================
13) معايير جودة (Acceptance Criteria)
========================================
لا تعتبر المهمة مكتملة إلا إذا:
1) Login يعمل ويمنع الوصول بدون تسجيل.
2) Session Setup يعمل ويمنع بدء المسح بدون counter_name & location.
3) Scan → Parse → Card يظهر بشكل صحيح حتى لو نقصت حقول.
4) Count إدخال سريع + Add + جدول يتحدث فورًا.
5) Duplicate rules تعمل (aggregate prompt + serial duplicate blocking).
6) Review page تعرض aggregated + warnings.
7) Finalize يقفل الجلسة ويمنع التعديل بدون صلاحية.
8) Reports: PDF + Excel + CSV تعمل وتحتوي الأعمدة المقترحة + KPIs + Warnings.
9) Audit log يسجل كل شيء ويُعرض ويُصدّر.
10) Persistence: بعد refresh تبقى البيانات موجودة.

========================================
14) المطلوب منك الآن كـ Codex
========================================
- افحص هيكل المشروع الحالي (ls، tree).
- أنشئ/حدّث الملفات المطلوبة.
- اربط استدعاء gs1_parser (python -m gs1_parser ... --json --lookup) داخل التطبيق بطريقة آمنة (subprocess) مع معالجة أخطاء.
- نفّذ كل واجهات Streamlit المذكورة.
- اكتب README واضح.
- شغّل فحوص بسيطة (تشغيل محلي) وتأكّد عدم وجود أخطاء runtime.

ابدأ التنفيذ الآن.
