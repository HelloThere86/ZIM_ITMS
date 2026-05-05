# TraffiQ / ITMS Authentication + RBAC Integration

Copy these files into your project root, preserving folder paths.

## 1. Install backend dependencies

```bash
pip install "python-jose[cryptography]" "passlib[bcrypt]" python-multipart email-validator
```

Also merge `requirements-auth.txt` into your normal `requirements.txt`.

## 2. Create the users table

From the project root:

```bash
python -m api.migrations.create_users_table
```

Default login:

```text
Email: admin@itms.zrp.gov.zw
Password: Admin@ITMS2024
```

Change this password after testing.

## 3. Register auth router in `api/main.py`

At the top of `api/main.py`, change:

```python
from fastapi import FastAPI, HTTPException, Query
```

to:

```python
from fastapi import FastAPI, HTTPException, Query, Depends
from api.auth import router as auth_router
from api.auth import require_permission, UserOut
```

After this line:

```python
app = FastAPI(title="ITMS Backend API")
```

add:

```python
app.include_router(auth_router)
```

## 4. Protect backend routes

Add FastAPI permission dependencies to important endpoints.

Examples:

```python
@app.get("/api/stats")
def get_stats(user: UserOut = Depends(require_permission("violations:read"))):
    ...
```

```python
@app.get("/api/violations")
def get_violations(user: UserOut = Depends(require_permission("violations:read"))):
    ...
```

```python
@app.get("/api/review-queue")
def get_review_queue(user: UserOut = Depends(require_permission("violations:approve"))):
    ...
```

```python
@app.post("/api/review-queue/{violation_code}/decision")
def decide_review_case(
    violation_code: str,
    payload: ReviewDecisionRequest,
    user: UserOut = Depends(require_permission("violations:approve")),
):
    ...
```

```python
@app.get("/api/evidence-search")
def get_evidence_search(
    plateNumber: Optional[str] = Query(default=None),
    intersection: Optional[str] = Query(default=None),
    dateFrom: Optional[str] = Query(default=None),
    dateTo: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    user: UserOut = Depends(require_permission("evidence:read")),
):
    ...
```

```python
@app.post("/api/evidence-search/{violation_code}/access")
def log_evidence_access(
    violation_code: str,
    payload: EvidenceAccessRequest,
    user: UserOut = Depends(require_permission("evidence:read")),
):
    ...
```

```python
@app.post("/api/violations/{violation_code}/send-sms")
def send_violation_sms(
    violation_code: str,
    payload: SendSmsRequest,
    user: UserOut = Depends(require_permission("sms:send")),
):
    ...
```

```python
@app.get("/api/notifications/sms")
def get_sms_notifications(user: UserOut = Depends(require_permission("sms:send"))):
    ...
```

```python
@app.get("/api/audit-log")
def get_audit_log(user: UserOut = Depends(require_permission("audit:read"))):
    ...
```

```python
@app.get("/api/config")
def get_config(user: UserOut = Depends(require_permission("settings:read"))):
    ...
```

```python
@app.put("/api/config/{config_key}")
def update_config(
    config_key: str,
    payload: ConfigUpdateRequest,
    user: UserOut = Depends(require_permission("settings:write")),
):
    ...
```

```python
@app.get("/api/traffic-results")
def get_traffic_results(user: UserOut = Depends(require_permission("results:read"))):
    ...
```

## 5. Add frontend files

Copy these files into the frontend:

```text
frontend/src/context/AuthContext.tsx
frontend/src/components/ProtectedRoute.tsx
frontend/src/components/AuthUserPanel.tsx
frontend/src/pages/LoginPage.tsx
frontend/src/pages/UsersPage.tsx
frontend/src/services/auth.ts
frontend/src/services/api.ts
frontend/src/services/users.ts
frontend/src/App.tsx
```

`App.tsx` assumes your existing pages are named:

```text
Dashboard
ViolationsPage
TrafficResultsPage
ReviewQueuePage
EvidenceSearchPage
SystemHealthPage
AuditTrailPage
ConfigPage
```

If your page names differ, only adjust imports at the top of `App.tsx`.

## 6. Add logout to Sidebar

Open:

```text
frontend/src/components/Sidebar.tsx
```

Add:

```tsx
import { AuthUserPanel } from "./AuthUserPanel";
```

Then place this near the bottom of the sidebar JSX:

```tsx
<AuthUserPanel />
```

Also add a sidebar link for user management if needed:

```tsx
/users
```

Only admins can open it.

## 7. Optional Vite environment variable

Create:

```text
frontend/.env
```

with:

```env
VITE_API_ORIGIN=http://127.0.0.1:8000
```

## 8. Run

Backend:

```bash
uvicorn api.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## 9. Demo accounts

After logging in as admin, go to `/users` and create:

```text
Supervisor:
  Role: supervisor

Officer:
  Role: officer
```

Test expected RBAC:

```text
Admin:
- Dashboard: allowed
- Review Queue: allowed
- Audit Trail: allowed
- Config: allowed
- Users: allowed

Supervisor:
- Dashboard: allowed
- Review Queue: allowed
- Audit Trail: allowed
- Config: denied
- Users write: denied

Officer:
- Dashboard: allowed
- Violations: allowed
- Evidence Search: allowed
- Review Queue: denied
- Audit Trail: denied
- Config: denied
- Users: denied
```
