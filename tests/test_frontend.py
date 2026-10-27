import json
import re
import struct

import pytest
from fastapi.testclient import TestClient

from app.config import BASE_DIR
from app.main import app

STATIC = BASE_DIR / "static"


@pytest.fixture(scope="module")
def web():
    return TestClient(app)


def png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_index_is_served_at_root(web):
    response = web.get("/")
    assert response.status_code == 200
    assert 'rel="manifest"' in response.text
    assert 'type="module" src="/js/app.js"' in response.text
    assert "<script>" not in response.text


def test_index_has_bottom_navigation_container(web):
    html = web.get("/").text
    assert '<nav id="nav"' in html and 'aria-label="Разделы"' in html


def test_api_routes_are_not_shadowed_by_static_files(web):
    assert web.get("/health").json() == {"status": "ok"}
    assert web.get("/docs").status_code == 200
    assert web.get("/session/next").status_code == 401
    assert web.get("/auth/me").status_code == 401


def test_manifest_is_installable():
    manifest = json.loads((STATIC / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/" and manifest["scope"] == "/"
    assert manifest["name"] and manifest["short_name"]
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon["purpose"] == "maskable" for icon in manifest["icons"])
    for icon in manifest["icons"]:
        width, height = png_size(STATIC / icon["src"].lstrip("/"))
        assert f"{width}x{height}" == icon["sizes"]


def test_manifest_is_served(web):
    response = web.get("/manifest.json")
    assert response.status_code == 200
    assert response.json()["name"]


def test_service_worker_is_served_from_root_scope(web):
    response = web.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_service_worker_precaches_existing_files_only():
    source = (STATIC / "sw.js").read_text(encoding="utf-8")
    shell = re.search(r"const SHELL = \[(.*?)\];", source, re.DOTALL).group(1)
    paths = re.findall(r'"(/[^"]*)"', shell)
    assert "/" in paths and "/js/app.js" in paths
    for path in paths:
        target = STATIC / "index.html" if path == "/" else STATIC / path.lstrip("/")
        assert target.is_file(), path


def test_service_worker_never_caches_api():
    source = (STATIC / "sw.js").read_text(encoding="utf-8")
    for api_path in ("/auth", "/session", "/admin/cards"):
        assert f'"{api_path}' not in source


def test_every_local_reference_in_index_exists():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for path in re.findall(r'(?:href|src)="(/[^"]+)"', html):
        assert (STATIC / path.lstrip("/")).is_file(), path


def test_shell_files_are_precached():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    source = (STATIC / "sw.js").read_text(encoding="utf-8")
    for path in re.findall(r'(?:href|src)="(/[^"]+)"', html):
        assert f'"{path}"' in source, path


def test_js_imports_resolve_and_shell_modules_are_precached():
    source = (STATIC / "sw.js").read_text(encoding="utf-8")
    for module in (STATIC / "js").rglob("*.js"):
        text = module.read_text(encoding="utf-8")
        if module.parent == STATIC / "js":
            assert f'"/js/{module.name}"' in source, module.name
            assert "teacher/" not in " ".join(re.findall(r'from "([^"]+)"', text)), module.name
        for imported in re.findall(r'from "(\.{1,2}/[^"]+)"', text):
            assert (module.parent / imported).resolve().is_file(), f"{module.name}: {imported}"


def test_teacher_page_is_served_and_references_exist(web):
    assert web.get("/teacher.html").status_code == 200
    html = (STATIC / "teacher.html").read_text(encoding="utf-8")
    assert "<script>" not in html
    for path in re.findall(r'(?:href|src)="(/[^"]+)"', html):
        assert (STATIC / path.lstrip("/")).is_file(), path


def test_frontend_never_writes_html_from_data():
    for module in (STATIC / "js").rglob("*.js"):
        text = module.read_text(encoding="utf-8")
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            assert forbidden not in text, f"{module.name}: {forbidden}"
