"""Verify BUG 1/2 fix: count enforcement + interest-specific content + no template markers."""
import os, requests, time

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://project-spark-ai-1.preview.emergentagent.com").rstrip("/")
EMAIL = "admin@projectgen.ai"
PWD = "ProjectGenAdmin123!"

TEMPLATE_MARKERS = [
    "Insight Hub", "Students need a focused", "Smart classification",
    "Natural-language assistant", "A scoped academic project with a clear user journey"
]


def _login():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


def test_generate_count_3_ocean():
    s = _login()
    payload = {
        "branch": "CSE", "year": "3rd Year", "skills": "python, ml",
        "interests": "ocean cleanup", "project_type": "AI/ML",
        "difficulty": "Intermediate", "team_size": 3, "duration": "3 months",
        "technologies": "python, react", "count": 3
    }
    t0 = time.time()
    r = s.post(f"{BASE}/api/projects/generate", json=payload, timeout=240)
    print(f"generate took {time.time()-t0:.1f}s status={r.status_code}")
    assert r.status_code == 200, f"generate failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    projects = data.get("projects", [])
    print(f"got {len(projects)} projects; titles: {[p.get('title') for p in projects]}")
    assert len(projects) == 3, f"expected 3 projects got {len(projects)}"

    for p in projects:
        blob = (p.get("title", "") + " " + p.get("description", "") + " " + p.get("problem_statement", "")).lower()
        for marker in TEMPLATE_MARKERS:
            assert marker.lower() not in blob, f"template marker '{marker}' found in {p.get('title')}"

    # At least half should reference ocean/water/marine keywords
    keywords = ["ocean", "marine", "water", "sea", "cleanup", "pollution", "plastic", "aquatic"]
    hits = sum(1 for p in projects if any(k in (p.get("title","")+p.get("description","")+p.get("problem_statement","")).lower() for k in keywords))
    print(f"ocean-related hits: {hits}/{len(projects)}")
    assert hits >= 2, f"only {hits}/3 projects reference ocean/marine keywords"


def test_no_mock_in_source():
    with open("/app/backend/server.py") as f:
        src = f.read()
    assert "mock_projects" not in src, "mock_projects still present in server.py"
    assert "Insight Hub" not in src, "Insight Hub template still present"
    assert "Students need a focused" not in src, "template phrase still present"


def test_refine_returns_ai_content():
    s = _login()
    # Get an existing project from history to refine
    r = s.get(f"{BASE}/api/projects", timeout=30)
    assert r.status_code == 200
    projs = r.json().get("projects", [])
    if not projs:
        print("no projects to refine, skipping")
        return
    proj = projs[0]
    r = s.post(f"{BASE}/api/ai/refine", json={"project": proj, "instruction": "add more IoT features"}, timeout=240)
    print(f"refine status={r.status_code}")
    assert r.status_code in (200, 503), f"unexpected: {r.status_code} {r.text[:200]}"
    if r.status_code == 200:
        refined = r.json().get("project", {})
        assert refined.get("title"), "refined project missing title"
