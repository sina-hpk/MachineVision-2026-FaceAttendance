<div dir="rtl" style="text-align: right; direction: rtl;">

# 📋 گزارش جامع و ژورنال توسعه پروژه CV Attendance System

> **تاریخ آخرین بازنگری:** ۴ اوت ۲۰۲۶
> **نسخه پروژه:** 3.2.0 — «مدیریت کامل نمونه‌های چهره»
> **محل پروژه:** `s:\TRAE\CV_Attendance`
> **وضعیت تست:** ۱۲۵ تست ✅ همه پاس

---

> 💡 **این فایل چیست؟** یک «ژورنال توسعه» است، نه یک README. هدفش ثبت **«چرا»** هاست: چرا این معماری انتخاب شد، چه چیزی شکست خورد، چطور فهمیدیم، و چه چیزی می‌توانست بهتر باشد. اگر تازه‌کار هستید، روی بخش‌های «نقد» و «شکار باگ» تمرکز کنید — ارزشمندترین قسمت‌ها آنجاست.

---

## 📑 فهرست

| بخش | موضوع |
|-----|-------|
| [۱](#۱-مقدمه-و-تعریف-مسئله) | مقدمه و تعریف مسئله |
| [۲](#۲-معماری-کلی-سیستم) | معماری کلی سیستم (پس از یکپارچه‌سازی) |
| [۳](#۳-تحلیل-عمیق-لایه‌های-هسته) | تحلیل عمیق لایه‌های هسته |
| [۴](#۴-جریان-داده-end-to-end) | جریان داده End-to-End |
| [۵](#۵-تنظیمات-و-configuration) | تنظیمات و Configuration |
| [۶](#۶-deployment-و-devops) | Deployment و DevOps |
| [۷](#۷-تست‌ها-و-کیفیت-کد) | تست‌ها و کیفیت کد |
| [۸](#۸-مانیتورینگ-و-observability) | مانیتورینگ و Observability |
| [۹](#۹-تحلیل-تصمیمات-طراحی) | تحلیل تصمیمات طراحی |
| [۱۰](#۱۰-شکار-باگ-روایت-کامل-یک-نشست-دیباگ-عمیق) | 🔥 **شکار باگ: روایت کامل** |
| [۱۱](#۱۱-roadmap-و-بهبودهای-پیشنهادی) | Roadmap و بهبودهای پیشنهادی |
| [۱۲](#۱۲-lessons-learned) | Lessons Learned |
| [۱۳](#۱۳-خلاصه-اجرایی) | خلاصه اجرایی و ارزیابی |
| [۱۴](#۱۴-ضمیمه-ساختار-فایل‌های-پروژه) | ضمیمه: ساختار فایل‌ها |
| [۱۵](#۱۵-changelog) | Changelog |

---

## ۱. مقدمه و تعریف مسئله

### ۱.۱ صورت مسئله

ثبت حضور و غیاب در کارگاه‌ها و شرکت‌های کوچک معمولاً با یکی از این روش‌ها انجام می‌شود:

| روش | مشکل اصلی |
|-----|-----------|
| کارت زدن (RFID) | کارت جا می‌ماند، رد و بدل می‌شود («buddy punching») |
| اثر انگشت | تماس فیزیکی، دست‌های آلوده/زخمی کار نمی‌کنند |
| دفتر دستی | قابل جعل، غیرقابل گزارش‌گیری |
| سرویس ابری چهره | داده‌های بیومتریک از سازمان خارج می‌شود |

هدف این پروژه: **حضور و غیاب بدون تماس، بدون کارت، و بدون ارسال هیچ داده‌ای به بیرون.** همه‌چیز روی یک ماشین محلی اجرا می‌شود — دوربین، مدل، دیتابیس.

### ۱.۲ الزامات کارکردی

1. کارگر جلوی دوربین می‌ایستد → سیستم او را می‌شناسد → ورود ثبت می‌شود.
2. همان کارگر در پایان شیفت مقابل دوربین می‌رود → خروج ثبت می‌شود.
3. چهرهٔ ناشناس نباید حضور ثبت کند؛ باید به‌عنوان «مهمان» نگه داشته شود تا اپراتور تصمیم بگیرد.
4. داشبورد زنده: تصویر دوربین + لیست حاضرین + گزارش ساعات.
5. پنل ادمین: دیدن کارگرهای ثبت‌نام‌شده و **عکس نمونه‌های چهرهٔ** هرکدام، افزودن نمونه (از دوربین یا فایل)، حذف نمونه، حذف کارگر، ارتقای مهمان.

### ۱.۳ الزامات غیرکارکردی

- **حریم خصوصی:** صفر درخواست شبکه به بیرون. مدل‌ها آفلاین، دیتابیس SQLite محلی.
- **پاسخ‌دهی:** داشبورد نباید قفل شود، حتی وقتی حلقهٔ تشخیص با تمام توان کار می‌کند. (این الزام دقیقاً همان چیزی بود که در نسخهٔ ۲.x شکست خورد — بخش ۱۰.)
- **صحت هویت:** یک شخص = یک رکورد. هرگز «یک نفر = سه کارگر». (این هم شکست خورد — بخش ۱۰.)
- **قابل نگهداری:** یک وب‌فریم‌ورک، یک ORM، یک فایل کانفیگ.

### ۱.۴ محدودیت‌های آگاهانه (Out of Scope)

- تشخیص چهره با ماسک کامل صورت
- multi-camera / چند شعبه
- ضدجعل سطح بالا (حملهٔ ۳بعدی، ماسک سیلیکونی). فقط liveness سبک داریم.
- مقیاس بالای همزمانی (سیستم برای <۲۰۰ کارگر روی یک ماشین طراحی شده)

---

## ۲. معماری کلی سیستم

### ۲.۱ نمای کلان

```
┌────────────── سخت‌افزار ──────────────┐
│  Webcam (DSHOW/V4L2)  +  Local Disk   │
└───────────────┬───────────────────────┘
                │ فریم BGR
┌───────────────▼───────────────────────┐
│  face_recognizer.py                   │
│  detect → quality → align → encode    │
│  → match(known, tolerance) → track    │
└───────────────┬───────────────────────┘
                │ [{box, person_id, name, confidence, encoding}]
┌───────────────▼───────────────────────┐
│  camera_loop()  (ترد پس‌زمینه)         │
│  _process_results() → attendance      │
│  raw_frame / frame (annotated)        │
└───────┬───────────────────┬───────────┘
        │                   │
┌───────▼──────┐   ┌────────▼──────────┐
│ attendance.py │   │  main_fastapi.py  │
│  toggle/report│   │  HTTP + MJPEG + WS│
└───────┬───────┘   └────────┬──────────┘
        │                    │
┌───────▼────────────────────▼──────────┐
│  models/repository.py  (FaceRepository)│
│  SQLAlchemy ORM  →  SQLite             │
└────────────────────────────────────────┘
```

### ۲.۲ چرا «یکپارچه‌سازی»؟

نسخه‌های اولیه دو مسیر موازی داشتند: یک اپ Flask ساده و یک اپ FastAPI مدرن؛ دو لایهٔ ذخیره‌سازی (فایل JSON + SQLAlchemy) و دو منبع کانفیگ. نتیجه: هر باگ باید دو بار رفع می‌شد و رفتار دو مسیر واگرا می‌شد.

در نسخهٔ ۳.۰.۰ فقط این‌ها باقی ماند:

| نقش | انتخاب نهایی | حذف‌شده |
|-----|--------------|---------|
| وب | FastAPI + Uvicorn | Flask |
| ذخیره‌سازی | SQLAlchemy + SQLite | فایل‌های JSON خام |
| کانفیگ | `config.py` (Pydantic Settings) | متغیرهای پراکنده |
| احراز هویت | `auth.py` (JWT + RBAC) | — |

### ۲.۳ مدل هم‌روندی (Concurrency Model)

این بخش قلب پروژه است و منبع دو باگ جدی بود.

```
┌─────────────────────────────────────────────────────────┐
│ Thread 1: camera_loop (daemon)                          │
│   while True:                                           │
│     raw = read_frame()                                  │
│     with recognition_lock: results = recognize(raw)      │
│     with cam_lock: raw_frame = raw; frame = annotated    │
│     _process_results(results)                           │
│     time.sleep(0.01)   ← رهاسازی GIL                    │
├─────────────────────────────────────────────────────────┤
│ Thread 2..N: Starlette threadpool                       │
│   هندلرهای `def` (سنکرون) → کوئری DB بدون بلاک event loop │
├─────────────────────────────────────────────────────────┤
│ Event loop: هندلرهای `async def`                        │
│   فقط کارهای I/O-bound غیرمسدودکننده                    │
└─────────────────────────────────────────────────────────┘
```

قفل‌ها:

| قفل | محافظت از |
|-----|-----------|
| `cam_lock` | `frame`, `raw_frame`, `frame_seq` |
| `recognition_lock` | فراخوانی `recognizer.recognize()` (dlib ایمن برای هم‌روندی نیست) |
| `guest_lock` | `guest_id` جاری (چهرهٔ ناشناسِ در انتظار تصمیم) |
| `event_lock` | آخرین رویداد برای نمایش در داشبورد |
| `_reg_lock` (در `registration.py`) | نشست ثبت‌نام ۶ زاویه |

**قاعدهٔ طلایی که یاد گرفتیم:** هر هندلری که کوئری دیتابیس یا کار CPU-bound دارد باید `def` باشد نه `async def`. FastAPI توابع `def` را در threadpool اجرا می‌کند؛ `async def` را روی event loop — و یک کوئری کند در event loop تمام سرور را می‌خواباند.

### ۲.۴ دو فریم، نه یکی

یک تصمیم کوچک با اثر بزرگ:

```python
frame: Optional[np.ndarray] = None       # با کادر و اسم رسم‌شده → فقط برای MJPEG
raw_frame: Optional[np.ndarray] = None   # خام → برای هر انکودینگی که ذخیره می‌شود
```

قبلاً مسیر ثبت‌نام از `frame` انکود می‌گرفت، یعنی مستطیل سبز و متن روی صورت هم بخشی از ورودی شبکه می‌شد. بخش ۱۰ توضیح می‌دهد چرا این فاجعه بود.

---
## ۳. تحلیل عمیق لایه‌های هسته

### ۳.۱ `face_recognizer.py` — ارکستراتور بینایی ماشین

این فایل دو موتور دارد و همین موضوع منشأ پیچیدگی است:

| موتور | مدل | بُعد بردار | نقش |
|-------|-----|-----------|-----|
| InsightFace | RetinaFace + ArcFace | ۵۱۲ | موتور اصلی (اگر نصب باشد) |
| dlib | HOG/CNN + ResNet-29 | ۱۲۸ | fallback — همین در محیط فعلی فعال است |

خط لوله `_recognize_dlib()` (مسیر فعال):

```
frame (BGR, full res)
  │
  ├─ resize(process_scale) → face_locations()      # تشخیص ارزان
  │      ↓ مقیاس‌دهی معکوس مختصات
  ├─ face_encodings(rgb_FULL, full_locations)      # ★ انکود روی فریم کامل
  │
  ├─ quality gate  (blur / brightness / pose)      # زیر آستانه → دور ریخته می‌شود
  ├─ landmarks → align_face()  ← فقط برای نمایش/ذخیره
  ├─ liveness.update()         ← تصویر مرده → دور ریخته می‌شود
  ├─ _match_dlib()  → argmin(face_distance) با tolerance
  └─ _apply_tracking()  → هموارسازی زمانی هویت
```

نکتهٔ حیاتی که با ستاره علامت زده شده: **تشخیص روی فریم کوچک، انکود روی فریم کامل.** جداکردن این دو، ریشهٔ اصلی باگ «یک نفر = سه کارگر» را کند (بخش ۱۰.۲).

محاسبهٔ اعتماد (confidence) در `_match_dlib`:

```python
confidence = 1.0 - sd[0] / sd[1]          # فاصلهٔ بهترین نسبت به دومین بهترین
confidence *= (0.5 + 0.5 * quality_score) # جریمهٔ کیفیت پایین
```

این یک معیار *نسبی* است، نه احتمال. اگر فقط یک نفر در دیتابیس باشد، `sd[1]` وجود ندارد و مقدار ثابت ۰.۶ استفاده می‌شود. **نقد:** این عدد به کاربر نمایش داده می‌شود و می‌تواند گمراه‌کننده باشد؛ بهتر بود فاصلهٔ خام هم در پنل ادمین دیده شود.

### ۳.۲ `models/repository.py` — تنها دروازهٔ دیتابیس

`FaceRepository` الگوی «یک session به‌ازای هر عملیات» را دنبال می‌کند:

```python
def _get_session(self) -> Session:
    return SessionLocal()      # هر متد session خودش را می‌سازد و در finally می‌بندد
```

**چرا نه یک session طولانی‌عمر؟** چون `camera_loop` در یک ترد و هندلرهای HTTP در تردهای دیگر اجرا می‌شوند و Session در SQLAlchemy thread-safe نیست. session کوتاه‌عمر گران‌تر است اما مسئلهٔ هم‌روندی را کامل حذف می‌کند.

متدهای کلیدی:

| متد | نکته |
|-----|------|
| `get_all_known()` | کارگرهای فعال + مهمان‌های ارتقانیافته را برمی‌گرداند. مهمان‌ها هم در لیست تطبیق هستند تا **دوباره ثبت نشوند** |
| `add_worker(name, encodings, face_image)` | نام تکراری → `DuplicateNameError`؛ عکس در `data/faces/W00X.jpg` |
| `add_encoding_to_worker()` | سقف `max_encodings=10` |
| `remove_encoding(wid, sid)` | از حذف **آخرین** نمونه جلوگیری می‌کند (وگرنه کارگر دیگر هرگز شناخته نمی‌شود) |
| `list_workers_detailed()` | با `joinedload(Worker.encodings)` تا از N+1 query جلوگیری شود |
| `promote_guest_to_worker()` | انکودینگ‌های مهمان را به کارگر جدید **کپی** می‌کند، مهمان را `promoted=1` می‌زند |

### ۳.۳ `attendance.py` — منطق کسب‌وکار

`AttendanceTracker` یک state machine ساده است: هر `worker_id` یا `in` است یا `out`، و `toggle()` بین این دو جابه‌جا می‌کند.

```python
def toggle(self, worker_id: str, worker_name: str) -> Optional[str]:
    """... Returns the new state, or None if `worker_id` is not a registered
    worker. Unknown faces must be promoted to a worker first — this method
    never creates worker rows."""
```

آن جملهٔ آخر در docstring نتیجهٔ مستقیم یک باگ است: نسخهٔ قبلی اگر کارگر را پیدا نمی‌کرد، **خودش یک ردیف `Worker` می‌ساخت** تا بتواند کلید خارجی رویداد را پر کند. نتیجه: ردیف‌هایی با نام `guest_001` در جدول کارگرها ظاهر می‌شدند (بخش ۱۰.۴).

سایر مسئولیت‌ها:
- `_check_rollover()` — تشخیص تغییر روز و بستن روز قبل
- `_finalize_day()` — محاسبهٔ ساعات کارکرد و نوشتن JSON روزانه
- `detect_anomalies()` — ورود بدون خروج، شیفت بیش از حد طولانی، ورودهای مکرر
- `get_all_states()` — snapshot برای پنل ادمین

### ۳.۴ `main_fastapi.py` — لایهٔ وب

بزرگ‌ترین فایل پروژه (~۱۷۵۰ خط) و متأسفانه پرمسئولیت‌ترین آن. مسئولیت‌ها:

1. حلقهٔ دوربین و ترد پس‌زمینه + watchdog
2. استریم MJPEG (`_mjpeg_generator` با `frame_seq` برای جلوگیری از ارسال فریم تکراری)
3. WebSocket برای push رویدادها
4. API عمومی داشبورد (بدون احراز هویت)
5. API ادمین (HTTP Basic — بخش ۹.۲)
6. API با JWT + RBAC برای مصرف ماشینی
7. health/readiness/metrics

**نقد صریح:** این فایل باید شکسته شود. کمینه به `routers/dashboard.py`، `routers/admin.py`، `routers/auth.py` و `camera_service.py`. دلیل نشکستن تا امروز: ریسک رگرسیون در حالی که باگ‌های عملکردی اولویت داشتند.

### ۳.۵ `cv_modules/` — چهار ماژول مستقل

| ماژول | ورودی | خروجی | نقش در تصمیم |
|-------|-------|-------|--------------|
| `quality.py` | برش چهره | `overall_score` (۰..۱) | زیر آستانه → چهره کامل نادیده گرفته می‌شود |
| `liveness.py` | خاکستری + لندمارک | `is_live` | تصویر روی کاغذ/مانیتور → رد |
| `alignment.py` | برش + لندمارک | برش ۱۱۲×۱۱۲ | **فقط نمایش/ذخیره** — از انکود حذف شد |
| `tracking.py` | لیست bbox | `track_id` + هویت هموارشده | جلوگیری از لرزش هویت بین فریم‌ها |

اینکه `alignment` از مسیر انکود بیرون کشیده شد یکی از کلیدی‌ترین اصلاحات این نسخه است — توضیح در بخش ۱۰.۳.

---
## ۴. جریان داده End-to-End

### ۴.۱ سناریو الف: کارگر شناخته‌شده وارد می‌شود

```
t=0.00  camera_loop: read_frame() → raw (640×480 BGR)
t=0.01  recognize(raw):
          face_locations(small)      → [(50,180,110,120)]  در مقیاس ۰.۵
          ×2 → full_locations        → [(100,360,220,240)]
          face_encodings(rgb_full)   → vec[128]
          quality 0.72 ≥ 0.4  ✓
          liveness is_live=True ✓
          face_distance(known, vec)  → min = 0.31 ≤ 0.6 → "W001"
t=0.06  _process_results:
          pid="W001" و startswith("W") ✓
          cooldown: آخرین رویداد > 8s ✓
          attendance.toggle("W001", "payman") → "in"
          _set_event({type:"in", name:"payman", ...})
             ├─ REST: /api/dashboard → latest_event
             └─ WS : broadcast_event() → push فوری
t=0.07  cam_lock: raw_frame = raw ; frame = draw_boxes(raw) ; frame_seq += 1
t=0.08  time.sleep(0.01)   ← GIL آزاد می‌شود
```

### ۴.۲ سناریو ب: چهرهٔ ناشناس

```
_match_dlib → min_dist = 0.78 > tolerance → person_id = None
      ↓
unknown_enc نگه داشته می‌شود (اولین چهرهٔ ناشناس فریم)
      ↓
اگر از آخرین ثبت مهمان > guest_capture_interval (۵ ثانیه) گذشته:
      db.add_guest([enc], face_image=crop) → "guest_004"
      guest_lock: guest_id = "guest_004"
      recognizer.invalidate_cache()   ← دفعهٔ بعد شناخته می‌شود
      ↓
هیچ رویداد حضوری ثبت نمی‌شود. فقط یک کارت «NEW FACE» در داشبورد.
```

نکتهٔ ظریف: مهمان بلافاصله به لیست `get_all_known()` اضافه می‌شود. این تنها چیزی است که مانع تولید `guest_005`, `guest_006`, … در ثانیه‌های بعد می‌شود. اگر انکودینگ‌های همان شخص ناپایدار باشند، این مکانیزم شکست می‌خورد — و دقیقاً همین اتفاق افتاد (بخش ۱۰).

### ۴.۳ سناریو ج: ثبت‌نام ۶ زاویه

```
POST /api/registration/start {name}
    ├─ بررسی نام تکراری → 409
    └─ start_session(name)   → نشست فعال، step_index=0

camera_loop در هر تکرار:
    sess = get_session()
    if sess and sess.is_active:
        update_session(best_encoding, face_crop)   ← جمع‌آوری تدریجی
    overlay راهنمای زاویه روی MJPEG رسم می‌شود

GET /api/registration/status  (polling هر ۱ ثانیه)
    → {active, step, total_steps: 6, current_pose, is_done, encodings_collected}

POST /api/registration/commit
    → db.add_worker(name, sess.encodings, face_crops[0])
    → recognizer.invalidate_cache()
```

مسیر جایگزین و سریع‌تر `POST /api/workers/capture` است: یک نمونهٔ تک از `raw_frame` می‌گیرد. برای تست خوب است، برای تولید نه — یک نمونه، مقاومت کافی به تغییر نور و زاویه ندارد.

### ۴.۴ سناریو د: ارتقای مهمان از پنل ادمین

```
GET /api/admin/workers          → مهمان‌ها با آواتار «?»
POST /api/guests/guest_001/promote {name: "reza"}
    ├─ نام تکراری               → 409
    ├─ مهمان یافت نشد           → 404
    └─ promote_guest_to_worker():
          Worker جدید (W002)
          کپی همهٔ encodings مهمان
          Guest.promoted = 1
    → invalidate_cache() + به‌روزرسانی متریک‌ها
```

---

## ۵. تنظیمات و Configuration

همهٔ تنظیمات از `config.py` (Pydantic Settings) می‌آید و با `.env` قابل بازنویسی است.

| کلید | مقدار پیش‌فرض | اثر عملی |
|------|---------------|----------|
| `camera_index` | `0` | ایندکس وب‌کم |
| `process_scale` | `0.5` | مقیاس **تشخیص**. انکود همیشه روی فریم کامل |
| `tolerance` | `0.6` | حد فاصلهٔ اقلیدسی برای تطبیق. پایین‌تر = سخت‌گیرتر |
| `quality_threshold` | `0.4` | چهرهٔ تارتر از این کاملاً نادیده گرفته می‌شود |
| `liveness_threshold` | `0.55` | آستانهٔ زنده‌بودن |
| `max_encodings` | `10` | سقف نمونهٔ هر کارگر |
| `augment_cooldown_minutes` | `5` | فاصلهٔ زمانی افزودن خودکار نمونه |
| `cooldown_seconds` | `8` | فاصلهٔ لازم بین دو toggle یک نفر |
| `guest_capture_interval` | `5` | فاصلهٔ لازم بین ساخت دو مهمان |
| `database_url` | `sqlite:///data/cv_attendance.db` | |
| `secret_key` | مقدار توسعه | **باید در تولید عوض شود** |
| `metrics_enabled` | `True` | `/metrics` |

### ۵.۱ رابطهٔ خطرناک بین دو پارامتر

`process_scale` و `tolerance` مستقل به‌نظر می‌رسند اما نیستند. کاهش `process_scale` هم چهره‌های کوچک را از دست می‌دهد و هم — در نسخهٔ باگ‌دار که انکود روی فریم کوچک انجام می‌شد — واریانس انکودینگ را بالا می‌برد و عملاً `tolerance` را بی‌معنا می‌کرد. با اصلاح انجام‌شده، این وابستگی قطع شد: تغییر `process_scale` دیگر روی فاصله‌ها اثر ندارد.

**پیشنهاد ثبت‌شده:** یک تست رگرسیون که تضمین کند تغییر `process_scale` فاصلهٔ انکودینگ‌های یک تصویر ثابت را بیش از حد جابه‌جا نمی‌کند.

---

## ۶. Deployment و DevOps

| ابزار | فایل | نکته |
|-------|------|------|
| Docker | `Dockerfile` | build چندمرحله‌ای، نصب dlib سنگین‌ترین لایه است |
| Compose | `docker-compose.yml` | app + redis + nginx |
| Nginx | `nginx/conf.d/default.conf` | reverse proxy؛ برای MJPEG باید buffering خاموش باشد |
| Alembic | `alembic/` | مهاجرت‌های اسکیمای دیتابیس |
| pre-commit | `.pre-commit-config.yaml` | لینت پیش از commit |
| اجرای محلی | `run_attendance.bat` | `uvicorn main_fastapi:app --port 5000` |

**محدودیت مهم:** `workers: int = 4` در کانفیگ گمراه‌کننده است. این اپ **نمی‌تواند** چند worker پروسه‌ای داشته باشد، چون دوربین یک منبع انحصاری است و هر پروسه یک `camera_loop` جدا می‌سازد. اجرای تولیدی باید تک‌پروسه با چند ترد باشد.

---

## ۷. تست‌ها و کیفیت کد

وضعیت فعلی: **۱۰۰ تست، همه پاس** (`pytest tests -q` → `100 passed in 40.70s`).

| فایل | پوشش |
|------|------|
| `test_models.py` | مدل‌های ORM، روابط، cascade |
| `test_repository.py` | CRUD، نام تکراری، سقف نمونه، حذف آخرین نمونه |
| `test_attendance.py` | toggle، rollover، ساعات، anomalies |
| `test_auth.py` | JWT، انقضا، RBAC |
| `test_config.py` | خواندن env |
| `test_api_integration.py` | مسیرهای HTTP با `TestClient` |
| `test_registration.py` | نشست ۶ زاویه |
| `test_server_live.py` | سرور واقعاً بالا می‌آید |
| `load_test.py` / `load_test.js` | بار همزمان (k6) |
| `mutation_test.py` | کیفیت خود تست‌ها |

### ۷.۱ شکاف‌های واقعی پوشش

اینها را صادقانه ثبت می‌کنیم:

1. **هیچ تست خودکاری برای مسیر CV وجود ندارد.** باگ اصلی این نشست (انکود روی فریم کوچک) با ۱۰۰ تست سبز کشف نشد، چون هیچ تستی تصویر واقعی را از خط لوله عبور نمی‌دهد. تست لازم: دو عکس از یک شخص → فاصله باید < tolerance؛ عکس دو شخص متفاوت → فاصله باید > tolerance.
2. **endpointهای ادمین تست واحد ندارند.** در این نشست دستی با `TestClient` بررسی شدند (بخش ۱۰.۶) اما در `tests/` ثبت نشده‌اند.
3. **هیچ تستی برای پاسخ‌دهی تحت بار CPU نیست.** باگ `ERR_ABORTED` هم از دید تست‌ها پنهان بود.

---

## ۸. مانیتورینگ و Observability

| مسیر | نوع | محتوا |
|------|-----|-------|
| `/healthz` | liveness | همیشه ۲۰۰ اگر پروسه زنده باشد |
| `/readyz` | readiness | اتصال دیتابیس + وضعیت دوربین |
| `/metrics` | Prometheus | متریک‌های زیر |
| `/camera/status` | JSON | باز/بسته + آخرین خطای دوربین |

متریک‌ها:

- `WORKERS_COUNT` (Gauge) — تعداد کارگرهای فعال
- `GUESTS_COUNT` (Gauge) — مهمان‌های ارتقانیافته
- `ATTENDANCE_EVENTS_TOTAL{type=in|out}` (Counter)
- `RECOGNITION_TOTAL{result=known|unknown}` (Counter)
- متریک‌های تأخیر HTTP از `metrics_middleware`

لاگ‌ها ساخت‌یافته (`log_json=True`) هستند تا در تولید قابل جست‌وجو باشند.

**شکاف:** هیچ متریکی برای *تأخیر خط لوله تشخیص* یا *توزیع فاصلهٔ تطبیق* وجود ندارد. اگر `recognition_distance` به‌عنوان Histogram ثبت می‌شد، باگ «یک نفر = سه کارگر» در نمودار به‌صورت انبوهه‌ای بالای ۰.۶ **قبل از** شکایت کاربر دیده می‌شد. این مهم‌ترین پیشنهاد observability این ژورنال است.

---

## ۹. تحلیل تصمیمات طراحی

### ۹.۱ SQLite در برابر PostgreSQL

انتخاب: SQLite. دلیل: نصب صفر، فایل قابل کپی/بکاپ، برای <۲۰۰ کارگر کافی. هزینه: نوشتن همزمان محدود، بدون replication. مسیر مهاجرت باز است چون همه‌چیز از SQLAlchemy می‌گذرد و `database_url` تنها نقطهٔ تغییر است.

### ۹.۲ احراز هویت پنل ادمین: Basic و نه JWT

در نسخهٔ ۳.۰.۰ پنل **هیچ** احراز هویتی نداشت («تصمیم آگاهانه» با این استدلال که فقط روی
`127.0.0.1` استفاده می‌شود). این استدلال با `HOST=0.0.0.0` در `.env` نمی‌خواند و در نسخهٔ
۳.۱.۲ رفع شد: `HTTPBasic` روی هر شش مسیر ادمین.

**چرا Basic و نه همان JWT موجود؟** پنل یک صفحهٔ HTML بدون فرم لاگین است. Basic باعث
می‌شود مرورگر خودش دیالوگ اعتبارنامه را بیاورد و آن را روی هر `fetch` به همان origin
تکرار کند — بدون اینکه `admin.html` نیاز به مدیریت چرخهٔ عمر توکن داشته باشد. مسیرهای
ماشینی (`/workers`, `/users`, `/attendance/*`) همان JWT + RBAC را نگه داشتند.

مقایسه با `secrets.compare_digest` انجام می‌شود، نه `==` — تا زمان اجرای مقایسه اطلاعاتی
از رمز لو ندهد.

محافظت دوم که از قبل بود: جلوگیری از Path Traversal در سرو تصویر:

```python
if not re.fullmatch(r"(W\d{3,}|guest_\d{3,})", identifier):
    raise HTTPException(status_code=404, detail="Not found")
```

تأیید شده: `GET /api/admin/face/..%2F..%2Fetc%2Fpasswd` → `404`.

⚠️ رمز پیش‌فرض `admin:admin` است و باید در `.env` عوض شود.

### ۹.۳ MJPEG در برابر WebRTC

MJPEG انتخاب شد چون در `<img src>` بدون هیچ کتابخانه‌ای کار می‌کند. هزینه: پهنای باند بالا. بهینه‌سازی انجام‌شده: `frame_seq` باعث می‌شود فریم تکراری دوباره encode/ارسال نشود و در نبود فریم جدید `sleep(0.05)` انجام شود.

### ۹.۴ چرا مهمان‌ها در لیست تطبیق هستند؟

اگر مهمان‌ها در `get_all_known()` نبودند، هر فریم یک مهمان جدید می‌ساخت. با حضورشان در لیست، بار دوم «شناخته‌شده» محسوب می‌شوند. اما تصمیم گرفتیم مهمان **هرگز** حضور ثبت نکند:

```python
if not pid.startswith("W"):
    continue
```

منطق: حضور و غیاب یک ادعای هویتی است؛ تا اپراتور نامی تأیید نکند، رکورد بی‌معناست.

### ۹.۵ آستانهٔ ۰.۶ برای dlib

مقدار توصیه‌شدهٔ رسمی `face_recognition` است. با `0.55` سخت‌گیرتر می‌شود (احتمال شناخته‌نشدن بیشتر)، با `0.65` شل‌تر (احتمال هویت اشتباه). عدد فعلی نگه داشته شد چون مشکل واقعی آستانه نبود — کیفیت انکودینگ بود.

---
## ۱۰. شکار باگ: روایت کامل یک نشست دیباگ عمیق

این بخش ارزشمندترین قسمت این ژورنال است. روایت واقعی یک نشست است که با دو جملهٔ کاربر شروع شد:

> «یک نفر رو ۳ کارگر مختلف در نظر گرفته! اضافه کردن و رجیستر کارگر باگ داره»
> «`net::ERR_ABORTED http://127.0.0.1:5000/api/dashboard`»

دو شکایت، که در نهایت به **هفت باگ مستقل** رسید. مهم است بدانید تست‌ها در تمام این مدت **سبز** بودند.

### ۱۰.۱ باگ ۱: `ERR_ABORTED` — چرا داشبورد قطع می‌شد

**نشانه:** در کنسول مرورگر:
```
خطا: signal is aborted without reason
net::ERR_ABORTED http://127.0.0.1:5000/api/dashboard
net::ERR_ABORTED http://127.0.0.1:5000/api/attendance/report
```

**فرضیهٔ اول (اشتباه):** مشکل CORS یا خطای سرور. → رد شد؛ لاگ سرور هیچ خطایی نداشت.

**سرنخ:** خود مرورگر درخواست را لغو می‌کرد. در [dashboard.html](file:///s:/TRAE/CV_Attendance/templates/dashboard.html#L133-L144):

```javascript
var timeout = path.includes("capture") ? 15000 : 5000
var ctrl = new AbortController()
var timer = setTimeout(function(){ctrl.abort()}, timeout)
```

پس منبع `abort` خودمان بودیم: پاسخ بیش از ۵ ثانیه طول می‌کشید.

**اندازه‌گیری:** با یک اسکریپت موقت زمان پاسخ اندازه‌گیری شد → درخواست‌ها به timeout می‌خوردند، یعنی >۵۰۰۰ms برای یک کوئری که باید چند میلی‌ثانیه باشد.

**علت واقعی — دو عامل همزمان:**

۱. هر دو هندلر `async def` بودند:
```python
@app.get("/api/dashboard")
async def api_dashboard():        # ← روی event loop
    workers = db.list_workers()   # ← کوئری مسدودکنندهٔ SQLite
```
در FastAPI، `async def` روی event loop اجرا می‌شود. یک فراخوانی مسدودکنندهٔ همگام در آن، **کل** event loop را متوقف می‌کند — یعنی همهٔ درخواست‌های دیگر هم منتظر می‌مانند.

۲. حلقهٔ دوربین هیچ‌گاه GIL را رها نمی‌کرد:
```python
while not shutdown_event.is_set():
    ...
    recognizer.recognize(raw)     # CPU-bound سنگین
    _process_results(results)
    # هیچ sleep ای نبود ← گرسنگی تردهای HTTP
```

ترکیب این دو: ترد دوربین GIL را نگه می‌داشت، event loop نوبت نمی‌گرفت، پاسخ از ۵ ثانیه می‌گذشت، مرورگر لغو می‌کرد.

**اصلاح:**

```python
# main_fastapi.py — تبدیل به سنکرون تا در threadpool اجرا شود
@app.get("/api/dashboard")
def api_dashboard():
    """Declared sync on purpose: every call does blocking DB work, so Starlette
    runs it in the threadpool instead of stalling the event loop (which made the
    browser's 5s fetch timeout abort while the camera thread held the GIL)."""
```

```python
# camera_loop — رهاسازی صریح GIL
            elif results:
                _process_results(results)

            # Yield the GIL so HTTP handlers stay responsive while recognition
            # runs continuously.
            time.sleep(0.01)
```

**نتیجهٔ اندازه‌گیری‌شده:** از timeout (>۵۰۰۰ms) به **~۰.۹–۱.۲ ثانیه**.

**نقد صادقانه:** ~۱ ثانیه هم زیاد است. علت باقی‌مانده این است که `/api/dashboard` هر بار همهٔ کارگرها و مهمان‌ها را کوئری می‌کند و `recognize()` هم CPU را اشغال کرده است. راه‌حل درست: کش snapshot در حافظه که `camera_loop` به‌روزش کند و هندلر فقط بخواند. ثبت شد در Roadmap.

### ۱۰.۲ باگ ۲: انکودینگ روی فریم کوچک‌شده — ریشهٔ «یک نفر = سه کارگر»

**نشانه:** یک شخص واحد مقابل دوربین، و هر چند ثانیه یک `guest_XXX` جدید ساخته می‌شد.

**فرضیهٔ اول:** `tolerance=0.6` خیلی سخت‌گیر است. → **رد شد**، و رد کردنش مهم‌ترین لحظهٔ این نشست بود.

**آزمایش تعیین‌کننده:** انکودینگ‌های ذخیره‌شدهٔ همان سه «مهمان» — که همه از یک شخص بودند — از دیتابیس خوانده شد و فاصلهٔ دوبه‌دو محاسبه شد:

```
guest_001 <-> guest_002 = 0.7003
guest_001 <-> guest_003 = 0.5805
guest_002 <-> guest_003 = 0.7461
                          ────────
tolerance               = 0.6
```

این اعداد فاجعه‌بار هستند. سه بردار از **یک صورت** باید فاصلهٔ ~۰.۲–۰.۳ داشته باشند. دو جفت از سه جفت، بالای آستانه‌اند. اگر آستانه را تا ۰.۷۵ بالا می‌بردیم که این‌ها یکی شوند، افراد مختلف هم یکی می‌شدند. **پس مشکل آستانه نبود؛ خود بردارها بی‌کیفیت بودند.**

**ریشه:** در `_recognize_dlib` هم تشخیص و هم انکود روی فریم کوچک‌شده انجام می‌شد:

```python
# نسخهٔ باگ‌دار
small = cv2.resize(frame, (0,0), fx=self.process_scale, fy=self.process_scale)
rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
locations = face_recognition.face_locations(rgb_small)
encodings = face_recognition.face_encodings(rgb_small, locations)   # ← فاجعه
```

با `process_scale=0.5`، صورتی که در فریم کامل ۱۶۰px بود، ۸۰px می‌شد. شبکهٔ ResNet دی‌لیب ورودی ~۱۵۰px می‌خواهد و صورت ۸۰px را باید بزرگ کند — یعنی درون‌یابی و از دست رفتن جزئیات. هر فریم به‌خاطر لرزش تشخیص، برش کمی متفاوت می‌داد و بردار خروجی به‌شدت جابه‌جا می‌شد.

**اصلاح:** تشخیص ارزان روی فریم کوچک بماند، اما مختصات به مقیاس کامل برگردانده شود و انکود روی فریم کامل انجام شود:

```python
small = cv2.resize(frame, (0, 0), fx=self.process_scale, fy=self.process_scale)
rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

locations = face_recognition.face_locations(rgb_small)
if not locations:
    return []

scale = int(1 / self.process_scale)
# Detection is cheap at reduced scale, but the encoder must see the
# full-resolution face: dlib's ResNet expects ~150px input, and encoding
# a downscaled face produces vectors that don't compare against
# full-resolution ones (distances drift well past `tolerance`).
full_locations = [
    (t * scale, r * scale, b * scale, l * scale) for (t, r, b, l) in locations
]
encodings = face_recognition.face_encodings(rgb_full, full_locations)
```

**درس:** «برای سرعت، کوچک کن» یک بهینه‌سازی درست است — اما فقط برای **تشخیص**. برای **انکود** یک باگ صحت است که خودش را به‌شکل «آستانه بد است» جا می‌زند.

### ۱۰.۳ باگ ۳: انکود مجدد از تصویر align‌شدهٔ ۱۱۲×۱۱۲

عامل دوم واریانس. کد قبلی پس از align کردن چهره، **دوباره** از تصویر align‌شده انکود می‌گرفت:

```
face_crop (مثلاً ۱۶۰×۱۶۰)
   → align_face() → ۱۱۲×۱۱۲   (resize + affine warp)
   → face_encodings(aligned)   ← انکود دوم روی تصویر تخریب‌شده
```

دو مشکل:
1. دی‌لیب **خودش** از روی لندمارک‌ها به‌صورت داخلی align می‌کند. align دستی یک تبدیل هندسی اضافه است، نه بهبود.
2. resize به ۱۱۲×۱۱۲ اطلاعات را کم می‌کند — دقیقاً همان مشکل باگ ۲ در مقیاس کوچک‌تر.

**اصلاح:** align فقط برای نمایش و ذخیرهٔ عکس بماند:

```python
# Alignment is kept for display/storage only. Re-encoding the
# aligned 112x112 crop is deliberately skipped: dlib already aligns
# internally from landmarks, so a second resize only adds variance
# between encodings of the same person.
aligned_face = face_crop
```

### ۱۰.۴ باگ ۴: مسیر ثبت‌نام کاملاً ناهمخوان با مسیر زمان اجرا

**نشانه:** «اضافه کردن و رجیستر کارگر باگ داره» — کارگری که تازه ثبت می‌شد، شناخته نمی‌شد.

**علت:** مسیر `capture` یک خط لولهٔ کاملاً جدا داشت:

| | ثبت‌نام (قبل) | زمان اجرا |
|--|--------------|-----------|
| منبع فریم | `frame` (**با کادر سبز و متن رسم‌شده**) | `raw` |
| مقیاس انکود | `fx=0.25` | `process_scale=0.5` |
| gate کیفیت | نداشت | داشت |
| liveness | نداشت | داشت |

یعنی بردار ذخیره‌شده در دیتابیس با بردارهای زمان اجرا **قابل مقایسه نبود**. مستطیل سبز روی صورت هم مستقیماً ورودی شبکه می‌شد.

**اصلاح:** مسیر ثبت‌نام همان تابع `recognize()` را صدا می‌زند، از `raw_frame` استفاده می‌کند:

```python
with cam_lock:
    current_frame = raw_frame.copy() if raw_frame is not None else None
...
with recognition_lock:
    results = recognizer.recognize(current_frame)
best = _best_face(results)
seed_enc, bbox = best
face_crop = _crop_face(current_frame, bbox)
collected = [seed_enc]
wid = db.add_worker(name, collected, face_image=face_crop)
```

برای این کار یک متغیر گلوبال جدید اضافه شد:

```python
cam_lock = threading.Lock()
frame: Optional[np.ndarray] = None
raw_frame: Optional[np.ndarray] = None      # ← جدید
frame_seq = 0
```

**درس مهم:** اگر داده‌ای در زمان *ثبت‌نام* تولید و در زمان *تشخیص* مقایسه می‌شود، هر دو مسیر باید **دقیقاً یک تابع** را صدا بزنند. هر شعبهٔ موازی، دیر یا زود واگرا می‌شود.

### ۱۰.۵ باگ ۵: `attendance.toggle()` که خودش کارگر می‌ساخت

**نشانه:** ردیف‌هایی با نام `guest_001`, `guest_002`, `guest_003` در جدول **کارگرها**.

**علت:** `toggle()` برای درج رویداد به `worker.id` نیاز داشت. اگر پیدا نمی‌کرد، به‌جای انصراف، یک `Worker` جدید می‌ساخت. مهمان‌ها هم `toggle` صدا می‌زدند، پس هر مهمان تبدیل به «کارگر» می‌شد.

**اصلاح دو لایه:**

```python
# attendance.py — دیگر هرگز کارگر نمی‌سازد
def toggle(self, worker_id: str, worker_name: str) -> Optional[str]:
    """Toggle a registered worker's in/out state.
    Returns the new state, or None if `worker_id` is not a registered
    worker. Unknown faces must be promoted to a worker first — this method
    never creates worker rows."""
    ...
        worker = (
            db.query(Worker)
            .filter(Worker.worker_id == worker_id, Worker.is_active == 1)
            .first()
        )
        if worker is None:
            return None
```

```python
# main_fastapi.py — مهمان‌ها اصلاً وارد مسیر حضور نمی‌شوند
# Guests are recognized (so they aren't re-registered) but have no
# attendance record until an operator promotes them to a worker.
if not pid.startswith("W"):
    continue
...
state = attendance.toggle(pid, r["name"])
if state is None:
    continue
```

این تغییر ۴ تست را شکست (چون تست‌ها به رفتار «ساخت خودکار» تکیه کرده بودند). با یک fixture صریح رفع شد:

```python
def test_toggle_unregistered_worker_is_ignored(self, attendance):
    """An unpromoted guest must not create a worker row or an event."""
    assert attendance.toggle("guest_001", "guest_001") is None
    assert attendance.count_in() == 0
```

**درس:** وقتی یک تست پس از رفع باگ می‌شکند، اول بپرسید «آیا تست رفتار غلط را تثبیت کرده بود؟» اینجا جواب مثبت بود.

### ۱۰.۶ باگ ۶: خطاهای مدیریت‌نشده در ارتقای مهمان

بعد از ساخت پنل ادمین، endpointها با `TestClient` بررسی شدند. نتیجهٔ اولیه:

```
promote missing guest → ValueError: Guest 'guest_zzz' not found   ← ۵۰۰ خام
```

`promote_guest_to_worker()` در حالت‌های خطا `ValueError` و `DuplicateNameError` پرتاب می‌کند، اما endpoint ادمین هیچ‌کدام را نمی‌گرفت. یعنی خطای کاربر (نام تکراری یا مهمان حذف‌شده) به traceback و ۵۰۰ تبدیل می‌شد.

همچنین سه خط **کد مرده** در همان تابع بود:

```python
wid = db.promote_guest_to_worker(guest_id, name)
with guest_lock:
    guest_id = None      # ← فقط پارامتر محلی تابع را null می‌کند؛ بی‌اثر
with event_lock:
    event = None         # ← متغیر محلی جدید می‌سازد؛ بی‌اثر
```

بدون `global`، این دو انتساب هیچ اثری روی وضعیت مشترک ندارند. حذف شدند.

**نسخهٔ اصلاح‌شده:**

```python
@app.post("/api/guests/{guest_id}/promote", tags=["Admin"])
async def api_admin_promote_guest(guest_id: str, request: Request):
    """Promote a guest to a registered worker (admin panel, no auth)."""
    body = await request.json() if request.headers.get("content-type") else {}
    name = ((body or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")

    try:
        wid = db.promote_guest_to_worker(guest_id, name)
    except DuplicateNameError:
        raise HTTPException(status_code=409, detail=f"A worker named '{name}' already exists")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    recognizer.invalidate_cache()
    WORKERS_COUNT.set(db.worker_count())
    GUESTS_COUNT.set(db.guest_count())
    return {"ok": True, "worker_id": wid, "name": name}
```

**نتیجهٔ تأیید نهایی با `TestClient`:**

```
admin page:            200
/api/admin/workers:    200  (worker_count=1, sample_total=10)
face traversal probe:  404   ← ..%2F..%2Fetc%2Fpasswd مسدود شد
delete bogus sample:   400  {"error":"Sample not found"}
add sample, no camera: 503  {"error":"Camera is not running"}
promote missing guest: 404  {"error":"Guest 'guest_zzz' not found"}
promote dup name:      409  {"error":"A worker named 'payman' already exists"}
```

### ۱۰.۷ باگ ۷: مسیرهای اشتباه در `admin.html`

پنل ادمین به `/registration/start` و `/registration/status` درخواست می‌زد، اما مسیرهای واقعی `/api/registration/*` هستند. علاوه بر آن، نام فیلدها هم اشتباه بود (`is_active` به‌جای `active`، `step_index` به‌جای `step`) و مرحلهٔ `commit` هم فراخوانی نمی‌شد — یعنی حتی با مسیر درست، کارگر هرگز ذخیره نمی‌شد.

اصلاح: مسیرها، نام فیلدها مطابق پاسخ واقعی سرور، فراخوانی `POST /api/registration/commit` پس از اتمام، و `abort` در صورت timeout.

### ۱۰.۸ پاک‌سازی دیتابیس

پس از تأیید صریح کاربر («اره پاک کن»):

```powershell
Copy-Item data\cv_attendance.db data\cv_attendance.db.bak    # پشتیبان اول
```

سپس حذف شد: کارگر `guest_001` (+۱ رویداد)، `guest_002` (+۲ رویداد)، `guest_003` (+۱۹ رویداد)، و سه رکورد مهمان با عکس‌هایشان.

### ۱۰.۹ تأیید عملی اصلاح

پس از restart سرور با همان شخص مقابل دوربین:

- **قبل:** هر چند ثانیه یک `guest_XXX` جدید
- **بعد:** فقط **یک** مهمان (`guest_001`) ساخته شد و در ۱.۵ دقیقهٔ بعد **هیچ** هویت جدیدی اضافه نشد

این تنها معیار قابل قبول بود: نه تست سبز، نه بازبینی کد، بلکه رفتار واقعی سیستم با دوربین واقعی.

### ۱۰.۱۰ جمع‌بندی زنجیرهٔ علت

```
process_scale روی انکود  ─┐
align مجدد ۱۱۲×۱۱۲       ─┼→ بردارهای بی‌کیفیت (فاصلهٔ ۰.۵۸..۰.۷۵ برای یک نفر)
capture از frame مزین     ─┘         │
                                     ↓
                        هر فریم «ناشناس» تشخیص داده می‌شد
                                     ↓
                        add_guest() → guest_001, 002, 003...
                                     ↓
                        toggle() خودش Worker می‌ساخت
                                     ↓
                        «یک نفر = ۳ کارگر مختلف»
```

و به‌طور موازی:

```
async def + کوئری مسدودکننده  ─┐
camera_loop بدون sleep         ─┴→ پاسخ >۵s → AbortController → ERR_ABORTED
```

یک شکایت کاربر («۳ کارگر») در واقع **پنج** باگ به‌هم‌پیوسته بود. هیچ‌کدام با خواندن کد به‌تنهایی پیدا نشدند؛ همه با **اندازه‌گیری عدد واقعی** پیدا شدند.

---
## ۱۱. Roadmap و بهبودهای پیشنهادی

اولویت‌بندی بر اساس نسبت «ارزش به ریسک»:

### 🔴 اولویت بالا — بدهی فنی که هزینه‌اش را همین امروز می‌دهیم

| # | کار | دلیل |
|---|-----|------|
| ۱ | **تست رگرسیون خط لولهٔ CV** | دو عکس واقعی از یک نفر → assert فاصله < tolerance. این تنها تستی است که باگ ۱۰.۲ را می‌گرفت |
| ۲ | **ثبت‌نام ۲–۳ نفر واقعی** | با یک کارگر در دیتابیس، توانایی *تفکیک* هویت‌ها اثبات نمی‌شود |
| ۳ | **کش snapshot داشبورد** | حذف کوئری تکراری از مسیر داغ؛ پاسخ از ~۱s به ~۱۰ms |
| ۴ | **Histogram متریک `recognition_distance`** | باگ‌های کیفیت انکودینگ را *قبل از* شکایت کاربر نشان می‌دهد |

### 🟡 اولویت متوسط — کیفیت و نگهداری

| # | کار | دلیل |
|---|-----|------|
| ۵ | شکستن `main_fastapi.py` به routers | ~۱۷۵۰ خط با ۷ مسئولیت |
| ۶ | تست واحد برای endpointهای ادمین | فعلاً فقط دستی تأیید شده‌اند |
| ۷ | نمایش فاصلهٔ خام تطبیق در پنل ادمین | `confidence` نسبی گمراه‌کننده است |
| ۸ | حذف یا مستندسازی `workers: int = 4` | با دوربین انحصاری چند-پروسه ممکن نیست |
| ۹ | فشرده‌سازی/کیفیت تنظیم‌پذیر MJPEG | مصرف پهنای باند |

### 🟢 بلندمدت — قابلیت‌های جدید

- مهاجرت کامل به InsightFace/ArcFace (۵۱۲ بُعد) به‌جای fallback دی‌لیب
- پشتیبانی چند دوربین با یک پروسهٔ مجزا به‌ازای هر دوربین و دیتابیس مشترک
- Liveness قوی‌تر (چالش فعال: پلک بزن / سر بچرخان)
- گزارش‌های تحلیلی (میانگین ساعات، الگوی تأخیر)
- اپلیکیشن موبایل برای مشاهدهٔ گزارش

---

## ۱۲. Lessons Learned

درس‌های واقعی این نشست، نه توصیه‌های کلی:

**۱. «تست‌ها سبزند» یعنی «تست‌ها چیزی را که شکسته است پوشش نمی‌دهند».**
۱۰۰ تست پاس بود در حالی که هستهٔ محصول — تشخیص هویت — کاملاً خراب بود. تست‌ها ORM و منطق کسب‌وکار را می‌آزمودند، نه خط لولهٔ CV را.

**۲. عدد اندازه‌گیری‌شده > حدس معقول.**
حدس «tolerance سخت‌گیر است» کاملاً معقول بود. اگر بر اساسش آستانه را بالا می‌بردیم، باگ *پنهان* می‌شد و به یک باگ بدتر (هویت اشتباه بین دو نفر) تبدیل می‌شد. محاسبهٔ سهٔ عدد `0.7003 / 0.5805 / 0.7461` مسیر را برگرداند.

**۳. بهینه‌سازی سرعت می‌تواند یک باگ صحت باشد.**
`process_scale` برای سرعت اضافه شده بود و کار می‌کرد — روی تشخیص. اما وقتی مرز بین «تشخیص» و «انکود» رعایت نشد، به یک باگ صحت تبدیل شد که به‌شکل یک مشکل تنظیمات ظاهر می‌شد.

**۴. هر مسیر موازی برای تولید داده، دیر یا زود واگرا می‌شود.**
مسیر ثبت‌نام و مسیر تشخیص باید یک تابع را صدا بزنند. داشتن `fx=0.25` در یکی و `0.5` در دیگری، اجتناب‌ناپذیر بود چون دو کد جدا بودند.

**۵. در پایتون، `async def` بدون I/O غیرمسدودکننده یک تله است.**
`def` ساده در FastAPI **سریع‌تر** است اگر کار مسدودکننده دارید، چون به threadpool می‌رود. این خلاف شهود عمومی «async همیشه بهتر است» است.

**۶. یک ترد CPU-bound بدون `sleep` می‌تواند کل وب‌سرور را بخواباند.**
GIL یعنی «تردهای من مستقل‌اند» یک فرض غلط است. `time.sleep(0.01)` — یک خط — کل مشکل پاسخ‌دهی را حل کرد.

**۷. `global` را فراموش کنید و کدتان بی‌صدا کار نمی‌کند.**
```python
with guest_lock:
    guest_id = None      # بدون global: یک متغیر محلی می‌سازد، هیچ خطایی هم نمی‌دهد
```
این نوع باگ نه crash می‌کند و نه در لاگ دیده می‌شود.

**۸. تستی که پس از رفع باگ می‌شکند، ممکن است خودش باگ را تثبیت کرده باشد.**
۴ تست `test_attendance.py` روی رفتار «ساخت خودکار کارگر» تکیه داشتند. اصلاح درست، تغییر تست بود نه برگرداندن کد.

**۹. تأیید نهایی باید در دنیای واقعی باشد.**
معیار پذیرش «فقط یک مهمان در ۱.۵ دقیقه» بود — با دوربین واقعی و شخص واقعی. هیچ تست واحدی جای این را نمی‌گیرد.

**۱۰. پشتیبان قبل از حذف، همیشه.**
`Copy-Item data\cv_attendance.db data\cv_attendance.db.bak` پیش از پاک‌سازی. رایگان است و یک بار که لازم شود، ارزشش را ثابت می‌کند.

---

## ۱۳. خلاصه اجرایی

### ۱۳.۱ وضعیت فعلی سیستم

| شاخص | مقدار |
|------|-------|
| نسخه | ۳.۲.۰ |
| تست‌ها | ۱۲۵ پاس (۴۶ ثانیه) |
| کارگر ثبت‌شده | ۱ (`W001` — payman، ۱۰ نمونه ۵۱۲ بُعدی) |
| مهمان | ۰ |
| پاسخ `/api/dashboard` | ۵۵–۸۹ms |
| ساخت هویت تکراری | برطرف شده (تأیید عملی ۱.۵ دقیقه) |
| احراز هویت پنل ادمین | ✅ HTTP Basic (نسخهٔ ۳.۱.۲) |
| مدیریت نمونه‌ها | ✅ مشاهدهٔ عکس، آپلود دستی، حذف کارگر (نسخهٔ ۳.۲.۰) |

### ۱۳.۲ ارزیابی صادقانه

**قوت‌ها:**
- حریم خصوصی کامل: هیچ داده‌ای از ماشین خارج نمی‌شود
- معماری لایه‌ای تمیز با یک دروازهٔ دیتابیس (`FaceRepository`)
- زیرساخت تولیدی واقعی: health check، متریک، لاگ ساخت‌یافته، Docker، Alembic
- پنل ادمین برای بازرسی نمونه‌های چهره — دقیقاً همان چیزی که دیباگ این باگ را ممکن کرد
- پوشش تست خوب در لایهٔ داده و منطق

**ضعف‌ها (بدون تعارف):**
- **خط لولهٔ CV تست واحد دارد اما تست end-to-end با عکس واقعی ندارد** — مهم‌ترین ضعف
- `main_fastapi.py` بیش از حد بزرگ و پرمسئولیت
- دیتابیس دمو فقط یک کارگر دارد؛ توانایی تفکیک چند نفر عملاً اثبات نشده
- پاسخ ~۱ ثانیه‌ای داشبورد هنوز کند است
- دو موتور تشخیص (InsightFace/dlib) پیچیدگی مضاعف بدون بهرهٔ کامل از اولی
- مقیاس‌پذیری افقی ذاتاً محدود (دوربین انحصاری)

### ۱۳.۳ آمادگی تولید

| محیط | ارزیابی |
|------|---------|
| کارگاه کوچک، شبکهٔ داخلی، `127.0.0.1` | ✅ آماده |
| شبکهٔ سازمانی چندکاربره | ⚠️ فقط با احراز هویت روی مسیرهای ادمین |
| قابل دسترس از اینترنت | ❌ توصیه نمی‌شود |

---

## ۱۴. ضمیمه: ساختار فایل‌های پروژه

```
CV_Attendance/
├── main.py                     # CLI: run / list / remove / web / export / guests
├── main_fastapi.py             # ⭐ اپ FastAPI: camera_loop، MJPEG، WS، همهٔ API
├── face_recognizer.py          # ⭐ خط لولهٔ CV (InsightFace + dlib fallback)
├── attendance.py               # منطق حضور: toggle، rollover، ساعات، anomaly
├── registration.py             # نشست ثبت‌نام ۶ زاویه
├── academic.py                 # بنچمارک/تأخیر برای گزارش دانشگاهی
├── auth.py / auth_fastapi.py   # JWT + RBAC + Dependencies
├── config.py                   # Pydantic Settings (تنها منبع کانفیگ)
├── database.py                 # engine + SessionLocal
├── redis_client.py             # کش اختیاری
│
├── models/
│   ├── base.py                 # Base + declarative
│   ├── worker.py               # Worker + FaceEncoding
│   ├── guest.py                # Guest
│   ├── attendance.py           # AttendanceEvent
│   ├── user.py                 # User (RBAC)
│   └── repository.py           # ⭐ FaceRepository — تنها دروازهٔ DB
│
├── cv_modules/
│   ├── quality.py              # blur / brightness / contrast / pose
│   ├── liveness.py             # blink / texture / motion
│   ├── alignment.py            # affine بر پایهٔ چشم‌ها (فقط نمایش)
│   └── tracking.py             # ردیابی چندچهره + هموارسازی هویت
│
├── templates/
│   ├── dashboard.html          # داشبورد اصلی (RTL)
│   ├── admin.html              # ⭐ پنل ادمین (RTL) — نمونه‌ها، ارتقا، ثبت‌نام
│   └── academic.html           # صفحهٔ بنچمارک
├── static/style.css
│
├── tests/                      # ۱۰۰ تست
│   ├── conftest.py             # fixtureها (db_session, registered_workers, ...)
│   ├── test_models.py / test_repository.py / test_attendance.py
│   ├── test_auth.py / test_config.py / test_registration.py
│   ├── test_api_integration.py / test_server_live.py
│   └── load_test.py / load_test.js / mutation_test.py
│
├── data/
│   ├── cv_attendance.db        # SQLite
│   ├── cv_attendance.db.bak    # پشتیبان پیش از پاک‌سازی
│   ├── faces/                  # W001.jpg, guest_00X.jpg
│   └── attendance/             # گزارش JSON روزانه
│
├── alembic/ + alembic.ini      # مهاجرت اسکیما
├── nginx/conf.d/default.conf   # reverse proxy
├── Dockerfile / docker-compose.yml
├── requirements.txt / requirements-test.txt
├── .env / .env.example / setup.cfg / .pre-commit-config.yaml
├── run_attendance.bat
├── ARCHITECTURE.md             # معماری (سند مرجع)
├── PROJECT_JOURNAL.md          # ⭐ این فایل — ژورنال «چرا»ها
├── CHANGELOG.md / README.md / proposal.md
```

---

## ۱۵. Changelog

### `3.2.0` — ۴ اوت ۲۰۲۶ — «مدیریت کامل نمونه‌های چهره»

تا این نسخه پنل ادمین فقط می‌توانست نمونهٔ جدید از دوربین بگیرد و نمونه حذف کند. سه شکاف
عملی باقی بود: نمی‌شد دید هر بردار از **چه تصویری** ساخته شده، نمی‌شد از یک عکس موجود
نمونه اضافه کرد (فقط دوربین زنده)، و کارگر اشتباه ثبت‌شده هیچ راه حذفی نداشت.

#### 🖼 دیدن عکس چهرهٔ هر نمونه

مشکل ریشه‌ای این بود که هنگام ثبت نمونه، فقط **بردار ۵۱۲ بُعدی** ذخیره می‌شد و برش چهره
دور ریخته می‌شد — پس هیچ راهی برای بازرسی بصری کیفیت نمونه‌ها وجود نداشت.

- `FaceRepository` پوشهٔ `data/faces/samples/{worker_id}/{encoding_id}.jpg` را می‌سازد و
  `add_worker` / `add_encoding_to_worker` برش چهره را در آن ذخیره می‌کنند
- `db.flush()` پیش از نام‌گذاری فایل لازم است چون نام فایل از `FaceEncoding.id` می‌آید و
  آن مقدار تا flush شدن session در دسترس نیست
- مسیر جدید `GET /api/admin/samples/{wid}/{sid}` تصویر را به‌صورت JPEG برمی‌گرداند
- `list_workers_detailed` فیلد `has_image` برمی‌گرداند تا رابط کاربری بداند بندانگشتی
  نشان دهد یا placeholder

**سازگاری با گذشته:** نمونه‌هایی که پیش از این نسخه ثبت شده‌اند عکسی روی دیسک ندارند، پس
`has_image=false` می‌گیرند و در جدول به‌جای بندانگشتی خط‌تیره دیده می‌شود. بازتولید عکس
برای آن‌ها ممکن نیست — بردار برگشت‌پذیر نیست.

#### 📤 افزودن نمونه به‌صورت دستی (آپلود فایل)

`POST /api/admin/workers/{wid}/samples/upload` با `multipart/form-data`. تصویر با
`cv2.imdecode` خوانده می‌شود، از همان `recognizer.recognize` عبور می‌کند (پس همان دروازهٔ
کیفیت و همان موتور فعال اعمال می‌شود) و بزرگ‌ترین چهره انتخاب می‌گردد. سقف ۱۰ مگابایت،
و خطای صریح `400` اگر چهره‌ای پیدا نشود یا فایل تصویر خوانا نباشد.

در `admin.html` یک `<input type="file">` مخفی برای همهٔ کارگرها بازاستفاده می‌شود و
`onchange` در هر کلیک دوباره bind می‌شود تا بداند نمونه برای کدام کارگر است.

#### 🗑 حذف کارگر

`DELETE /api/admin/workers/{wid}` — با تأیید در رابط کاربری.

**تصمیم طراحی: soft delete در دیتابیس، hard delete روی دیسک.** رکورد کارگر
`is_active=0` می‌شود و پاک نمی‌گردد، چون رویدادهای حضور به آن FK دارند و حذف فیزیکی
تاریخ حضور را می‌شکند (یا نیاز به cascade مخرب دارد). در مقابل، **دادهٔ بیومتریک کاملاً
پاک می‌شود**: بردارها از جدول و فایل‌های `samples/{wid}/` از دیسک حذف می‌شوند. این
تفکیک عمدی است — سابقهٔ حضور دادهٔ سازمانی است، بردار چهره دادهٔ شخصی.

پس از حذف، `recognizer.invalidate_cache()` و `WORKERS_COUNT.set(...)` صدا زده می‌شوند.

#### 🐛 باگ ۱۹: الگوی اعتبارسنجی شناسهٔ نمونه با نوع واقعی آن نمی‌خواند

برای جلوگیری از path traversal روی `GET /api/admin/samples/{wid}/{sid}` الگوی
`re.fullmatch(r"\d+", sid)` نوشته شده بود، با این فرض که شناسهٔ نمونه عدد صحیح است.
تست زنده `400` داد. با خواندن `models/worker.py` مشخص شد:

```python
FaceEncoding.id = Column(GUID(), primary_key=True, default=uuid.uuid4)
```

شناسه یک **UUID** است، نه عدد. الگو به `[0-9a-fA-F-]{8,36}` اصلاح شد — که هم UUID را
می‌پذیرد و هم `/` و `.` و `%2F` را رد می‌کند. درس: الگوی اعتبارسنجی را باید از **schema**
خواند، نه از حدس.

#### 🧪 تست

- `tests/test_repository.py`: پنج تست جدید برای ذخیره/حذف عکس نمونه (مجموع ۲۷)
- `tests/test_api_integration.py`: کلاس `TestAdminSampleImages` — path traversal،
  شناسهٔ بدشکل، ۴۰۴ برای UUID ناموجود، آپلود غیرعکس ۴۰۰، حذف کارگر ناموجود ۴۰۴ (مجموع ۳۱)

| بررسی زنده | نتیجه |
|-----------|-------|
| آپلود عکس واقعی به W001 | **۲۰۰** `{"ok":true}` |
| `has_image` پس از آپلود | `[False×9, True]` |
| `GET /api/admin/samples/W001/{uuid}` | **۲۰۰** `image/jpeg` ۱۴۱۰۵ بایت |
| حذف نمونه، سپس درخواست عکسش | **۴۰۴** (فایل هم پاک شد) |
| آپلود فایل متنی به‌جای عکس | **۴۰۰** |
| `..%2F..%2Fetc` در `sid` | **۴۰۴** (مسدود) |
| حذف کارگر بدون احراز هویت | **۴۰۱** |
| حذف کارگر ناموجود | **۴۰۴** |
| مجموعهٔ تست | **۱۲۵ passed** |

---

### `3.1.2` — ۴ اوت ۲۰۲۶ — «بستن پنل ادمین»

#### 🔒 پنل ادمین بدون هیچ محافظتی باز بود

شش مسیر `/admin` و `/api/admin/*` (به‌همراه `/api/guests/{id}/promote`) بدون احراز هویت
در دسترس بودند، در حالی که این مسیرها **نمونهٔ چهره حذف می‌کنند** و مهمان را به کارگر
ارتقا می‌دهند. با `HOST=0.0.0.0` یعنی هر کسی در شبکهٔ محلی می‌توانست داده را پاک کند.

`HTTPBasic` روی همهٔ شش مسیر اضافه شد با `secrets.compare_digest` (بررسی زمان-ثابت،
جلوگیری از timing attack). دو تنظیم جدید `admin_username` / `admin_password` در
`config.py` و `.env.example`.

**انتخاب Basic و نه JWT:** پنل یک صفحهٔ HTML ساده بدون فرم لاگین است. با Basic مرورگر
خودش دیالوگ می‌آورد و اعتبارنامه را روی هر `fetch` به همان origin تکرار می‌کند — بدون
اینکه `admin.html` نیاز به مدیریت توکن داشته باشد. مسیرهای `/workers`، `/users` و
`/attendance/*` از قبل JWT + RBAC داشتند و دست‌نخورده ماندند.

#### 🧪 تست

پنج تست در `TestAdminPanelAuth` (فایل `tests/test_api_integration.py`): بدون اعتبارنامه
۴۰۱، رمز غلط ۴۰۱، اعتبارنامهٔ درست ۲۰۰، و `DELETE` نمونه بدون احراز هویت ۴۰۱.

| بررسی زنده | نتیجه |
|-----------|-------|
| `GET /api/admin/workers` بدون احراز هویت | **۴۰۱** |
| با `admin:admin` | **۲۰۰** |
| با رمز غلط | **۴۰۱** |
| `GET /api/dashboard` (باید باز بماند) | **۲۰۰** |
| مجموعهٔ تست | **۱۱۲ passed** |

⚠️ رمز پیش‌فرض `admin:admin` است. پیش از قرار دادن سرور روی شبکه باید در `.env` عوض شود.

---

### `3.1.1` — ۴ اوت ۲۰۲۶ — «بازبینی و بهبود مسیر ArcFace»

بازبینی خط‌به‌خط `face_recognizer.py` پس از فعال‌سازی ArcFace. چهار مشکل واقعی پیدا و رفع شد.

#### 🐛 باگ ۱۵: منطق augmentation در مسیر ArcFace برعکس دی‌لیب بود

`_maybe_augment_arcface` **هیچ باند فاصله‌ای نداشت** و هر تطبیق باکیفیت را ذخیره می‌کرد،
در حالی که نسخهٔ دی‌لیب شرط `augment_min_distance < dist < tolerance` را داشت. نتیجه:
سهمیهٔ `max_encodings` با نمونه‌های تقریباً تکراری پر می‌شد و تنوع واقعی زوایا از دست می‌رفت.

باند به زبان شباهت کسینوسی ترجمه شد (`dist ≈ 1 - sim`):

```
1 - tolerance  <  sim  <  1 - augment_min_distance
     0.4       <  sim  <         0.8
```

#### 🐛 باگ ۱۶: محاسبهٔ confidence با **نسبت** شباهت‌ها

فرمول قبلی `sd[0] / max(sd[1], 0.001)` بود. این الگو از مسیر دی‌لیب کپی شده بود که با
**فاصله** کار می‌کند (همیشه مثبت). شباهت کسینوسی می‌تواند صفر یا منفی باشد، پس مقسوم‌علیه
بی‌معنا می‌شد: با `sd[1]` نزدیک صفر نسبت به عددی نجومی می‌رسید و با `sd[1]` منفی علامت
عوض می‌کرد. جایگزین شد با **حاشیه** (تفاضل) که برای شباهت درست است:

```python
margin = sd[0] - sd[1]
confidence = best_sim * min(1.0, 0.5 + margin)
```

#### 🐛 باگ ۱۷: نرمال‌سازی دیتابیس در حلقهٔ چهره‌ها + جهش لیست‌های فریم

کد قبلی داخل حلقهٔ `for det in dets` نام‌های `known_ids, known_encs` را **بازنویسی** می‌کرد.
برای فریم دو نفره، چهرهٔ دوم لیست فیلترشدهٔ چهرهٔ اول را می‌دید. همچنین نرمال‌سازی L2
تمام بردارهای دیتابیس برای **هر چهره** تکرار می‌شد. حالا ماتریس نرمال‌شده یک بار در هر
فریم (lazy، در اولین چهره) ساخته می‌شود و در متغیرهای جدا نگه داشته می‌شود.

#### 🐛 باگ ۱۸: `capture_encodings` هنوز از فریم کوچک‌شده انکود می‌گرفت

همان باگ ۳ (بخش ۱۰.۲) که در `_recognize_dlib` رفع شده بود، در این متد باقی مانده بود.
بدتر: ضریب بازگردانی مختصات **`* 4` هاردکد** بود، در حالی که `process_scale` قابل تنظیم
است (با `0.5` باید `* 2` باشد) — یعنی برش چهره به‌کل بیرون از کادر می‌افتاد. اکنون تشخیص
در مقیاس کوچک و انکود روی `rgb_full` انجام می‌شود و ضریب از `int(1 / process_scale)` می‌آید.

#### 🧹 پاک‌سازی

- پنج `import logging as _lg` تکراری **در بدنهٔ حلقه** → یک logger ماژول‌سطح
- سطح لاگ‌های نویزی (`0 detections`, `invalid bbox`, `quality gate`) از `warning` به `debug`
- حذف `self._use_fallback` که هیچ‌جا خوانده نمی‌شد

#### 🧪 تست جدید: `tests/test_recognizer.py`

هفت تست بدون نیاز به دوربین و بدون InsightFace (با `prefer_insightface=False`):

| تست | ادعا |
|-----|------|
| `test_near_duplicate_is_skipped` | `sim=0.95` ذخیره نمی‌شود |
| `test_borderline_view_is_stored` | `sim=0.6` ذخیره می‌شود |
| `test_non_match_is_skipped` | `sim=0.1` ذخیره نمی‌شود |
| `test_low_quality_is_skipped` | کیفیت زیر آستانه ذخیره نمی‌شود |
| `test_cooldown_blocks_second_call` | فراخوان دوم در cooldown بی‌اثر است |
| `test_mismatched_dimension_yields_no_match` | ۱۲۸ بُعدی با دیتابیس ۵۱۲ بُعدی → `None` |
| `test_matching_dimension_is_compared` | هم‌بُعد → تطبیق درست |

#### ✅ تأیید

| بررسی | نتیجه |
|-------|-------|
| مجموعهٔ تست | **۱۰۷ passed** (۱۰۰ قبلی + ۷ جدید) |
| بازشناسی W001 پس از تغییرات | `pid=W001 name=payman conf=0.472 dim=512` |
| `GetDiagnostics` | بدون خطا |

کاهش `confidence` از ۰.۹۰۶ به ۰.۴۷۲ **رگرسیون نیست**: عدد قبلی محصول نسبت
`sd[0]/sd[1]` بود که روی مقادیر کوچک منفجر می‌شد و همیشه به سقف ۱.۰ می‌چسبید. عدد جدید
معنای واقعی دارد — شباهت واقعی ضربدر حاشیه و کیفیت.

---

### `3.1.0` — ۴ اوت ۲۰۲۶ — «فعال‌سازی واقعی ArcFace»

تا این نسخه، کد خودش را «InsightFace به‌عنوان موتور اصلی» معرفی می‌کرد اما `insightface` و
`onnxruntime` **نصب نبودند** و مسیر اجرا همیشه fallback دی‌لیب بود. یعنی ادعای مستندات با
واقعیت اجرا نمی‌خواند. این نسخه آن شکاف را می‌بندد.

#### نصب و فعال‌سازی

- `onnxruntime==1.19.2` و `insightface==1.0.1` نصب و در `requirements.txt` پین شدند
- مدل‌های `buffalo_l` دانلود شدند: `det_10g.onnx` (SCRFD) + `w600k_r50.onnx` (ArcFace)
- `settings.prefer_insightface=True` و `settings.insightface_det_size=320` اضافه شد
- موتور فعال در استارتاپ لاگ می‌شود: `Recognition engine: insightface_arcface`

#### 🐛 باگ ۱۱: `det_size` غیرمربع → خطای broadcast در SCRFD

مقدار قبلی `(320, 240)` بود و باعث می‌شد `app.get()` همیشه استثنا بدهد و بی‌صدا به دی‌لیب
برگردد — یعنی InsightFace حتی اگر نصب هم بود کار نمی‌کرد:

```
ValueError: operands could not be broadcast together with shapes (140,) (160,)
    in distance2bbox()
```

SCRFD شبکهٔ anchor را از **ارتفاع** ورودی برای هر دو محور می‌سازد. اندازهٔ مربع الزامی است.
تست اندازه‌های مختلف روی یک فریم ثابت:

| `det_size` | تشخیص | تأخیر میانه |
|-----------|-------|-------------|
| (320, 240) | ❌ استثنا | — |
| (256, 256) | ✅ ۱ چهره | ۳۷۶ms |
| (320, 320) | ✅ ۱ چهره | ۳۹۵ms |
| (448, 448) | ✅ ۱ چهره | ۴۷۲ms |
| (640, 640) | ✅ ۱ چهره | ۶۵۹ms |

`320` انتخاب شد: کمترین تأخیر با حاشیهٔ اطمینان برای چهره‌های دورتر.

#### 🐛 باگ ۱۲: بارگذاری زیرمدل‌های بی‌استفاده

پکیج `buffalo_l` پنج مدل دارد اما پروژه فقط دو تای اول را استفاده می‌کند. با
`allowed_modules=["detection", "recognition"]` مدل‌های `genderage`, `landmark_2d_106`,
`landmark_3d_68` بارگذاری نمی‌شوند: تأخیر از **~۷۴۰ms به ~۶۲۵ms** در `det_size=640`.

#### 🐛 باگ ۱۳: انکود مجدد از تصویر align‌شده در مسیر InsightFace

همان باگ ۱۰.۳ که در مسیر دی‌لیب رفع شده بود، در مسیر InsightFace **باقی مانده بود**:
کد پس از align کردن، دوباره `app.get(aligned_rgb)` صدا می‌زد و بردار را جایگزین می‌کرد.
ArcFace خودش از روی ۵ لندمارک به ۱۱۲×۱۱۲ warp می‌کند، پس این یک warp اضافه و منبع واریانس بود.
حذف شد؛ `aligned_face` فقط برای نمایش/ذخیره می‌ماند.

#### 🐛 باگ ۱۴: خطای broadcast در تطبیق دی‌لیب پس از مهاجرت

`_match_dlib` بردارهای دیتابیس را بدون بررسی بُعد به `face_distance` می‌داد. بعد از اینکه
دیتابیس ۵۱۲ بُعدی شد، سوئیچ به موتور پشتیبان کرش می‌کرد:

```
ValueError: operands could not be broadcast together with shapes (2,512) (128,)
```

فیلتر هم‌بُعدی اضافه شد (مسیر InsightFace از قبل این فیلتر را داشت).

#### 🔄 مهاجرت داده

انکودینگ‌های ۱۲۸ بُعدی دی‌لیب با بردارهای ۵۱۲ بُعدی ArcFace **قابل مقایسه نیستند** و
بی‌صدا فیلتر می‌شدند — یعنی کارگر موجود هرگز شناخته نمی‌شد. پس از پشتیبان‌گیری
(`data/cv_attendance.db.pre-arcface.bak`)، نمونه‌ها از `data/faces/W001.jpg` بازسازی شدند:

```
W001 (payman): 10 × 128-d  →  1 × 512-d
removed 4 stale guest record(s)
```

#### ✅ تأیید نهایی

| بررسی | نتیجه |
|-------|-------|
| موتور فعال | `insightface_arcface`, ArcFace 512-d, det_size=320 |
| بازشناسی W001 روی فریم آزمون | `pid=W001 name=payman conf=0.906 dim=512` |
| مجموعهٔ تست | ۱۰۰ passed |
| `/api/dashboard` (۴ فراخوانی) | ۳۰۳ms سپس ۵۵ / ۸۵ / ۸۹ms |
| ثبت هویت تکراری در ۴۵ ثانیهٔ اجرای زنده | `guests=0` — هیچ مهمان کاذبی ساخته نشد |
| افزایش خودکار نمونه‌ها | ۱ → ۴ نمونه، همه ۵۱۲ بُعدی |

**نکتهٔ مهم برای ارائه:** پاسخ داشبورد از ~۱ ثانیه در نسخهٔ ۳.۰.۰ به **۵۵–۸۹ms** رسید، در حالی
که موتور سنگین‌تری (ArcFace با ~۳۸۰ms در هر فریم) اجرا می‌شود. این نتیجهٔ اصلاح باگ‌های
هم‌روندی بخش ۱۰.۱ است: هزینهٔ CPU بالاتر رفت اما پاسخ‌دهی HTTP بهتر شد.

---

### `3.0.0` — ۱ اوت ۲۰۲۶ — «یکپارچه‌سازی و رفع باگ‌های عمیق»

#### 🐛 رفع باگ

| # | باگ | فایل | اصلاح |
|---|-----|------|-------|
| ۱ | `ERR_ABORTED` روی `/api/dashboard` و `/api/attendance/report` | `main_fastapi.py` | `async def` → `def` (اجرا در threadpool) |
| ۲ | حلقهٔ دوربین GIL را رها نمی‌کرد | `main_fastapi.py` | `time.sleep(0.01)` در `camera_loop` |
| ۳ | انکودینگ روی فریم کوچک‌شده → «یک نفر = ۳ کارگر» | `face_recognizer.py` | تشخیص در مقیاس کوچک، انکود روی `rgb_full` |
| ۴ | انکود مجدد از تصویر align‌شدهٔ ۱۱۲×۱۱۲ | `face_recognizer.py` | align فقط برای نمایش/ذخیره |
| ۵ | `capture` از فریم مزین با کادر و `fx=0.25` | `main_fastapi.py` | `raw_frame` + همان `recognizer.recognize()` |
| ۶ | `attendance.toggle()` خودش `Worker` می‌ساخت | `attendance.py` | بازگشت `Optional[str]`، هرگز ردیف نمی‌سازد |
| ۷ | مهمان‌ها حضور ثبت می‌کردند | `main_fastapi.py` | `if not pid.startswith("W"): continue` |
| ۸ | `ValueError` مدیریت‌نشده در ارتقای مهمان → ۵۰۰ | `main_fastapi.py` | ۴۰۴ برای مهمان ناموجود، ۴۰۹ برای نام تکراری |
| ۹ | کد مردهٔ `guest_id = None` بدون `global` | `main_fastapi.py` | حذف شد |
| ۱۰ | `admin.html` به `/registration/*` (مسیر ناموجود) درخواست می‌زد | `templates/admin.html` | `/api/registration/*` + فیلدهای درست + `commit` |

#### ✨ قابلیت جدید: پنل ادمین

- `GET /admin` — رابط فارسی RTL
- `GET /api/admin/workers` — کارگرها + نمونه‌ها + مهمان‌ها (با `joinedload`)
- `GET /api/admin/face/{identifier}` — سرو JPEG با محافظت Path Traversal
- `POST /api/admin/workers/{wid}/samples` — افزودن نمونه از دوربین
- `DELETE /api/admin/workers/{wid}/samples/{sid}` — حذف نمونه (آخرین نمونه محافظت‌شده)
- `POST /api/guests/{guest_id}/promote` — ارتقای مهمان به کارگر
- لینک «👥 ادمین» در داشبورد

#### 🔧 تغییرات داخلی

- `raw_frame` گلوبال جدید (فریم بدون annotation) در کنار `frame`
- `attendance.get_all_states()` برای snapshot پنل ادمین
- `repository.list_workers_detailed()` و `repository.remove_encoding()`
- fixture `registered_workers` در `tests/test_attendance.py` + تست جدید
  `test_toggle_unregistered_worker_is_ignored`

#### 🧹 پاک‌سازی داده (با تأیید کاربر)

پشتیبان `data/cv_attendance.db.bak` گرفته شد، سپس کارگرهای معیوب `guest_001/002/003`
(به‌همراه ۲۲ رویداد) و سه رکورد مهمان با عکس‌هایشان حذف شدند.

#### 📚 مستندات

- `ARCHITECTURE.md` بازنویسی کامل: ۷ لایه، جریان داده، جدول کامل API، ۸ قانون معماری
- `PROJECT_JOURNAL.md` بازنویسی کامل با بخش جدید «۱۰. شکار باگ» شامل اعداد واقعی اندازه‌گیری‌شده

---

### `2.2.0` — نسخهٔ پیشین

- ماژول‌های CV فاز ۲: quality، liveness، alignment، tracking
- JWT + RBAC، Prometheus، health checks، Docker Compose، Alembic
- مهاجرت از فایل JSON به SQLAlchemy + SQLite
- ثبت‌نام ۶ زاویه با راهنمای تصویری

---

<div align="center">

**پایان ژورنال — نسخه ۳.۲.۰**

این سند زنده است. هر باگ عمیق بعدی باید در قالب بخش ۱۰ به آن اضافه شود:
نشانه → فرضیهٔ اشتباه → اندازه‌گیری → ریشه → اصلاح → تأیید عملی.

</div>

</div>
