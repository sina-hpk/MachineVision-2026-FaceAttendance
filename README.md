<div align="center">
  <h1> 🎥 CV Attendance System </h1>
  <h3> Face-Recognition Attendance System </h3>
  <h4> K. N. Toosi University of Technology (KNTU) </h4>
  <p>
    <strong>Course:</strong> Machine Vision — <strong>Year:</strong> 2026
  </p>
</div>

---

## 📝 Project Title

> **CV Attendance System — Smart Face-Recognition Attendance**

A real-time attendance system that replaces ID cards and fingerprints with **facial recognition**. A camera captures frames, the system detects faces (SCRFD), converts each face into a **512-dimensional embedding vector** (ArcFace), and compares it against the stored vectors of registered workers. If the similarity passes a threshold, check-in/check-out is logged automatically; unknown faces are stored as **guests** — never falsely checked in.

Key design principles:

- **Privacy-first:** all processing runs locally — no face image ever leaves the machine, and embeddings are **not reversible** to the original photo.
- **Conservative by design:** unknown person ⇒ guest, never a false attendance record.
- **Debuggable:** an admin panel shows the exact crop each vector was built from, plus a documented journal of 19 root-caused bugs.

---

## 🎥 Product Pitch & Demos

Watch the full presentation and demonstration of the project here:

- [**YouTube Video**](Link-Here)
- [**Aparat Video**](Link-Here)

📄 **[Project Report & Documentation (Google Drive)](Link-Here)**

---

## 👥 Team Members

| Name | Student ID | GitHub Profile | Role / Contribution |
| :--- | :--- | :--- | :--- |
| [Hamed Nabipour](حامد نبی‌پور) | `40222153` | [@username](https://github.com/username) | Machine Vision Pipeline (Detection, Quality, Liveness, Tracking) |
| [Sina Hasanpour](سینا حسن‌پور) | `40216723` | [@username](https://github.com/username) | Data Layer & Business Logic (DB Schema, Guest Logic, Cooldown) |
| [AmirMohammad Ahmadi](امیرمحمد احمدی) | `40214403` | [@username](https://github.com/username) | Web, API & Security (FastAPI, Real-time Stream, JWT/RBAC) |

---

## 📂 Repository Structure

```text
MachineVision-2026-FaceAttendance/
├── main_fastapi.py           # FastAPI app — unified entry point (API, MJPEG, WebSocket)
├── main.py                   # CLI entry point (run, list, remove, export)
├── face_recognizer.py        # CV layer: detect → quality → encode → match
├── attendance.py             # Business logic (toggle, cooldown, reports)
├── auth.py / auth_fastapi.py # JWT + RBAC auth and FastAPI dependencies
├── config.py                 # Pydantic settings (from .env)
├── redis_client.py           # Redis client (rate limiting, sessions)
├── academic.py               # Recognition-engine benchmark (accuracy, charts)
├── models/                   # SQLAlchemy models + repository.py (CRUD)
├── cv_modules/               # quality.py, liveness.py, alignment.py, tracking.py
├── templates/                # dashboard.html, admin.html, academic.html
├── static/                   # style.css
├── docs/                     # Reports, architecture, bug journal, proposal
├── assets/                   # Images, diagrams, media for this README
├── data/                     # Runtime data (faces, attendance) — git-ignored
├── tests/                    # 125 unit & integration tests
├── alembic/                  # Database migrations
├── nginx/                    # Nginx config (reverse proxy)
├── requirements.txt          # Python dependencies
├── requirements-test.txt     # Test-only dependencies
├── Dockerfile                # Container image
├── docker-compose.yml        # Multi-service orchestration
├── .env.example              # Environment template (copy to .env)
├── .gitignore
└── README.md                 # This file
```

---

## ⚙️ Installation & Requirements

### Prerequisites

- **Python 3.11+**
- **Webcam**
- **Redis** (optional — only for rate limiting/sessions)
- Windows / Linux / macOS

### Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/YourUsername/MachineVision-2026-FaceAttendance.git
   ```

2. Navigate to the directory:

   ```bash
   cd MachineVision-2026-FaceAttendance
   ```

3. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Linux/macOS
   # .venv\Scripts\activate       # Windows
   ```

4. Install the dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   > **Windows users:** install the prebuilt `dlib` wheel (fallback engine):
   >
   > ```bash
   > pip install https://github.com/z-mahmud22/Dlib_Windows_Python3.x/raw/main/dlib-19.24.1-cp311-cp311-win_amd64.whl
   > ```

5. Configure environment:

   ```bash
   cp .env.example .env
   # edit .env — at minimum change ADMIN_USERNAME / ADMIN_PASSWORD and SECRET_KEY
   ```

---

## 🚀 Usage & Execution

### Run the server (recommended — production-ready FastAPI)

```bash
python -m uvicorn main_fastapi:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser: **http://localhost:8000**

- Dashboard & live camera stream: `http://localhost:8000/`
- Admin panel (HTTP Basic): `http://localhost:8000/admin`
- Swagger UI (auto docs): `http://localhost:8000/docs`

### Register workers

1. Open the admin panel and register each worker with **6 pose variations** (front, left, right, up, down, smile) — this variety is what makes recognition robust.
2. Verify the sample count and thumbnail crops in the admin panel.
3. Test separation: each person walks in front of the camera and their correct name must appear.

### CLI mode

```bash
python main.py run          # direct camera loop
python main.py list         # list workers
python main.py remove W001  # remove a worker
python main.py export       # export attendance CSV
```

*(Add screenshots or GIFs of your project running here to make it visually appealing!)*

---

## 📊 Results & Achievements

- **125 automated tests** (unit + integration) — all passing
- **19 documented bugs** with root-cause analysis (see [docs/PROJECT_JOURNAL.md](docs/PROJECT_JOURNAL.md))
- **Dual recognition engines**: InsightFace SCRFD + ArcFace (512-d) as primary, dlib (128-d) as automatic fallback
- **Face quality gate**: blur (Laplacian variance), brightness, pose, and occlusion checks before encoding — low-quality crops are deliberately rejected
- **Anti-spoofing (liveness)**: blink detection (EAR), texture analysis (FFT/LBP), and natural motion tracking
- **Multi-face tracking** with identity smoothing via voting consensus over the last N frames
- **Real-time dashboard**: MJPEG stream, WebSocket events, daily reports
- **Security**: JWT + RBAC, HTTP Basic with constant-time comparison on the admin panel, Redis sliding-window rate limiting, path-traversal validation

### Known limitations (honestly stated)

| Limitation | Mitigation |
| :--- | :--- |
| Liveness vs. advanced 3D-mask attacks | Simple photo attacks are blocked; depth/IR sensors would be required for stronger attacks |
| No automated end-to-end CV tests | Unit tests cover logic with synthetic vectors; real-photo validation was manual |
| Default admin credentials | `admin` / `admin` — must be changed in `.env` before production use |
| SQLite database | Sufficient for single-device use; SQLAlchemy allows switching to PostgreSQL via one connection string |
| ~400ms/frame on CPU | Reduce with GPU + `onnxruntime-gpu` |

---

## 📜 License

This project is licensed under the [MIT License](LICENSE).
