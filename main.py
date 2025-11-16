import os
import hashlib
import secrets
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from database import db, create_document, get_documents
from schemas import User as UserSchema, BlogPost as BlogPostSchema, Inquiry as InquirySchema

app = FastAPI(title="Modern Minimal App API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------
# Helper functions
# -----------------

def hash_password(password: str, salt: Optional[str] = None):
    if not salt:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 120_000)
    return dk.hex(), salt

# In-memory token store for demo (non-persistent, acceptable for this environment)
# Note: We still use DB for user data. Tokens are ephemeral for preview purposes.
TOKENS = {}

# -----------------
# Request/Response models
# -----------------
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    token: str
    name: str
    email: EmailStr

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    message: str

class DashboardStats(BaseModel):
    welcome: str
    stats: dict
    quick_actions: List[dict]

# -----------------
# Basic routes
# -----------------
@app.get("/")
def read_root():
    return {"message": "Modern Minimal App Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set",
        "database_name": "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            try:
                response["collections"] = db.list_collection_names()
                response["connection_status"] = "Connected"
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "❌ Not Initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# -----------------
# Auth endpoints
# -----------------
@app.post("/api/auth/signup", response_model=AuthResponse)
def signup(payload: SignupRequest):
    # Check if user exists
    existing = db["user"].find_one({"email": payload.email}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    password_hash, salt = hash_password(payload.password)
    user_doc = UserSchema(
        name=payload.name,
        email=payload.email,
        password_hash=password_hash,
        salt=salt,
    )
    _id = create_document("user", user_doc)
    token = secrets.token_urlsafe(24)
    TOKENS[token] = {
        "email": payload.email,
        "name": payload.name,
    }
    return AuthResponse(token=token, name=payload.name, email=payload.email)

@app.post("/api/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    user = db["user"].find_one({"email": payload.email}) if db else None
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    computed_hash, _ = hash_password(payload.password, user.get("salt"))
    if computed_hash != user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(24)
    TOKENS[token] = {
        "email": user["email"],
        "name": user.get("name", "")
    }
    return AuthResponse(token=token, name=TOKENS[token]["name"], email=user["email"])

# Simple dependency to get current user from token (if provided)
class TokenHeader(BaseModel):
    token: Optional[str] = None


def get_current_user(token: Optional[str] = None):
    if token and token in TOKENS:
        return TOKENS[token]
    return None

# -----------------
# Dashboard
# -----------------
@app.get("/api/dashboard", response_model=DashboardStats)
def dashboard(token: Optional[str] = None):
    user = get_current_user(token)
    name = user["name"] if user else "Guest"
    email = user["email"] if user else None
    # Example stats (some depend on DB counts)
    users_count = db["user"].count_documents({}) if db else 0
    posts_count = db["blogpost"].count_documents({}) if db else 0
    inquiries_count = db["inquiry"].count_documents({}) if db else 0
    stats = {
        "Users": users_count,
        "Articles": posts_count,
        "Inquiries": inquiries_count
    }
    if email:
        stats["Your Email"] = email
    quick_actions = [
        {"label": "Create Post", "href": "/blog/new"},
        {"label": "View Articles", "href": "/blog"},
        {"label": "Contact Support", "href": "/contact"},
    ]
    return DashboardStats(welcome=f"Welcome, {name}", stats=stats, quick_actions=quick_actions)

# -----------------
# Blog
# -----------------
class BlogCreate(BaseModel):
    title: str
    slug: str
    excerpt: Optional[str] = None
    content: str
    author: str
    tags: Optional[List[str]] = []
    cover_image: Optional[str] = None

@app.get("/api/blogs")
def list_blogs(limit: int = 20):
    items = get_documents("blogpost", {}, limit)
    # sanitize ObjectId
    for it in items:
        it["id"] = str(it.pop("_id", ""))
    return {"items": items}

@app.get("/api/blogs/{slug}")
def get_blog(slug: str):
    doc = db["blogpost"].find_one({"slug": slug}) if db else None
    if not doc:
        raise HTTPException(status_code=404, detail="Post not found")
    doc["id"] = str(doc.pop("_id", ""))
    return doc

@app.post("/api/blogs")
def create_blog(payload: BlogCreate):
    # upsert by slug
    exists = db["blogpost"].find_one({"slug": payload.slug}) if db else None
    blog = BlogPostSchema(**payload.model_dump())
    if exists:
        db["blogpost"].update_one({"slug": payload.slug}, {"$set": blog.model_dump()})
        return {"status": "updated", "slug": payload.slug}
    _id = create_document("blogpost", blog)
    return {"status": "created", "id": _id}

# -----------------
# Contact
# -----------------
@app.post("/api/contact")
def contact(payload: ContactRequest):
    inquiry = InquirySchema(**payload.model_dump())
    _id = create_document("inquiry", inquiry)
    return {"status": "received", "id": _id}

# -----------------
# Seed sample content (idempotent)
# -----------------
@app.post("/api/seed")
def seed_content():
    samples = [
        {
            "title": "Designing With Purpose",
            "slug": "designing-with-purpose",
            "excerpt": "Crafting interfaces that feel calm and intentional.",
            "content": "# Designing With Purpose\n\nMinimalism isn't about less; it's about clarity...",
            "author": "Flames Team",
            "tags": ["design", "ux"],
            "cover_image": None,
        },
        {
            "title": "Subtle Motion, Big Impact",
            "slug": "subtle-motion-big-impact",
            "excerpt": "Using micro-interactions to guide attention.",
            "content": "# Subtle Motion\n\nMotion should support meaning, not distract...",
            "author": "Flames Team",
            "tags": ["motion", "ui"],
            "cover_image": None,
        },
    ]
    created = 0
    for s in samples:
        if not db["blogpost"].find_one({"slug": s["slug"]}):
            create_document("blogpost", BlogPostSchema(**s))
            created += 1
    return {"status": "ok", "created": created}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
