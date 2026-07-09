"""Schémas Pydantic du module auth (Chap 5 §Validation)."""

from pydantic import BaseModel, ConfigDict, EmailStr

from app.core.models import UserRole


class Credentials(BaseModel):
    """Identifiants pour register et login."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
