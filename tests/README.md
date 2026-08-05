# 🧪 Tests

125 automated unit & integration tests covering the core logic of the system.

| File | Covers |
| :--- | :--- |
| `test_repository.py` | CRUD for workers & guests, face-sample storage |
| `test_attendance.py` | Attendance logic — toggle, cooldown, pairing |
| `test_auth.py` | JWT and RBAC permissions |
| `test_models.py` | SQLAlchemy models |
| `test_config.py` | Settings and environment variables |
| `test_recognizer.py` | Augmentation band and vector-dimension filtering (synthetic vectors) |
| `test_api_integration.py` | API integration & admin authentication |
| `test_server_live.py` | Live-server smoke test (needs Redis running) |
| `load_test.py` / `load_test.js` | Load / stress tests (Python + k6) |
| `mutation_test.py` | Mutation testing helper |

## Run

```bash
# All tests
python -m pytest tests -q

# With coverage
python -m pytest tests -v --cov=.
```

> Integration tests need a running Redis server.
