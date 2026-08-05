# CV Attendance System - معماری پروژه

## 1. تعریف پروژه

یک سیستم حضور و غیاب هوشمند مبتنی بر تشخیص چهره که:
- کارمندان با نمایش چهره به دوربین به صورت خودکار ورود/خروج ثبت می‌کنند
- تمام اطلاعات به صورت محلی ذخیره می‌شود (حریم خصوصی کامل)
- داشبورد تحت وب با استریم زنده دوربین
- پنل ادمین برای مدیریت کارگرها و نمونه‌های چهره

## 2. اجزای سیستم (معماری یکپارچه)

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│   نقطه ورود CLI: run, list, remove, web, export, guests     │
└─────────────────────┬───────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌──────────────────┐    ┌──────────────────────┐
│  face_recognizer │    │   main_fastapi.py    │
│  │               │    │   │ سرور FastAPI      │
│  تشخیص چهره +    │    │   │ استریم ویدئو      │
│  تطبیق با        │    │   │ API REST + JWT    │
│  دیتابیس         │    │   │ پنل ادمین         │
└────────┬─────────┘    └──────────┬───────────┘
         │                         │
         └──────────┬──────────────┘
                    ▼
         ┌────────────────────┐
         │    models/         │
         │   SQLAlchemy       │
         │   - Worker         │
         │   - FaceEncoding   │
         │   - Guest          │
         │   - Attendance     │
         │   - User (RBAC)    │
         └────────┬───────────┘
                  │
         ┌────────┴───────────┐
         │   attendance.py    │
         │   رویدادهای روزانه │
         │   ورود/خروج/hour   │
         └────────────────────┘
```

## 3. لایه‌ها (Layers)

### لایه 1: سخت‌افزار
- وب‌کم (منبع تصویر)
- سیستم فایل (data/faces/, data/attendance/, SQLite)

### لایه 2: تشخیص چهره (face_recognizer.py)
**مسئولیت:** تعامل با دوربین، تشخیص چهره، تطبیق با دیتابیس

**دو موتور، با انتخاب در زمان اجرا:**

| موتور | Detector | Embedding | بُعد | معیار تطبیق | تأخیر (CPU ۴ هسته) |
|-------|----------|-----------|------|-------------|---------------------|
| اصلی — InsightFace `buffalo_l` | SCRFD (`det_10g.onnx`) | ArcFace (`w600k_r50.onnx`) | ۵۱۲ | شباهت کسینوسی > `1 - tolerance` | ~۳۸۰ms |
| پشتیبان — dlib | HOG + SVM | ResNet-29 | ۱۲۸ | فاصلهٔ اقلیدسی < `tolerance` | ~۲۴ms |

انتخاب با `settings.prefer_insightface` انجام می‌شود و در صورت خطای بارگذاری، به‌صورت خودکار به dlib برمی‌گردد. `recognizer.engine_name` موتور فعال را برمی‌گرداند.

⚠️ **دو نکتهٔ عملیاتی:**
1. `insightface_det_size` باید **مربع** باشد. SCRFD شبکهٔ anchor را از ارتفاع ورودی برای هر دو محور می‌سازد، پس مقدار غیرمربع مثل `(320, 240)` باعث خطای broadcast در `distance2bbox()` می‌شود.
2. انکودینگ‌های دو موتور **قابل مقایسه نیستند**. هر دو تابع تطبیق، بردارهای با بُعد ناهمخوان را فیلتر می‌کنند؛ تغییر موتور نیازمند بازسازی نمونه‌های ذخیره‌شده است.

**متدها:**
- `open_camera()` / `release_camera()` / `read_frame()` - مدیریت دوربین
- `recognize(frame)` - تشخیص چهره در فریم → لیست نتایج
- `capture_encodings(name, num_samples)` - ثبت‌نام چهره جدید
- `invalidate_cache()` - باطل کردن کش known faces

### لایه 3: دیتابیس (models/ + SQLAlchemy)
**مسئولیت:** ذخیره و بازیابی اطلاعات کارگران، مهمان‌ها، رویدادها
- `FaceRepository` - کلاس اصلی با Session SQLAlchemy
- `get_all_known()` - تمام چهره‌های ثبت‌شده (با کش TTL ۵ ثانیه)
- `add_worker()` / `remove_worker()` / `add_encoding_to_worker()` / `remove_encoding()`
- `promote_guest_to_worker()`
- `list_workers_detailed()` - برای پنل ادمین

### لایه 4: حضور و غیاب (attendance.py)
**مسئولیت:** ثبت رویدادها، گزارش‌گیری
- `AttendanceTracker` - کلاس اصلی
- `toggle(worker_id)` - تغییر وضعیت ورود/خروج (فقط کارگرهای ثبت‌شده)
- `export_csv()` - خروجی CSV
- `get_all_states()` - وضعیت همه کارگرها برای ادمین

### لایه 5: وب (main_fastapi.py - FastAPI)
**مسئولیت:** رابط کاربری وب، API، احراز هویت
- `camera_loop()` - ترد پس‌زمینه دوربین + تشخیص + الحضور
- MJPEG stream در `/video_feed`
- REST API با JWT + RBAC
- پنل ادمین در `/admin` (پشت HTTP Basic)
- Health checks: `/healthz`, `/readyz`
- Prometheus metrics در `/metrics`

### لایه 6: CLI (main.py)
**مسئولیت:** رابط خط فرمان
- `cmd_run()` - دوربین مستقیم
- `cmd_list()` - لیست کارگران
- `cmd_web()` - اجرای وب سرور
- `cmd_export()` - خروجی گزارش
- `cmd_guests()` - مدیریت مهمان‌ها

### لایه 7: ماژول‌های CV Phase 2 (cv_modules/)
- `quality.py` - Face Quality Assessment (Blur, Pose, Brightness, Contrast)
- `liveness.py` - Liveness Detection (Blink, Texture, Motion)
- `alignment.py` - Face Alignment (Eye-based affine transform)
- `tracking.py` - Multi-face Tracking + Temporal Identity Smoothing

## 4. جریان داده (Data Flow)

```
وب‌کم → فریم → face_recognizer.recognize()
                       ↓
              [{box, person_id, name, confidence, encoding}]
                       ↓
               camera_loop()  (هر فریم)
                       ↓
            ┌──────────┴──────────┐
            ▼                      ▼
      person_id موجود          person_id == None
      attendance.toggle()      db.add_guest([enc])
      رویداد in/out ثبت        مهمان ساخته می‌شود
