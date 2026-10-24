from pydantic import BaseModel


class LogoutResponse(BaseModel):
    logout_url: str | None
