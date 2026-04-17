"""
User schemas
"""
from pydantic import BaseModel, ConfigDict, EmailStr

class UserBase(BaseModel):
    """User base schema."""
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)

class UserCreate(UserBase):
    """User create schema."""
    password: str

class User(UserBase):
    """User schema."""
    id: int
    is_active: bool | None = None

class UserResponse(UserBase):
    """User response schema."""
    id: int
    is_active: bool
