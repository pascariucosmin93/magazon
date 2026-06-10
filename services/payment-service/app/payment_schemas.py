from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    return_base_url: str
