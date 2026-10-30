import hashlib
import os
import re
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.discovery import Resume
from app.models.profile import LOCAL_USER_ID
from app.repositories.profile import lock_local_user

MAX_RESUME_BYTES = 5 * 1024 * 1024


def upload(session: Session, data: bytes, filename: str) -> Resume:
    if not 0 < len(data) <= MAX_RESUME_BYTES:
        raise HTTPException(413, "PDF must be between 1 byte and 5 MiB")
    if not re.match(rb"%PDF-(?:1\.[0-7]|2\.0)", data[:12]) or b"%%EOF" not in data[-2048:]:
        raise HTTPException(422, "Upload a PDF document with a valid header and end marker")
    if not filename.lower().endswith(".pdf") or "/" in filename or "\\" in filename:
        raise HTTPException(422, "Use a PDF filename without path separators")
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename).strip()[:200]
    digest = hashlib.sha256(data).hexdigest()
    lock_local_user(session)
    existing = session.scalar(
        select(Resume).where(
            Resume.user_id == LOCAL_USER_ID,
            Resume.sha256 == digest,
        )
    )
    if existing:
        return existing
    version = (
        session.scalar(
            select(func.max(Resume.version)).where(
                Resume.user_id == LOCAL_USER_ID,
            )
        )
        or 0
    ) + 1
    root = get_settings().storage_dir / "resumes"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    resume_id = uuid4()
    path = root / f"{resume_id}.pdf"
    temp = root / f"{resume_id}.tmp"
    try:
        with temp.open("xb") as handle:
            os.chmod(temp, 0o600)
            handle.write(data)
        temp.replace(path)
        row = Resume(
            id=resume_id,
            user_id=LOCAL_USER_ID,
            original_filename=filename,
            file_key=path.name,
            sha256=digest,
            size_bytes=len(data),
            version=version,
            is_default=version == 1,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
    except Exception:
        session.rollback()
        temp.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise


def set_default(session: Session, row: Resume) -> Resume:
    lock_local_user(session)
    session.execute(update(Resume).where(Resume.user_id == LOCAL_USER_ID).values(is_default=False))
    session.flush()
    row.is_default = True
    session.commit()
    session.refresh(row)
    return row
