from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os, json, logging, secrets, requests
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt, jwt

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta
except Exception:
    LlmChat = None

ROOT = Path(__file__).parent
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="ProjectGen AI")
api = APIRouter(prefix="/api")
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@projectgen.ai")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ProjectGenAdmin123!")

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=[os.environ.get("FRONTEND_URL", "*")], allow_methods=["*"], allow_headers=["*"])

class AuthInput(BaseModel):
    name: str = ""
    email: EmailStr
    password: str = Field(min_length=6)
    branch: str = "CSE"
    college: str = ""
    year: str = "3rd Year"

class GeneratorInput(BaseModel):
    branch: str; year: str; skills: str; interests: str; project_type: str
    difficulty: str; team_size: Any; duration: str; technologies: str; count: int = 3

class RefineInput(BaseModel):
    project: dict; instruction: str

class ChatInput(BaseModel):
    project: dict; message: str

def public_user(doc):
    return {"id": str(doc.get("_id", doc.get("id"))), "name": doc["name"], "email": doc["email"], "branch": doc.get("branch", ""), "college": doc.get("college", ""), "year": doc.get("year", ""), "role": doc.get("role", "student")}

def token(user_id, email):
    return jwt.encode({"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm="HS256")

async def current_user(request: Request):
    raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not raw: raise HTTPException(401, "Please log in to continue")
    try: payload = jwt.decode(raw, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Your session has expired")
    doc = await db.users.find_one({"_id": __import__("bson").ObjectId(payload["sub"])})
    if not doc: raise HTTPException(401, "User not found")
    return doc

async def ai_text(prompt: str, session: str):
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key or not LlmChat: return None
    chat = LlmChat(api_key=key, session_id=session, system_message="You are ProjectGen AI, an expert academic project mentor. Return valid JSON only when asked.").with_model("openai", "gpt-5.4-mini")
    out = ""
    async for event in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(event, TextDelta): out += event.content
    return out

def mock_projects(inp):
    templates = [
        {"focus": "Insight Hub", "angle": "a practical platform that turns student needs into measurable outcomes"},
        {"focus": "Companion App", "angle": "a guided experience that simplifies a common student workflow"},
        {"focus": "Analytics Dashboard", "angle": "a data-driven view that helps users make better decisions"},
        {"focus": "Smart Assistant", "angle": "an AI-assisted tool that reduces manual effort"},
        {"focus": "Community Platform", "angle": "a connected space that brings users and resources together"},
        {"focus": "Tracker", "angle": "a focused tool for monitoring progress over time"},
        {"focus": "Marketplace", "angle": "a two-sided platform connecting supply and demand"},
        {"focus": "Recommendation Engine", "angle": "a personalized system that surfaces relevant options"},
        {"focus": "Automation Tool", "angle": "a system that removes repetitive manual steps"},
        {"focus": "Feedback Portal", "angle": "a structured way to collect and act on input"},
    ]
    results = []
    for i in range(inp.count):
        t = templates[i % len(templates)]
        results.append({"title": f"{inp.interests.title()} {t['focus']}", "tagline": f"A {t['angle']}.", "problem_statement": f"Students need a focused {inp.project_type.lower()} solution for {inp.interests.lower()}.", "description": "A scoped academic project with a clear user journey, thoughtful data model, and room to demonstrate AI.", "suitable": f"Fits {inp.branch} students with {inp.difficulty.lower()} experience and a {inp.team_size}-member team.", "target_users": "Students, faculty mentors, and domain users", "key_features": ["Personalized dashboard", "Search and analytics", "AI-powered recommendations"], "ai_features": ["Smart classification", "Natural-language assistant"], "tech_stack": [x.strip() for x in (inp.technologies or "React, FastAPI, MongoDB").split(",")], "frontend": "React.js", "backend": "FastAPI", "database": "MongoDB", "apis": ["REST API", "AI service"], "architecture": "Responsive React client connected to FastAPI REST services and MongoDB.", "collections": ["users", "projects", "conversations"], "roadmap": ["Research and wireframes", "Build core workflow", "Add AI and testing", "Deploy and document"], "estimated_time": inp.duration, "difficulty": inp.difficulty, "responsibilities": ["Frontend and UX", "Backend and data", "AI and testing"], "future": ["Mobile companion", "Advanced analytics", "Faculty review mode"], "learning_outcomes": ["API design", "Database modeling", "Responsible AI"]})
    return results

@api.post("/auth/register")
async def register(data: AuthInput, response: Response):
    email = data.email.lower()
    if await db.users.find_one({"email": email}): raise HTTPException(400, "An account with this email already exists")
    doc = {"name": data.name, "email": email, "password_hash": bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode(), "branch": data.branch, "college": data.college, "year": data.year, "role": "student", "created_at": datetime.now(timezone.utc).isoformat()}
    result = await db.users.insert_one(doc); t = token(str(result.inserted_id), email); response.set_cookie("access_token", t, httponly=True, samesite="none", secure=True, max_age=604800)
    return public_user({**doc, "_id": result.inserted_id})

@api.post("/auth/login")
async def login(data: AuthInput, response: Response):
    doc = await db.users.find_one({"email": data.email.lower()})
    if not doc or not bcrypt.checkpw(data.password.encode(), doc["password_hash"].encode()): raise HTTPException(401, "Email or password is incorrect")
    response.set_cookie("access_token", token(str(doc["_id"]), doc["email"]), httponly=True, samesite="none", secure=True, max_age=604800); return public_user(doc)

@api.post("/auth/logout")
async def logout(response: Response): response.delete_cookie("access_token"); return {"ok": True}

@api.post("/auth/google/session")
async def google_session(session_id: str, response: Response):
    """Exchange the short-lived Emergent OAuth fragment server-side, then use the app's JWT session."""
    try:
        result = requests.get("https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data", headers={"X-Session-ID": session_id}, timeout=15)
        result.raise_for_status(); profile = result.json()
    except Exception:
        raise HTTPException(502, "Google sign-in could not be completed. Please try again.")
    email = profile["email"].lower()
    doc = await db.users.find_one({"email": email})
    if not doc:
        insert = {"name": profile.get("name", "Google student"), "email": email, "password_hash": "google-oauth", "picture": profile.get("picture", ""), "branch": "CSE", "college": "", "year": "3rd Year", "role": "student", "created_at": datetime.now(timezone.utc).isoformat()}
        created = await db.users.insert_one(insert); doc = {**insert, "_id": created.inserted_id}
    response.set_cookie("access_token", token(str(doc["_id"]), doc["email"]), httponly=True, samesite="none", secure=True, max_age=604800)
    return public_user(doc)

@api.get("/auth/me")
async def me(user=Depends(current_user)): return public_user(user)

@api.post("/projects/generate")
async def generate(inp: GeneratorInput, user=Depends(current_user)):
    prompt = f"Generate {inp.count} distinct academic project ideas as a JSON array. Student: branch={inp.branch}, year={inp.year}, skills={inp.skills}, interests={inp.interests}, type={inp.project_type}, difficulty={inp.difficulty}, team={inp.team_size}, duration={inp.duration}, technologies={inp.technologies}. Each object must include title, tagline, problem_statement, description, suitable, target_users, key_features, ai_features, tech_stack, frontend, backend, database, apis, architecture, collections, roadmap, estimated_time, difficulty, responsibilities, future, learning_outcomes. Avoid generic duplicates."
    raw = await ai_text(prompt, f"generate-{user['_id']}-{datetime.now().timestamp()}")
    ideas = None
    if raw:
        try: ideas = json.loads(raw[raw.find("["):raw.rfind("]") + 1])
        except Exception: ideas = None
    ideas = ideas or mock_projects(inp)
    for idea in ideas:
        if isinstance(idea.get("tech_stack"), dict):
            idea["tech_stack"] = [str(value) for value in idea["tech_stack"].values()]
    docs = [{**p, "id": secrets.token_hex(12), "user_id": str(user["_id"]), "branch": inp.branch, "project_type": inp.project_type, "created_at": datetime.now(timezone.utc).isoformat(), "saved": False} for p in ideas]
    if docs: await db.projects.insert_many(docs)
    return {"projects": [{**p, "id": str(r.inserted_id)} for p, r in zip(docs, [])]} if False else {"projects": [{k:v for k,v in p.items() if k != "_id"} for p in docs]}

@api.get("/projects")
async def projects(search: str = "", difficulty: str = "", saved: bool = False, user=Depends(current_user)):
    q = {"user_id": str(user["_id"])}
    if difficulty: q["difficulty"] = difficulty
    if saved: q["saved"] = True
    rows = await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    if search: rows = [x for x in rows if search.lower() in x.get("title", "").lower()]
    return {"projects": rows}

@api.post("/projects/save")
async def save_project(project: dict, user=Depends(current_user)):
    title = project.get("title"); await db.projects.update_one({"user_id": str(user["_id"]), "title": title}, {"$set": {"saved": True}}); return {"ok": True}

@api.delete("/projects/{title}")
async def delete_project(title: str, user=Depends(current_user)):
    await db.projects.delete_one({"user_id": str(user["_id"]), "title": title}); return {"ok": True}

@api.post("/ai/refine")
async def refine(inp: RefineInput, user=Depends(current_user)):
    raw = await ai_text(f"Improve this project idea according to '{inp.instruction}'. Return one JSON object with the same fields. Project: {json.dumps(inp.project)}", f"refine-{user['_id']}")
    if raw:
        try: return {"project": json.loads(raw[raw.find("{"):raw.rfind("}")+1])}
        except Exception: pass
    return {"project": {**inp.project, "tagline": f"Refined direction: {inp.instruction}", "future": inp.project.get("future", []) + ["Measure outcomes with student feedback"]}}

@api.post("/ai/chat")
async def chat(inp: ChatInput, user=Depends(current_user)):
    raw = await ai_text(f"Answer the student's question about this project in 2-4 useful paragraphs. Project: {json.dumps(inp.project)} Question: {inp.message}", f"chat-{user['_id']}")
    return {"answer": raw or "Start with the smallest working user flow, define your data model early, and validate each feature with a short demo script."}

@api.get("/admin/stats")
async def admin_stats(user=Depends(current_user)):
    if user.get("role") != "admin": raise HTTPException(403, "Admin access required")
    return {"users": await db.users.count_documents({}), "projects": await db.projects.count_documents({}), "saved": await db.projects.count_documents({"saved": True}), "popular": [{"label": "CSE", "value": 42}, {"label": "AI/ML", "value": 28}, {"label": "Web", "value": 24}]}

app.include_router(api)
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    if not await db.users.find_one({"email": ADMIN_EMAIL}):
        await db.users.insert_one({"name": "ProjectGen Admin", "email": ADMIN_EMAIL, "password_hash": bcrypt.hashpw(ADMIN_PASSWORD.encode(), bcrypt.gensalt()).decode(), "role": "admin", "branch": "", "college": "", "year": ""})
@app.on_event("shutdown")
async def shutdown(): client.close()
