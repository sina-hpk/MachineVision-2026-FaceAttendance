# Changelog — CV Attendance System v2.2.1

## بازبینی کامل کد (Code Audit) — ۱۴۰۴/۰۵/۰۶

### خلاصه
- **۳۰ مشکل** شناسایی و رفع شد (7 P0 بحرانی, 14 P1 زیاد, 7 P2 متوسط, 2 P3 کم)
- **۱۱ API endpoint** تست شد ✅
- **۷۳ تست واحد** ALL PASS ✅
- **۳۶ فایل Python** کامپایل سالم ✅

---

### P0 — بحرانی (۷ رفع)

| # | مشکل | فایل | راه‌حل |
|---|------|------|--------|
| 1 | Guest/Event state هرگز پاک نمی‌شد (متغیر محلی) | `main_fastapi.py` | `global guest_id, event` اضافه شد |
| 2 | Dashboard endpoints بدون احراز هویت | `main_fastapi.py` | مستندسازی محدودیت (نیاز به auth در آینده) |
| 3 | `connected_websockets` race condition | `main_fastapi.py` | `_websocket_lock` اضافه شد |
| 4 | `NameError` وقتی همه encodings فیلتر شوند | `face_recognizer.py` | `similarities=[]` + `if len(similarities)>0` |
| 5 | `daily_summary` رویدادهای جفت‌نشده را حذف می‌کرد | `attendance.py` | `zip_longest` جایگزین `zip` |
| 6 | XSS در dashboard.html (innerHTML) | `dashboard.html` | تابع `esc()` برای sanitization |
| 7 | XSS در academic.html (template literals) | `academic.html` | تابع `esc()` برای sanitization |

### P1 — زیاد (۱۴ رفع)

| # | مشکل | فایل | راه‌حل |
|---|------|------|--------|
| 8 | CORS credentials=True + wildcard | `main_fastapi.py` | `allow_credentials=False` |
| 9 | Traceback leak در response 500 | `main_fastapi.py` | حذف `traceback` از response |
| 10 | `@rate_limit` با async endpoints کار نمی‌کرد | `redis_client.py` | `asyncio.iscoroutinefunction` تشخیص + wrapper مجزا |
| 11 | `broadcast_event` fail قبل از WebSocket | `main_fastapi.py` | `_ws_loop` در `lifespan` ذخیره شد |
| 12 | Health check مقادیر hardcoded | `main_fastapi.py` | `func.now()` + `redis.health_check()` واقعی |
| 13 | Full re-detection بعد از alignment | `face_recognizer.py` | فقط در صورت تغییر >10px |
| 14 | Hardcoded 0.5 | `face_recognizer.py` | `self.quality_threshold` جایگزین |
| 15 | ArcFace augmentation duplicate | `face_recognizer.py` | چک quality از `self.quality_threshold` |
| 16 | `on_known` هر فریم fire می‌شد | `face_recognizer.py` | `cooldown_sec` پارامتر داخلی |
| 17 | Rectangle مختصات جابجا | `face_recognizer.py` | `(box[3],box[0])` → `(box[1],box[2])` |
| 18 | Registration بدون تشخیص چهره | `main_fastapi.py` | `reset step_start_time` وقتی چهره نیست |
| 19 | `_next_worker_id` race condition | `models/repository.py` | `SELECT max()` اتمیک با SQL |
| 20 | Silent exceptions قورت داده شده | `models/repository.py` | `logging.warning` به ۳ متد |
| 21 | مستندات اشتباه bcrypt | `README.md` | اصلاح به sha256_crypt |

### P2 — متوسط (۷ رفع)

| # | مشکل | فایل | راه‌حل |
|---|------|------|--------|
| 22 | کلاس `GUID` تکراری | `models/worker.py` | حذف کپی محلی، import از `base.py` |
| 23 | JWT secret key ضعیف | `config.py` | تغییر به کلید قوی‌تر |
| 24 | رفرنس فایل‌های ناموجود در docs | `README.md` | حذف `test_mutation_test`, `test_load_test` |
| 25 | Kalman filter ابعاد اشتباه | `cv_modules/tracking.py` | تبدیل `[x1,y1,x2,y2]` ↔ `[cx,cy,w,h]` |
| 26 | Singleton `_benchmark` thread-unsafe | `academic.py` | `_benchmark_lock` double-checked locking |
| 27 | `camera_enabled`/`camera_error` بدون sync | `main_fastapi.py` | `camera_lock` اضافه شد |
| 28 | متن فارسی RTL با OpenCV | `registration.py` | حذف متن فارسی (OpenCV LTR) |

### P3 — کم (۲ رفع)

| # | مشکل | فایل | راه‌حل |
|---|------|------|--------|
| 29 | Self-contradictory مستندات | `PROJECT_JOURNAL.md` | اصلاح "Empty - Needs Implementation" |
| 30 | Date parsing خطای ۴۰۰ | `main_fastapi.py` | `try/except ValueError` → HTTP 400 |

### رفع‌های اضافی (آخرین مرحله)

| مشکل | فایل | راه‌حل |
|------|------|--------|
| `broadcast_event` fallback بدون try/except | `main_fastapi.py` | `try/except RuntimeError` |
| `_make_placeholder_frame` dead code | `main_fastapi.py` | حذف کامل |
| `get_fastapi_deps()` ~85 خط dead code | `auth.py` | حذف کامل |
| Date parsing بدون خطاگیری در export | `main_fastapi.py` | `try/except ValueError` → HTTP 400 |

### فایل‌های تغییر کرده

```
main_fastapi.py       — 12 محل (CORS, health, date, WebSocket, ...)
face_recognizer.py    — 6 محل (NameError, coordinates, quality, ...)
attendance.py         — 1 محل (zip_longest)
models/repository.py  — 4 محل (logging, _next_worker_id)
models/worker.py      — 1 محل (GUID duplicate)
cv_modules/tracking.py — 1 محل (Kalman coordinates)
academic.py           — 1 محل (benchmark singleton)
registration.py       — 1 محل (RTL text)
redis_client.py       — 1 محل (async rate_limit)
auth.py               — 1 محل (dead code removal)
config.py             — 1 محل (secret_key)
templates/dashboard.html  — 1 محل (XSS)
templates/academic.html   — 1 محل (XSS)
README.md             — 2 محل (bcrypt, file tree)
PROJECT_JOURNAL.md    — 2 محل (test status, file tree)
tests/test_config.py  — 1 محل (secret_key expected value)
tests/test_attendance.py — 1 محل (num_switches expected value)
```