```

**ثبت کارگر جدید (از پنل ادمین یا داشبورد):**
```
POST /registration/start {name}
    ↓
چهارچوب گرفتن ۵ زاویه (جلو، چپ، راست، بالا، پایین)
    ↓
encodings + face_crop جمع‌آوری می‌شود
    ↓
POST /api/workers/capture → db.add_worker()
    ↓
recognizer.invalidate_cache()
```

**ارتقای مهمان به کارگر (از پنل ادمین):**
```
مهمان در guest_XXX شناسایی می‌شود
    ↓
پنل ادمین: دکمهٔ «ارتقا به کارگر» + نام
    ↓
POST /api/guests/{guest_id}/promote
    ↓
db.promote_guest_to_worker() → worker جدید + encodings کپی
    ↓
recognizer.invalidate_cache()
```

## 5. API Routes

### عمومی (بدون احراز هویت)
| مسیر | متد | خروجی |
|------|------|-------|
| `/` | GET | HTML dashboard |
| `/video_feed` | GET | MJPEG stream |
| `/camera/status` | GET | JSON (وضعیت دوربین) |
| `/api/dashboard` | GET | JSON (کارگران، رویدادها، آمار) |
| `/api/attendance/report` | GET | JSON (گزارش امروز با ساعات) |
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |
| `/metrics` | GET | Prometheus metrics |

### ادمین (HTTP Basic — `ADMIN_USERNAME` / `ADMIN_PASSWORD`)
این مسیرها داده حذف و تغییر می‌دهند، پس همه پشت `require_admin` هستند.

| مسیر | متد | ورودی | خروجی |
|------|------|-------|-------|
| `/admin` | GET | — | HTML admin panel |
| `/api/admin/workers` | GET | — | JSON (کارگرها + نمونه‌ها + مهمان‌ها) |
| `/api/admin/face/{id}` | GET | — | JPEG (عکس چهره) |
| `/api/admin/workers/{wid}/samples` | POST | - | نمونه جدید از دوربین |
| `/api/admin/workers/{wid}/samples/upload` | POST | `multipart` (`file`) | نمونه جدید از فایل |
| `/api/admin/workers/{wid}/samples/{sid}` | DELETE | - | حذف نمونهٔ خاص |
| `/api/admin/samples/{wid}/{sid}` | GET | — | JPEG (عکس همان نمونه) |
| `/api/admin/workers/{wid}` | DELETE | — | حذف کارگر + همهٔ نمونه‌هایش |
| `/api/guests/{guest_id}/promote` | POST | `{name}` | ارتقای مهمان به کارگر |

### احراز هویت (JWT + RBAC)
| مسیر | متد | Permission | توضیح |
|------|------|------------|-------|
| `/auth/login` | POST | — | Login → tokens |
| `/auth/refresh` | POST | — | Refresh access token |
| `/workers` | GET | worker:read | List workers (paginated) |
| `/workers` | POST | worker:create | Create worker |
| `/workers/{id}/capture` | POST | worker:create | Capture face samples |
| `/workers/{id}` | DELETE | worker:delete | Delete worker |
| `/guests` | GET | worker:read | List unknown faces |
| `/guests/{id}/promote` | POST | worker:create | Promote guest → worker |
| `/attendance` | GET | attendance:read | List events |
| `/attendance/report` | GET | attendance:read | Daily report with hours |

## 6. ساختار فایل‌ها

```
CV_Attendance/
├── main.py                      # CLI entry
├── main_fastapi.py              # FastAPI app (Modern Stack)
├── face_recognizer.py           # CV Pipeline Orchestrator
├── attendance.py                # Business Logic (Attendance)
├── auth.py                      # JWT + RBAC
├── auth_fastapi.py              # FastAPI Auth Dependencies
├── config.py                    # Pydantic Settings
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── run_attendance.bat           # Windows Launcher
├── .env                         # Local Config (gitignored)
├── .gitignore
├── ARCHITECTURE.md              # این فایل
├── PROJECT_JOURNAL.md           # ژورنال توسعه
├── README.md
├── 📁 models/                   # SQLAlchemy Models
│   ├── __init__.py
│   ├── base.py
│   ├── worker.py
│   ├── face_encoding.py
│   ├── guest.py
│   ├── attendance.py
│   └── user.py
├── 📁 cv_modules/               # Phase 2 CV Modules
│   ├── quality.py
│   ├── liveness.py
│   ├── alignment.py
│   └── tracking.py
├── 📁 alembic/                  # DB Migrations
├── 📁 templates/
│   ├── dashboard.html
│   └── admin.html
├── 📁 static/
├── 📁 data/
│   ├── cv_attendance.db         # SQLite
│   ├── faces/                   # تصاویر چهره (W001.jpg, guest_001.jpg)
│   └── attendance/              # گزارش‌های روزانه JSON
└── 📁 tests/                    # ۱۰۰ تست (Unit + Integration)
```

## 7. تنظیمات و Configuration (config.py)

```python
# Camera
camera_enabled: bool = True
camera_index: int = 0
process_scale: float = 0.25

