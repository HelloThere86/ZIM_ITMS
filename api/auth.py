"""
Authentication and RBAC for TraffiQ / ITMS.

Roles:
  admin       - full system access, including user management and settings
  supervisor  - review queue, audit trail, fines, system health, SMS actions
  officer     - dashboard, violations, evidence search, traffic results
"""

import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = os.environ.get(
    "DB_PATH",
    str(PROJECT_ROOT / "database" / "itms_production.db"),
)

SECRET_KEY = os.environ.get("JWT_SECRET", "change-this-before-final-demo")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.environ.get("TOKEN_EXPIRE_MINUTES", str(60 * 8)))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "violations:read",
        "violations:approve",
        "evidence:read",
        "evidence:export",
        "results:read",
        "sms:send",
        "audit:read",
        "fines:read",
        "settings:read",
        "settings:write",
        "users:read",
        "users:write",
    },
    "supervisor": {
        "violations:read",
        "violations:approve",
        "evidence:read",
        "evidence:export",
        "results:read",
        "sms:send",
        "audit:read",
        "fines:read",
    },
    "officer": {
        "violations:read",
        "evidence:read",
        "results:read",
    },
}

ROLE_LABELS = {
    "admin": "System Administrator",
    "supervisor": "Supervisor",
    "officer": "Traffic Officer",
}

LEGACY_ROLE_MAP = {
    "admin": "Admin",
    "supervisor": "Operator",
    "officer": "Officer",
}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    permissions: list[str]


class UserOut(BaseModel):
    user_id: int
    full_name: str
    badge_number: Optional[str]
    email: str
    role: str
    role_label: str
    is_active: bool
    created_at: str
    last_login: Optional[str]
    permissions: list[str]


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    badge_number: Optional[str] = None
    role: str
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    badge_number: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM users
            WHERE LOWER(email) = LOWER(?) AND is_active = 1
            """,
            (email,),
        ).fetchone()


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()


def update_last_login(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET last_login = datetime('now') WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()


def row_to_user_out(row: sqlite3.Row) -> UserOut:
    role = row["role"]
    return UserOut(
        user_id=row["user_id"],
        full_name=row["full_name"],
        badge_number=row["badge_number"],
        email=row["email"],
        role=role,
        role_label=ROLE_LABELS.get(role, role),
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
        last_login=row["last_login"],
        permissions=sorted(PERMISSIONS.get(role, set())),
    )


def ensure_valid_role(role: str) -> None:
    if role not in PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {role}. Allowed roles: {', '.join(PERMISSIONS.keys())}",
        )


def sync_user_to_legacy(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    full_name: str,
    email: str,
    password_hash: str,
    role: str,
    is_active: bool,
) -> None:
    legacy_role = LEGACY_ROLE_MAP[role]
    conn.execute(
        """
        INSERT INTO system_user (
            user_id,
            full_name,
            role,
            username,
            password_hash,
            is_active
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name = excluded.full_name,
            role = excluded.role,
            username = excluded.username,
            password_hash = excluded.password_hash,
            is_active = excluded.is_active
        """,
        (
            user_id,
            full_name,
            legacy_role,
            email,
            password_hash,
            int(is_active),
        ),
    )


def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2)) -> UserOut:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise credentials_exc
        user_id = int(user_id_raw)
    except (JWTError, TypeError, ValueError):
        raise credentials_exc

    row = get_user_by_id(user_id)
    if not row or not row["is_active"]:
        raise credentials_exc

    return row_to_user_out(row)


def require_permission(permission: str):
    async def checker(user: UserOut = Depends(get_current_user)) -> UserOut:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Your role ({user.role_label}) does not have "
                    f"'{permission}' access."
                ),
            )
        return user

    return checker


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    row = get_user_by_email(form.username)

    if not row or not pwd_ctx.verify(form.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    update_last_login(row["user_id"])

    token = create_token(row["user_id"], row["role"])

    return TokenResponse(
        access_token=token,
        role=row["role"],
        full_name=row["full_name"],
        permissions=sorted(PERMISSIONS.get(row["role"], set())),
    )


@router.get("/me", response_model=UserOut)
async def me(user: UserOut = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
async def list_users(_: UserOut = Depends(require_permission("users:read"))):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM users
            ORDER BY created_at DESC
            """
        ).fetchall()

    return [row_to_user_out(row) for row in rows]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    _: UserOut = Depends(require_permission("users:write")),
):
    ensure_valid_role(body.role)

    password_hash = pwd_ctx.hash(body.password)

    try:
        with get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    password_hash,
                    role,
                    badge_number
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    body.full_name.strip(),
                    body.email.lower().strip(),
                    password_hash,
                    body.role,
                    body.badge_number.strip() if body.badge_number else None,
                ),
            )
            user_id = cursor.lastrowid

            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            sync_user_to_legacy(
                conn,
                user_id=row["user_id"],
                full_name=row["full_name"],
                email=row["email"],
                password_hash=row["password_hash"],
                role=row["role"],
                is_active=bool(row["is_active"]),
            )
            conn.commit()

        return row_to_user_out(row)

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or badge number already exists.",
        )


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    current: UserOut = Depends(require_permission("users:write")),
):
    existing = get_user_by_id(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if body.role is not None:
        ensure_valid_role(body.role)

    if current.user_id == user_id and body.role and body.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own admin role.",
        )

    if current.user_id == user_id and body.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    fields: list[str] = []
    values: list[object] = []

    if body.full_name is not None:
        fields.append("full_name = ?")
        values.append(body.full_name.strip())

    if body.badge_number is not None:
        fields.append("badge_number = ?")
        values.append(body.badge_number.strip() or None)

    if body.role is not None:
        fields.append("role = ?")
        values.append(body.role)

    if body.is_active is not None:
        fields.append("is_active = ?")
        values.append(int(body.is_active))

    if body.password is not None:
        fields.append("password_hash = ?")
        values.append(pwd_ctx.hash(body.password))

    if not fields:
        return row_to_user_out(existing)

    values.append(user_id)

    try:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?",
                values,
            )
            updated = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            sync_user_to_legacy(
                conn,
                user_id=updated["user_id"],
                full_name=updated["full_name"],
                email=updated["email"],
                password_hash=updated["password_hash"],
                role=updated["role"],
                is_active=bool(updated["is_active"]),
            )
            conn.commit()

        return row_to_user_out(updated)

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or badge number already exists.",
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    current: UserOut = Depends(require_permission("users:write")),
):
    if current.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        conn.execute(
            "UPDATE users SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        conn.execute(
            "UPDATE system_user SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()

    return None
