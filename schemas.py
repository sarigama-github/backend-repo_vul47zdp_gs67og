"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogpost" collection
- Inquiry -> "inquiry" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user"
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Password hash (PBKDF2)")
    salt: str = Field(..., description="Per-user salt for hashing")
    avatar_url: Optional[str] = Field(None, description="Avatar image URL")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(True, description="Whether user is active")

class BlogPost(BaseModel):
    """
    Blog posts collection schema
    Collection name: "blogpost"
    """
    title: str
    slug: str = Field(..., description="URL-friendly unique slug")
    excerpt: Optional[str] = None
    content: str
    author: str
    tags: List[str] = []
    cover_image: Optional[str] = None
    published_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

class Inquiry(BaseModel):
    """
    Contact inquiries collection schema
    Collection name: "inquiry"
    """
    name: str
    email: EmailStr
    message: str
    status: str = Field("new", description="Status of the inquiry")
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)

# Note: The Flames database viewer can read these models from GET /schema
