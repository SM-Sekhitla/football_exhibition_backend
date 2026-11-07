from typing import Literal
from app.core.config import settings
from pydantic import EmailStr, Field, field_validator
from app.schemas.auth import Password, StrictModel

class Proof(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    data: str = Field(min_length=10, max_length=settings.max_document_size_mb * 1024 * 1024 * 4 // 3 + 1024)
    type: Literal['application/pdf','image/jpeg','image/png']

class TeamApplication(StrictModel):
    teamName: str = Field(min_length=1, max_length=100)
    captain: str = Field(min_length=1, max_length=100)
    email: EmailStr
    city: str = Field(min_length=1, max_length=100)
    players: list[str] = Field(min_length=5, max_length=8)
    proofOfPayment: Proof
    prerequisitesAccepted: Literal[True]

    @field_validator('players')
    @classmethod
    def unique_players(cls, players):
        names = [p.strip() for p in players]
        if any(not p or len(p)>100 for p in names) or len({p.casefold() for p in names}) != len(names):
            raise ValueError('Enter 5–8 distinct player names, up to 100 characters each')
        return names

class VendorApplication(StrictModel):
    business: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    email: EmailStr
    description: str = Field(min_length=1, max_length=2000)

class Review(StrictModel):
    status: Literal['Pending','Approved','Rejected']
    paymentStatus: Literal['Awaiting payment','Under review','Verified']
    reviewNote: str = Field(default='', max_length=2000)

class Lookup(StrictModel):
    reference: str = Field(min_length=3, max_length=80)
    email: EmailStr

class Banking(StrictModel):
    bankName: str = Field(min_length=1, max_length=100)
    accountNumber: str = Field(min_length=1, max_length=50)
    accountName: str = Field(min_length=1, max_length=100)
    accountType: str = Field(min_length=1, max_length=100)
    branchCode: str = Field(min_length=1, max_length=30)
    reference: str = Field(min_length=1, max_length=500)

class BankingUpdate(StrictModel):
    banking: Banking
    password: Password = Field(min_length=1, max_length=200)
