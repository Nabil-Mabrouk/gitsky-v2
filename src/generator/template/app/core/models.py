"""Modèles du core (Chap 4).

Deux entités toujours présentes dès que `MODULE_AUTH=true` (tier T1+) :
l'énumération de rôles `UserRole` et le modèle `User`. En T0 (Landing), la table
`users` n'est même pas créée — sa migration n'est pas appliquée (voir Chap 4).
"""

import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, func

from app.core.database import Base


class UserRole(str, enum.Enum):
    anonymous = "anonymous"
    waitlist = "waitlist"
    user = "user"
    premium = "premium"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    # Version des refresh tokens (Chap 7 §Révocation). Le JWT refresh embarque
    # cette valeur (claim `tv`) ; l'incrémenter invalide TOUS les refresh déjà
    # émis — seul levier de révocation d'un JWT stateless (token volé,
    # « déconnexion partout », changement de mot de passe).
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
