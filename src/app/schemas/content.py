from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Model(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class Player(Model):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=100)
    number: int = Field(ge=1,le=99)
    position: str = Field(min_length=1,max_length=30)

class Team(Model):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=100)
    short: str = Field(min_length=1,max_length=10)
    captain: str = Field(min_length=1,max_length=100)
    city: str = Field(min_length=1,max_length=100)
    group: Literal['Unassigned','Group A','Group B','Group C','Group D']
    logo: str = Field(max_length=28_000_000)
    players: list[Player] = Field(min_length=5,max_length=8)

class Fixture(Model):
    id: str = Field(min_length=1,max_length=80)
    stage: Literal['Group Stage','Quarter Final','Semi Final','Final']
    group: Literal['Group A','Group B','Group C','Group D','Knockout']
    homeId: str
    awayId: str
    date: str = Field(min_length=1,max_length=40)
    time: str = Field(pattern=r'^\d{2}:\d{2}$')
    pitch: str = Field(min_length=1,max_length=100)
    status: Literal['Upcoming','Live','Half Time','Full Time','Cancelled']
    homeScore: int | None = Field(default=None,ge=0,strict=True)
    awayScore: int | None = Field(default=None,ge=0,strict=True)

class Post(Model):
    id: str = Field(min_length=1,max_length=80)
    title: str = Field(max_length=200)
    slug: str = Field(max_length=200)
    category: str = Field(min_length=1,max_length=100)
    excerpt: str = Field(max_length=2000)
    content: str = Field(max_length=28_000_000)
    image: str = Field(max_length=28_000_000)
    date: str = Field(max_length=40)
    featured: bool
    status: Literal['Draft','Published']
    updatedAt: str | None = None

class Media(Model):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=200)
    src: str = Field(min_length=1,max_length=28_000_000)
    type: str = Field(min_length=1,max_length=100)
    category: str = Field(min_length=1,max_length=100)
    createdAt: str = Field(min_length=1,max_length=50)

class Gallery(Media):
    caption: str = Field(max_length=2000)
    featured: bool
    visible: bool
    order: int = Field(ge=0)

class Vendor(Model):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=100)
    category: str = Field(min_length=1,max_length=100)
    description: str = Field(min_length=1,max_length=5000)
    image: str = Field(max_length=28_000_000)
    website: str = Field(max_length=2000)
    visible: bool
    updatedAt: str = Field(max_length=50)

class SponsorLogo(Model):
    id: str = Field(min_length=1,max_length=80)
    name: str = Field(min_length=1,max_length=150)
    image: str = Field(min_length=1,max_length=28_000_000)
    scale: float = Field(default=1,ge=1,le=2,allow_inf_nan=False)

class Landing(Model):
    sponsorLogos: list[SponsorLogo] = Field(default_factory=list,max_length=50)
    heroEyebrow: str = Field(min_length=1,max_length=200)
    heroLineOne: str = Field(min_length=1,max_length=200)
    heroHighlight: str = Field(min_length=1,max_length=200)
    heroLineThree: str = Field(min_length=1,max_length=200)
    heroDescription: str = Field(min_length=1,max_length=5000)
    heroImages: list[str] = Field(min_length=3,max_length=3)
    primaryButton: str = Field(min_length=1,max_length=100)
    secondaryButton: str = Field(min_length=1,max_length=100)
    cultureEyebrow: str = Field(min_length=1,max_length=200)
    cultureTitle: str = Field(min_length=1,max_length=200)
    cultureDescription: str = Field(min_length=1,max_length=5000)
    cultureImage: str
    cultureButton: str = Field(min_length=1,max_length=100)
    ctaEyebrow: str = Field(min_length=1,max_length=200)
    ctaTitle: str = Field(min_length=1,max_length=200)
    ctaButton: str = Field(min_length=1,max_length=100)

class Branding(Model):
    mainLogo: str
    lightLogo: str
    favicon: str

class SettingsSchema(Model):
    banking: dict[str,str]
    registrationPrerequisites: str = Field(min_length=1,max_length=20_000)
    lifecycle: Literal['Pre Tournament','Matchday','Completed']
    tournamentName: str = Field(min_length=1,max_length=200)
    eventDate: str = Field(min_length=1,max_length=50)
    venue: str = Field(min_length=1,max_length=200)
    city: str = Field(min_length=1,max_length=100)
    prize: float = Field(ge=0,allow_inf_nan=False)
    numberOfTeams: int = Field(ge=2,le=1024,strict=True)
    affiliationFee: float = Field(ge=0,allow_inf_nan=False)
    spotBookingFee: float = Field(ge=0,allow_inf_nan=False)
    vendorStallFee: float = Field(ge=0,allow_inf_nan=False)
    contactEmail: str = Field(min_length=1,max_length=254)
    contactPhone: str = Field(min_length=1,max_length=100)
    whatsapp: str = Field(max_length=2000)
    instagram: str = Field(max_length=2000)
    facebook: str = Field(max_length=2000)
    twitter: str = Field(max_length=2000)
    youtube: str = Field(max_length=2000)
    tiktok: str = Field(max_length=2000)
    branding: Branding
    modules: dict[str,bool]

    @field_validator('modules')
    @classmethod
    def modules_known(cls,value):
        allowed={'news','tournament','fixtures','results','standings','knockout','teams','teamRegistration','vendorRegistration','vendors','gallery','sponsors','countdown','liveScores','homepageNews','homepageTeams','homepageSponsors'}
        if set(value)!=allowed: raise ValueError('Provide all known module flags')
        return value
