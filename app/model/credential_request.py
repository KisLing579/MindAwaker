from pydantic import BaseModel, model_validator

from app.configs.credentials import clear_legacy_credentials


class CredentialRequest(BaseModel):
    """Accept legacy clients, but discard all client-supplied credentials."""

    @model_validator(mode="before")
    @classmethod
    def discard_credentials(cls, values):
        return clear_legacy_credentials(values)
