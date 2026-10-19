"""FB-038: check_flow.mjs падает на блоке схемы без <title> — для блоков, описанных в data/flows.json (label или what), с
--strict-titles — для всех; с <title> в каждом блоке — проходит. Схема на странице всё равно получает <title> из nodes[].what
(build_html.py, см. test_site_interactive.py). Браузер — Chromium из Playwright; без него тест пропускается.
  python3 -m pytest skills/product-strategy/tests/test_site_flow_a11y.py -q
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parent.parent
NODE_DIR = SKILL / "scripts" / "node"
NODE = shutil.which("node")


def pw_dir():
    for d in (os.environ.get("PS_NODE_DIR"), str(NODE_DIR), str(Path.home() / ".cache" / "product-strategy" / "node")):
        if d and (Path(d) / "node_modules" / "playwright" / "package.json").exists():
            return d
    return None


PW = pw_dir()
needs_pw = pytest.mark.skipif(not NODE or not PW, reason="playwright недоступен (PS_NODE_DIR или ~/.cache/product-strategy/node)")


def svg(titles):
    t = lambda k, s: ("<title>%s</title>" % s) if titles else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 160" width="520" height="160" font-family="Arial" font-size="14">'
            '<g data-node="f:1">%s<rect x="20" y="40" width="180" height="50" fill="#eef"/><text x="30" y="70">Первый визит</text></g>'
            '<g data-node="f:2">%s<rect x="320" y="40" width="180" height="50" fill="#efe"/><text x="330" y="70">Активация</text></g></svg>'
            % (t(1, "Первый визит: пользователь пришёл из поиска"), t(2, "Активация: первый результат")))


def run(out, *extra):
    r = subprocess.run([NODE, str(NODE_DIR / "check_flow.mjs"), str(out), "--node-dir", PW] + list(extra), capture_output=True, text=True, timeout=240)
    rep = json.loads((out / "data" / "flows-check.json").read_text(encoding="utf-8"))
    return r, {i["key"]: i for i in rep["items"]}


def write(out, key, titles, described):
    (out / "charts" / "flows").mkdir(parents=True, exist_ok=True)
    (out / "charts" / "flows" / (key + ".svg")).write_text(svg(titles), encoding="utf-8")
    nodes = [{"id": "f:1", "label": "Первый визит", "what": "пользователь пришёл из поиска"}, {"id": "f:2", "label": "Активация"}] if described \
        else [{"id": "f:1"}, {"id": "f:2"}]
    return {"key": key, "title": key, "svg": "charts/flows/%s.svg" % key, "nodes": nodes}


@needs_pw
def test_check_flow_fails_on_described_node_without_title(tmp_path):
    flows = [write(tmp_path, "bare", False, True), write(tmp_path, "titled", True, True), write(tmp_path, "undescribed", False, False)]
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "flows.json").write_text(json.dumps(flows, ensure_ascii=False), encoding="utf-8")
    r, by = run(tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert [p["type"] for p in by["bare"]["problems"]] == ["node_no_title"] and "f:1, f:2" in by["bare"]["problems"][0]["msg"]
    assert by["titled"]["ok"] and by["undescribed"]["ok"]                      # без описания в flows.json — по умолчанию не требуется
    assert "node_no_title 1" in r.stdout
    r, by = run(tmp_path, "--strict-titles", "--only", "undescribed")
    assert r.returncode == 1 and [p["type"] for p in by["undescribed"]["problems"]] == ["node_no_title"]
    r, by = run(tmp_path, "--only", "titled")
    assert r.returncode == 0, r.stdout
