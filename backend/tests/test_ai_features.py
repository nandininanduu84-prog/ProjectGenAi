import os, uuid, requests, pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN = {"email": "admin@projectgen.ai", "password": "ProjectGenAdmin123!"}
LONG = 240  # AI can take ~30-120s per call

MOCK_MARKERS = ["Insight Hub", "Smart classification", "Natural-language assistant",
                "Students need a focused"]


def _is_mock(project: dict) -> bool:
    blob = " ".join([
        project.get("title", ""),
        project.get("problem_statement", ""),
        " ".join(project.get("ai_features", []) or []),
        " ".join(project.get("key_features", []) or []),
    ])
    return any(m in blob for m in MOCK_MARKERS)


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def two_generations(admin_session):
    """Serial AI generations with distinct interests. Provider allows 1 concurrent call."""
    payload_a = {"branch": "CSE", "year": "3rd Year", "skills": "Python, C++",
                 "interests": "smart farming drones", "project_type": "IoT",
                 "difficulty": "Intermediate", "team_size": 3, "duration": "2 months",
                 "technologies": "React, FastAPI, MongoDB", "count": 3}
    payload_b = dict(payload_a, interests="stock market prediction",
                     project_type="AI/ML", technologies="React, FastAPI, MongoDB, Python ML")
    ra = admin_session.post(f"{BASE_URL}/api/projects/generate", json=payload_a, timeout=LONG)
    assert ra.status_code == 200, ra.text
    rb = admin_session.post(f"{BASE_URL}/api/projects/generate", json=payload_b, timeout=LONG)
    assert rb.status_code == 200, rb.text
    return ra.json()["projects"], rb.json()["projects"]


# --- Bug verification: distinct, non-mock generations
class TestGenerationDistinct:
    def test_first_generation_returns_ids_and_features(self, two_generations):
        a, _ = two_generations
        assert len(a) == 3
        for p in a:
            assert p.get("id")
            assert p.get("title")
            assert isinstance(p.get("key_features", []), list) and len(p["key_features"]) >= 3

    def test_generations_are_not_mock(self, two_generations):
        a, b = two_generations
        assert not any(_is_mock(p) for p in a), f"mock leaked in A: {[p['title'] for p in a]}"
        assert not any(_is_mock(p) for p in b), f"mock leaked in B: {[p['title'] for p in b]}"

    def test_generations_are_distinct_between_inputs(self, two_generations):
        a, b = two_generations
        titles_a = {p["title"].lower() for p in a}
        titles_b = {p["title"].lower() for p in b}
        assert titles_a.isdisjoint(titles_b), f"Titles overlap: {titles_a & titles_b}"

    def test_generations_reflect_input_topic(self, two_generations):
        a, b = two_generations
        blob_a = " ".join(p["title"].lower() + " " + p.get("problem_statement", "").lower() for p in a)
        blob_b = " ".join(p["title"].lower() + " " + p.get("problem_statement", "").lower() for p in b)
        assert any(k in blob_a for k in ["farm", "drone", "crop", "agri", "iot", "field"]), blob_a[:200]
        assert any(k in blob_b for k in ["stock", "market", "trad", "financ", "predict", "invest"]), blob_b[:200]


# --- Refine
class TestRefine:
    def test_refine_returns_modified_project(self, admin_session, two_generations):
        base = two_generations[0][0]
        r = admin_session.post(f"{BASE_URL}/api/ai/refine",
                               json={"project": base, "instruction": "Make it more advanced"},
                               timeout=LONG)
        assert r.status_code == 200, r.text
        refined = r.json()["project"]
        assert refined.get("title")
        # Must NOT be the naive fallback tagline
        assert not (refined.get("tagline", "").startswith("Refined direction:"))


# --- Ask mentor / chat
class TestChat:
    def test_chat_returns_answer(self, admin_session, two_generations):
        base = two_generations[0][0]
        r = admin_session.post(f"{BASE_URL}/api/ai/chat",
                               json={"project": base, "message": "How do I split work across a 3-member team?"},
                               timeout=LONG)
        assert r.status_code == 200, r.text
        ans = r.json().get("answer", "")
        assert isinstance(ans, str) and len(ans) > 40


# --- Viva
class TestViva:
    def test_viva_returns_questions(self, admin_session, two_generations):
        base = two_generations[0][0]
        r = admin_session.post(f"{BASE_URL}/api/ai/viva",
                               json={"project": base}, timeout=LONG)
        assert r.status_code == 200, r.text
        qs = r.json()["questions"]
        assert isinstance(qs, list) and len(qs) >= 3
        assert all(q.get("question") and q.get("answer") for q in qs)


# --- Save / list / delete
class TestSaveDelete:
    def test_save_then_favorites_then_delete(self, admin_session, two_generations):
        base = two_generations[0][0]
        title = base["title"]
        s = admin_session
        assert s.post(f"{BASE_URL}/api/projects/save", json=base, timeout=30).status_code == 200
        fav = s.get(f"{BASE_URL}/api/projects?saved=true", timeout=30).json()["projects"]
        assert any(p["title"] == title for p in fav)
        assert s.delete(f"{BASE_URL}/api/projects/{title}", timeout=30).status_code == 200
        after = s.get(f"{BASE_URL}/api/projects?saved=true", timeout=30).json()["projects"]
        assert not any(p["title"] == title for p in after)


# --- History listing includes both saved and unsaved
class TestHistory:
    def test_history_returns_all(self, admin_session):
        rows = admin_session.get(f"{BASE_URL}/api/projects", timeout=30).json()["projects"]
        assert isinstance(rows, list) and len(rows) >= 3


# --- Google session invalid handling
class TestGoogleSession:
    def test_invalid_session_returns_502(self):
        r = requests.post(f"{BASE_URL}/api/auth/google/session?session_id=fake", timeout=30)
        assert r.status_code == 502
