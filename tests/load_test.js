// k6 Load Test for CV Attendance System
// Run: k6 run tests/load_test.js
//
// Options:
//   k6 run --vus 10 --duration 30s tests/load_test.js
//   k6 run --vus 50 --duration 60s tests/load_test.js

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const failureRate = new Rate('failed_requests');
const healthLatency = new Trend('healthz_latency');
const dashboardLatency = new Trend('dashboard_latency');

export const options = {
  stages: [
    { duration: '10s', target: 5 },   // Ramp-up to 5 users
    { duration: '20s', target: 20 },  // Ramp-up to 20 users
    { duration: '10s', target: 20 },  // Stay at 20 users
    { duration: '10s', target: 0 },   // Ramp-down
  ],
  thresholds: {
    failed_requests: ['rate<0.05'],        // < 5% failure rate
    http_req_duration: ['p(95)<500'],      // 95% under 500ms
    healthz_latency: ['p(95)<200'],        // Health check under 200ms
    dashboard_latency: ['p(95)<300'],      // Dashboard under 300ms
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  // ── Health Check ──
  group('Health Check', function () {
    const r = http.get(`${BASE_URL}/healthz`);
    const ok = check(r, {
      'status is 200': (res) => res.status === 200,
    });
    failureRate.add(!ok);
    healthLatency.add(r.timings.duration);
  });

  // ── Ready Check ──
  group('Ready Check', function () {
    const r = http.get(`${BASE_URL}/readyz`);
    check(r, {
      'readiness status is 200': (res) => res.status === 200,
    });
  });

  // ── Dashboard API ──
  group('Dashboard API', function () {
    const r = http.get(`${BASE_URL}/api/dashboard`);
    const ok = check(r, {
      'dashboard status is 200': (res) => res.status === 200,
      'dashboard has workers': (res) => res.json().hasOwnProperty('workers'),
      'dashboard has events': (res) => res.json().hasOwnProperty('events_today'),
    });
    failureRate.add(!ok);
    dashboardLatency.add(r.timings.duration);
  });

  // ── Metrics ──
  group('Metrics', function () {
    const r = http.get(`${BASE_URL}/metrics`);
    check(r, {
      'metrics status is 200': (res) => res.status === 200,
    });
  });

  // ── Attendance Report ──
  group('Attendance Report', function () {
    const r = http.get(`${BASE_URL}/api/attendance/report`);
    check(r, {
      'report status is 200': (res) => res.status === 200,
    });
  });

  // ── Camera Status ──
  group('Camera Status', function () {
    const r = http.get(`${BASE_URL}/camera/status`);
    check(r, {
      'camera status is 200': (res) => res.status === 200,
      'camera has enabled': (res) => res.json().hasOwnProperty('enabled'),
    });
  });

  // ── Auth Endpoints ──
  group('Auth', function () {
    // Unauthorized access should return 401
    const r1 = http.get(`${BASE_URL}/auth/me`);
    check(r1, {
      'auth/me without token returns 401': (res) => res.status === 401,
    });

    const r2 = http.get(`${BASE_URL}/workers`);
    check(r2, {
      'workers without token returns 401': (res) => res.status === 401,
    });

    // Login with bad credentials
    const r3 = http.post(`${BASE_URL}/auth/login`, JSON.stringify({
      username: 'loadtest',
      password: 'wrong',
    }), { headers: { 'Content-Type': 'application/json' } });
    check(r3, {
      'login with bad creds returns 401': (res) => res.status === 401,
    });
  });

  // ── Static Files ──
  group('Static Files', function () {
    const r = http.get(`${BASE_URL}/docs`);
    check(r, {
      'swagger docs is 200': (res) => res.status === 200,
    });
  });

  sleep(1);
}
