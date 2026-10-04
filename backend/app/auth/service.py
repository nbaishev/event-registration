from uuid import uuid4

from sqlalchemy.orm import Session

from app.auth import repository
from app.auth.models import User
from app.auth.passwords import hash_password
from app.auth.schemas import RegisterRequest
from app.common.clock import Clock


def register_user(session: Session, clock: Clock, email: str, password: str) -> User:
    request = RegisterRequest(email=email, password=password)
    now = clock.now()
    user = User(
        id=uuid4(),
        email=str(request.email),
        password_hash=hash_password(request.password),
        created_at=now,
        updated_at=now,
    )
    return repository.insert_user(session, user)
