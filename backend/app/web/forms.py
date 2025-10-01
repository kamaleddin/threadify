"""Form schemas for web UI."""

from pydantic import BaseModel, HttpUrl


class SubmitForm(BaseModel):
    """Form data for URL submission."""

    url: HttpUrl
    account_id: int
    mode: str = "review"
    type: str = "thread"
    style: str = "punchy"
    summary_mode: str = "extractive"
    thread_cap: int = 12
    single_cap: int = 1400
    include_reference: bool = True
    utm_campaign: str = "threadify"
    include_image: bool = True
    include_hook: bool = True
    force: bool = False

    class Config:
        """Pydantic config."""

        str_strip_whitespace = True
