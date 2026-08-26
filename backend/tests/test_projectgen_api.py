import os
import uuid
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@projectgen.ai", "password": "ProjectGenAdmin123!"}


def test_auth_cookie_me_admin_and_logout():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert "access_token" in s.cookies
    assert s.get(f"{BASE_URL}/api/auth/me").json()["email"] == ADMIN["email"]
    assert s.post(f"{BASE_URL}/api/auth/logout").status_code == 200
    assert s.get(f"{BASE_URL}/api/auth/me").status_code == 401


def test_register_and_protected_generate_returns_requested_count_and_ids():
    s = requests.Session()
    email = f"test_{uuid.uuid4().hex}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={"name": "Test Student", "email": email, "password": "TestPass123!"})
    assert r.status_code == 200
    payload = {"branch":"CSE", "year":"3rd Year", "skills":"React", "interests":"Health", "project_type":"Full Stack", "difficulty":"Intermediate", "team_size":3, "duration":"2 months", "technologies":"React, FastAPI", "count":3}
    r = s.post(f"{BASE_URL}/api/projects/generate", json=payload)
    assert r.status_code == 200
    projects = r.json()["projects"]
    assert len(projects) == 3
    assert all("id" in p for p in projects)


def test_admin_stats_and_unauthorized_generation():
    s = requests.Session()
    assert s.post(f"{BASE_URL}/api/auth/login", json=ADMIN).status_code == 200
    r = s.get(f"{BASE_URL}/api/admin/stats")
    assert r.status_code == 200 and {"users", "projects", "saved"}.issubset(r.json())
    s.post(f"{BASE_URL}/api/auth/logout")
    assert s.post(f"{BASE_URL}/api/projects/generate", json={}).status_code == 401