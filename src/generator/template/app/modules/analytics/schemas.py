"""Schémas Pydantic du module analytics (Chap 5)."""

from pydantic import BaseModel


class CountryCount(BaseModel):
    country_code: str | None
    visits: int


class PathCount(BaseModel):
    path: str | None
    visits: int


class DayCount(BaseModel):
    date: str
    visits: int
