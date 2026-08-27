"""Iteration 5 retest: verify count>=5 regression fix on Groq gpt-oss-120b.
Spaces AI calls 60s apart due to 8000 TPM free-tier limit."""
import os, requests, time, pytest

def _load_url():
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL not found")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_url()).rstrip("/")
EMAIL = "admin@projectgen.ai"
PWD = "ProjectGenAdmin123!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    return s


def _generate(s, count, interests, keywords):
    payload = {
        "branch": "CSE", "year": "3rd Year",
        "skills": "python, ml, iot", "interests": interests,
        "project_type": "AI/ML", "difficulty": "Intermediate",
        "team_size": 3, "duration": "3 months",
        "technologies": "python, react", "count": count,
    }
    t0 = time.time()
    r = s.post(f"{BASE}/api/projects/generate", json=payload, timeout=120)
    elapsed = time.time() - t0
    print(f"[count={count} interests='{interests}'] {r.status_code} in {elapsed:.1f}s")
    # tier retry once if 503 possibly due to TPM window
    if r.status_code == 503:
        print("503 - sleeping 60s and retrying once (possible TPM window)")
        time.sleep(60)
        t0 = time.time()
        r = s.post(f"{BASE}/api/projects/generate", json=payload, timeout=120)
        print(f"[retry count={count}] {r.status_code} in {time.time()-t0:.1f}s")
    assert r.status_code == 200, f"generate failed: {r.status_code} {r.text[:400]}"
    projects = r.json().get("projects", [])
    titles = [p.get("title") for p in projects]
    print(f"got {len(projects)} titles: {titles}")
    assert len(projects) == count, f"expected {count} got {len(projects)}"
    assert len({t for t in titles if t}) == count, f"non-distinct titles: {titles}"
    hits = sum(1 for p in projects if any(
        k in (p.get("title","")+" "+p.get("description","")+" "+p.get("problem_statement","")).lower()
        for k in keywords))
    print(f"keyword hits: {hits}/{count}")
    assert hits >= max(1, count // 2), f"only {hits}/{count} match {keywords}"
    return projects


def test_a_count3(session):
    _generate(session, 3, "smart agriculture", ["farm", "agri", "crop", "irrigation", "soil"])


def test_b_count5(session):
    print("sleep 60s for TPM window")
    time.sleep(60)
    _generate(session, 5, "renewable energy", ["renewable", "solar", "wind", "energy", "grid", "battery"])


def test_c_count10(session):
    print("sleep 60s for TPM window")
    time.sleep(60)
    _generate(session, 10, "music production", ["music", "audio", "sound", "song", "instrument", "beat", "midi"])


def test_d_refine(session):
    print("sleep 60s for TPM window")
    time.sleep(60)
    r = session.get(f"{BASE}/api/projects", timeout=30)
    projs = r.json().get("projects", [])
    if not projs:
        pytest.skip("no projects to refine")
    proj = projs[0]
    r = session.post(f"{BASE}/api/ai/refine", json={"project": proj, "instruction": "add IoT features"}, timeout=120)
    print(f"refine {r.status_code}")
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("project", {}).get("title")


def test_e_viva(session):
    print("sleep 60s for TPM window")
    time.sleep(60)
    r = session.get(f"{BASE}/api/projects", timeout=30)
    projs = r.json().get("projects", [])
    if not projs:
        pytest.skip("no projects for viva")
    r = session.post(f"{BASE}/api/ai/viva", json={"project": projs[0]}, timeout=120)
    print(f"viva {r.status_code}")
    assert r.status_code == 200, r.text[:300]
    qs = r.json().get("questions", [])
    print(f"viva questions: {len(qs)}")
    assert len(qs) >= 6, f"expected ~8 got {len(qs)}"
