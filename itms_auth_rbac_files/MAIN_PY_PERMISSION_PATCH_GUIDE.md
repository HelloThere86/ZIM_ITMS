# `api/main.py` Permission Patch Guide

This file shows the minimum permission checks to add to your existing `api/main.py`.

## Imports

```python
from fastapi import FastAPI, HTTPException, Query, Depends
from api.auth import router as auth_router
from api.auth import require_permission, UserOut
```

## Router registration

Add after `app = FastAPI(...)`:

```python
app.include_router(auth_router)
```

## Permission map for your current endpoints

Use this table:

| Endpoint | Permission |
|---|---|
| `/api/stats` | `violations:read` |
| `/api/violations` | `violations:read` |
| `/api/review-queue` | `violations:approve` |
| `/api/review-queue/{violation_code}/decision` | `violations:approve` |
| `/api/evidence-search` | `evidence:read` |
| `/api/evidence-search/{violation_code}/access` | `evidence:read` |
| `/api/violations/{violation_code}/send-sms` | `sms:send` |
| `/api/notifications/sms` | `sms:send` |
| `/api/audit-log` | `audit:read` |
| `/api/config` GET | `settings:read` |
| `/api/config/{config_key}` PUT | `settings:write` |
| `/api/traffic-results` | `results:read` |

## Pattern

Before:

```python
@app.get("/api/stats")
def get_stats():
    ...
```

After:

```python
@app.get("/api/stats")
def get_stats(user: UserOut = Depends(require_permission("violations:read"))):
    ...
```

You do not need to use `user` inside the function unless you want audit tracking.