# Recognition
tolerance: float = 0.55
quality_threshold: float = 0.5
enable_alignment: bool = True
enable_liveness: bool = True
enable_quality_gate: bool = True
max_encodings_per_person: int = 10
augment_cooldown_minutes: int = 5

# Attendance
cooldown_seconds: int = 8
guest_capture_interval: int = 5

# Paths
data_dir: str = "data"
faces_dir: str = "data/faces"
attendance_dir: str = "data/attendance"

# Server
host: str = "0.0.0.0"
port: int = 5000
log_level: str = "INFO"
metrics_enabled: bool = True
```

## 8. قوانین معماری

1. **Single Responsibility**: هر کلاس/تابع فقط یک کار انجام بده
2. **Separation of Concerns**: لایه‌ها از هم مستقل باشند
3. **Single Source of Truth**: یک دیتابیس (SQLAlchemy)، یک کانفیگ، یک وب‌فریم‌ورک (FastAPI)
4. **Thread Safety**: دسترسی‌های دیتابیس با Session SQLAlchemy مدیریت می‌شود
5. **Clear Data Flow**: جریان داده مشخص و قابل ردیابی
6. **Fail Fast**: خطاها زود تشخیص داده بشن
7. **No Dead Code**: کدی وجود نداشته باشه که استفاده نشه
8. **Production Ready**: Health checks، Metrics، Structured Logging، Graceful Shutdown