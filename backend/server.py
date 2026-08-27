from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / ".env")

import os, json, logging, secrets, requests, asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
import bcrypt, jwt, httpx
from bson import ObjectId

logging.basicConfig(level=logging.INFO)

ROOT = Path(__file__).parent
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
app = FastAPI(title="ProjectGen AI")
api = APIRouter(prefix="/api")
JWT_SECRET = os.environ["JWT_SECRET"]
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@projectgen.ai")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ProjectGenAdmin123!")

app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origin_regex=".*", allow_methods=["*"], allow_headers=["*"])

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

class VivaInput(BaseModel):
    project: dict

def public_user(doc):
    return {"id": str(doc.get("_id", doc.get("id"))), "name": doc["name"], "email": doc["email"], "branch": doc.get("branch", ""), "college": doc.get("college", ""), "year": doc.get("year", ""), "role": doc.get("role", "student")}

def token(user_id, email):
    return jwt.encode({"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm="HS256")

async def current_user(request: Request):
    raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not raw: raise HTTPException(401, "Please log in to continue")
    try: payload = jwt.decode(raw, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Your session has expired")
    try: doc = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    except Exception: raise HTTPException(401, "Invalid token")
    if not doc: raise HTTPException(401, "User not found")
    return doc

AI_SEMAPHORE = asyncio.Semaphore(1)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
AI_ENABLED = bool(GROQ_API_KEY)
AI_BUSY_MESSAGE = "The AI mentor is busy with another request. Please wait a few seconds and try again."
AI_SYSTEM_MESSAGE = "You are ProjectGen AI, an expert academic project mentor. Return valid JSON only when asked."

async def ai_text(prompt: str, session: str):
    if not AI_ENABLED: return None
    async with AI_SEMAPHORE:
        async with httpx.AsyncClient(timeout=120) as http:
            for attempt in range(3):
                try:
                    r = await http.post("https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                        json={"model": GROQ_MODEL, "messages": [{"role": "system", "content": AI_SYSTEM_MESSAGE}, {"role": "user", "content": prompt}], "temperature": 0.9, "max_completion_tokens": 7000, "reasoning_effort": "low"})
                    if r.status_code in (413, 429):
                        await asyncio.sleep(6 * (attempt + 1)); continue
                    r.raise_for_status()
                    out = r.json()["choices"][0]["message"]["content"]
                    if out and out.strip(): return out
                except Exception as e:
                    logging.error(f"Groq AI call failed: {e}")
                    await asyncio.sleep(2)
    return None

def parse_ideas(raw):
    if not raw: return None
    start = raw.find("[")
    if start == -1: return None
    candidates = []
    if "]" in raw[start:]: candidates.append(raw[start:raw.rfind("]") + 1])
    if "}" in raw[start:]: candidates.append(raw[start:raw.rfind("}") + 1] + "]")
    for text in candidates:
        try:
            ideas = json.loads(text)
            found = [x for x in ideas if isinstance(x, dict) and x.get("title")]
            if found: return found
        except Exception: continue
    return None

@api.post("/auth/register")
async def register(data: AuthInput, response: Response):
    email = data.email.lower()
    if await db.users.find_one({"email": email}): raise HTTPException(400, "An account with this email already exists")
    doc = {"name": data.name, "email": email, "password_hash": bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode(), "branch": data.branch, "college": data.college, "year": data.year, "role": "student", "created_at": datetime.now(timezone.utc).isoformat()}
    result = await db.users.insert_one(doc); t = token(str(result.inserted_id), email); response.set_cookie("access_token", t, httponly=True, samesite="lax", max_age=604800)
    return public_user({**doc, "_id": result.inserted_id})

@api.post("/auth/login")
async def login(data: AuthInput, response: Response):
    doc = await db.users.find_one({"email": data.email.lower()})
    if not doc or not bcrypt.checkpw(data.password.encode(), doc["password_hash"].encode()): raise HTTPException(401, "Email or password is incorrect")
    response.set_cookie("access_token", token(str(doc["_id"]), doc["email"]), httponly=True, samesite="lax", max_age=604800); return public_user(doc)

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
    response.set_cookie("access_token", token(str(doc["_id"]), doc["email"]), httponly=True, samesite="lax", max_age=604800)
    return public_user(doc)

@api.get("/auth/me")
async def me(user=Depends(current_user)): return public_user(user)

@api.post("/projects/generate")
async def generate(inp: GeneratorInput, user=Depends(current_user)):
    if not AI_ENABLED: raise HTTPException(503, "The AI service is not configured on this server (missing GROQ_API_KEY). Ideas cannot be generated.")
    def build_prompt(count, exclude):
        avoid = f" Do NOT repeat these titles: {', '.join(exclude)}." if exclude else ""
        return f"Generate exactly {count} distinct academic project ideas as a JSON array of {count} objects. Student profile: branch={inp.branch}, year={inp.year}, skills={inp.skills}, interests={inp.interests}, type={inp.project_type}, difficulty={inp.difficulty}, team={inp.team_size}, duration={inp.duration}, technologies={inp.technologies}. Every idea must be clearly specific to the stated interests and skills. Each object must include title, tagline, problem_statement, description, suitable, target_users, key_features, ai_features, tech_stack, frontend, backend, database, apis, architecture, collections, roadmap, estimated_time, difficulty, responsibilities, future, learning_outcomes. Keep every string concise (max 22 words) and every list at most 5 items so the full array fits in the response.{avoid}"
    ideas = parse_ideas(await ai_text(build_prompt(inp.count, []), f"generate-{user['_id']}-{datetime.now().timestamp()}")) or []
    if ideas and len(ideas) < inp.count:
        extra = parse_ideas(await ai_text(build_prompt(inp.count - len(ideas), [i["title"] for i in ideas]), f"generate-topup-{user['_id']}-{datetime.now().timestamp()}"))
        if extra:
            titles = {i["title"] for i in ideas}
            ideas += [x for x in extra if x["title"] not in titles]
    if not ideas: raise HTTPException(503, AI_BUSY_MESSAGE)
    ideas = ideas[:inp.count]
    for idea in ideas:
        if isinstance(idea.get("tech_stack"), dict):
            idea["tech_stack"] = [str(value) for value in idea["tech_stack"].values()]
    docs = [{**p, "id": secrets.token_hex(12), "user_id": str(user["_id"]), "branch": inp.branch, "project_type": inp.project_type, "created_at": datetime.now(timezone.utc).isoformat(), "saved": False} for p in ideas]
    if docs: await db.projects.insert_many(docs)
    return {"projects": [{k: v for k, v in p.items() if k != "_id"} for p in docs]}

@api.get("/projects")
async def projects(search: str = "", difficulty: str = "", saved: bool = False, user=Depends(current_user)):
    q = {"user_id": str(user["_id"])}
    if difficulty: q["difficulty"] = difficulty
    if saved: q["saved"] = True
    rows = await db.projects.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    for row in rows:
        if isinstance(row.get("tech_stack"), dict): row["tech_stack"] = [str(v) for v in row["tech_stack"].values()]
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
    raise HTTPException(503, AI_BUSY_MESSAGE if AI_ENABLED else "The AI service is not configured on this server.")

@api.post("/ai/chat")
async def chat(inp: ChatInput, user=Depends(current_user)):
    raw = await ai_text(f"Answer the student's question about this project in 2-4 useful paragraphs. Project: {json.dumps(inp.project)} Question: {inp.message}", f"chat-{user['_id']}")
    if not raw: raise HTTPException(503, AI_BUSY_MESSAGE if AI_ENABLED else "The AI service is not configured on this server.")
    return {"answer": raw}

@api.post("/ai/viva")
async def viva(inp: VivaInput, user=Depends(current_user)):
    raw = await ai_text(f"You are an examiner. Generate 8 likely viva/oral-examination questions with strong suggested answers (3-5 sentences each) for this student project. Return only a JSON array of objects with 'question' and 'answer' string fields. Project: {json.dumps(inp.project)}", f"viva-{user['_id']}")
    items = None
    if raw:
        try:
            items = json.loads(raw[raw.find("["):raw.rfind("]") + 1])
            items = [x for x in items if isinstance(x, dict) and x.get("question")]
        except Exception: items = None
    if not items:
        raise HTTPException(503, AI_BUSY_MESSAGE if AI_ENABLED else "The AI service is not configured on this server.")
    return {"questions": items}

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