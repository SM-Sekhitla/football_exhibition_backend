from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

Password = Annotated[str, StringConstraints(strip_whitespace=False)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Login(StrictModel):
    email: EmailStr
    password: Password = Field(min_length=1, max_length=200)
    remember: bool = False

class ChangePassword(StrictModel):
    currentPassword: Password = Field(max_length=200)
    newPassword: Password = Field(min_length=12, max_length=200)

class ResetRequest(StrictModel):
    email: EmailStr

class ResetPassword(StrictModel):
    token: str = Field(min_length=30, max_length=200)
    password: Password = Field(min_length=12, max_length=200)

class UserCreate(StrictModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    role: Literal['super_admin','admin','manager','editor','reviewer']
    password: Password | None = Field(default=None, min_length=12, max_length=200)

class UserUpdate(StrictModel):
    role: Literal['super_admin','admin','manager','editor','reviewer']
    active: bool
