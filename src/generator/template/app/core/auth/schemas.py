"""Schémas Pydantic du module auth (Chap 5 §Validation)."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.models import UserRole


class Credentials(BaseModel):
    """Identifiants pour le login — password NON contraint : un compte créé
    avant la politique de mot de passe doit toujours pouvoir se connecter."""

    email: EmailStr
    password: str


class RegisterRequest(Credentials):
    """Création de compte : la politique de mot de passe s'applique ICI
    (et seulement ici) — 8 caractères minimum."""

    password: str = Field(min_length=8)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
