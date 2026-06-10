from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=6, max_length=255)
    address: str = Field(min_length=5, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=255)


class ProfileUpdateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr


class AddressRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    recipient_name: str = Field(min_length=2, max_length=120)
    line1: str = Field(min_length=5, max_length=255)
    city: str = Field(min_length=2, max_length=120)
    postal_code: str = Field(default="", max_length=20)
    country: str = Field(default="RO", min_length=2, max_length=2)
    is_default: bool = False


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=255)
    password: str = Field(min_length=8, max_length=255)
