from enum import StrEnum


class Role(StrEnum):
    RESEARCHER = "researcher"
    EDITOR = "editor"
    ADMIN = "admin"


class Locale(StrEnum):
    PT_BR = "pt-BR"
    EN = "en"
    RU = "ru"
