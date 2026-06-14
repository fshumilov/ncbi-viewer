from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error detail")
    request_id: str | None = Field(default=None, description="Correlation id for this request")
