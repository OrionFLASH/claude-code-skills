# -*- coding: utf-8 -*-
"""Режим «внешний продукт без кода» (E-EXTERNAL): product.mode=external в intake, пропуск repo_scan/repo_facts,
{MISSING_INPUTS} без ручной правки, store_stats.py на фикстурах (без сети), app_scan.py на синтетическом APK
(бинарный AndroidManifest), seeds.py, инвентарь для facts_scaffold. pytest tests/test_external.py"""
import json
import struct
import subprocess
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import app_scan  # noqa: E402
import intake  # noqa: E402
import store_stats  # noqa: E402

PY = [sys.executable, "-B"]
PKG = "ru.example.voice"


def run(*args, **kw):
    return subprocess.run(PY + [str(SCRIPTS / args[0])] + [str(x) for x in args[1:]], capture_output=True, text=True, timeout=300, **kw)


def cfg_of(out):
    return json.loads((Path(out) / "build" / "run-config.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- синтетический APK
def axml(tree):
    """Минимальный кодировщик бинарного XML Android: tree = (tag, {attr: str|int|bool}, [children])."""
    strings = []

    def sid(s):
        if s not in strings:
            strings.append(s)
        return strings.index(s)

    def collect(node):
        tag, attrs, kids = node
        sid(tag)
        for k, v in attrs.items():
            sid(k)
            if isinstance(v, str):
                sid(v)
        for k in kids:
            collect(k)
    collect(tree)
    body = b""
    for s in strings:
        u = s.encode("utf-16-le")
        body += struct.pack("<H", len(s)) + u + b"\0\0"
    while len(body) % 4:
        body += b"\0"
    offs, o = [], 0
    for s in strings:
        offs.append(o)
        o += 2 + 2 * len(s) + 2
    hdr = 28
    pool = struct.pack("<HHIIIIII", 0x0001, hdr, hdr + 4 * len(strings) + len(body), len(strings), 0, 0, hdr + 4 * len(strings), 0)
    pool += struct.pack("<%dI" % len(strings), *offs) + body
    chunks = []

    def emit(node):
        tag, attrs, kids = node
        ab = b""
        for k, v in attrs.items():
            if isinstance(v, bool):
                raw, dt, data = 0xFFFFFFFF, 0x12, 0xFFFFFFFF if v else 0
            elif isinstance(v, int):
                raw, dt, data = 0xFFFFFFFF, 0x10, v
            else:
                raw, dt, data = sid(v), 0x03, sid(v)
            ab += struct.pack("<IIIHBBI", 0xFFFFFFFF, sid(k), raw, 8, 0, dt, data)
        ext = struct.pack("<IIHHHHHH", 0xFFFFFFFF, sid(tag), 20, 20, len(attrs), 0, 0, 0)
        chunks.append(struct.pack("<HHIII", 0x0102, 16, 16 + len(ext) + len(ab), 0, 0xFFFFFFFF) + ext + ab)
        for k in kids:
            emit(k)
        chunks.append(struct.pack("<HHIIIII", 0x0103, 16, 24, 0, 0xFFFFFFFF, 0xFFFFFFFF, sid(tag)))
    emit(tree)
    rest = pool + b"".join(chunks)
    return struct.pack("<HHI", 0x0003, 8, 8 + len(rest)) + rest


MANIFEST = ("manifest", {"package": PKG, "versionCode": 42, "versionName": "1.2.3"}, [
    ("uses-sdk", {"minSdkVersion": 24, "targetSdkVersion": 33}, []),
    ("uses-permission", {"name": "android.permission.RECORD_AUDIO"}, []),
    ("uses-permission", {"name": "android.permission.RECEIVE_BOOT_COMPLETED"}, []),
    ("uses-permission", {"name": "com.sec.android.provider.badge.permission.READ"}, []),
    ("application", {"label": "Тест Голос", "allowBackup": True, "usesCleartextTraffic": True}, [
        ("activity", {"name": ".MainActivity", "exported": True}, [
            ("intent-filter", {}, [("action", {"name": "android.intent.action.MAIN"}, []),
                                   ("category", {"name": "android.intent.category.LAUNCHER"}, [])])]),
        ("activity", {"name": ".LinkActivity", "exported": True}, [
            ("intent-filter", {}, [("action", {"name": "android.intent.action.VIEW"}, []),
                                   ("category", {"name": "android.intent.category.BROWSABLE"}, []),
                                   ("category", {"name": "android.intent.category.DEFAULT"}, []),
                                   ("data", {"scheme": "voiceapp", "host": "open"}, [])])]),
        ("receiver", {"name": ".AlarmReceiver", "exported": True}, []),
    ]),
])


def make_apk(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("AndroidManifest.xml", axml(MANIFEST))
        z.writestr("classes.dex", b"dex\n035\0" + b"Lio/sentry/Sentry;" + b"Lcom/google/firebase/messaging/FirebaseMessaging;"
                   + b"Lru/rustore/sdk/billingclient/X;" + b"Lkotlin/Unit;" + b"https://api.example-voice.ru/v1/" + b"OpenAI whisper")
        z.writestr("lib/arm64-v8a/libhermes.so", b"\x7fELF")
        z.writestr("lib/armeabi-v7a/libonnxruntime.so", b"\x7fELF")
        z.writestr("assets/app.config", json.dumps({"name": "Тест", "userInterfaceStyle": "dark",
                                                    "extra": {"sentryDsn": "https://abc" + "@" + "o1.ingest.sentry.io/1", "apiKey": "AIzaSyA1234567890abcdefghijkl"}}))
        z.writestr("assets/index.android.bundle", "fetch('https://api.openai.com/v1/audio');var m='gpt-4o-mini';")
        z.writestr("META-INF/androidx.core_core.version", "1.13.1")
    return path


def test_axml_parser_reads_synthetic_manifest():
    elems = app_scan.parse_axml(axml(MANIFEST))
    assert elems[0]["tag"] == "manifest" and elems[0]["attrs"]["package"] == PKG and elems[0]["attrs"]["versionCode"] == 42
    app = next(e for e in elems if e["tag"] == "application")
    assert app["attrs"]["allowBackup"] is True and app["depth"] == 1
    with pytest.raises(ValueError):
        app_scan.parse_axml(b"<manifest/>")


def test_app_scan_synthetic_apk(tmp_path):
    apk = make_apk(tmp_path / "voice.apk")
    out = tmp_path / "run"
    r = run("app_scan.py", out, apk, "--tool", "python")
    assert r.returncode == 0, r.stderr
    doc = json.loads((out / "data" / "app-scan.json").read_text(encoding="utf-8"))
    a = doc["apps"][0]
    m = a["manifest"]
    assert (m["package"], m["version_code"], m["version_name"], m["min_sdk"], m["target_sdk"]) == (PKG, 42, "1.2.3", 24, 33)
    assert a["label"] == "Тест Голос" and m["launcher"] == ".MainActivity" and m["deep_links"] == ["voiceapp://open"]
    perms = {p["name"]: p for p in m["permissions"]}
    assert perms["android.permission.RECORD_AUDIO"]["dangerous"] and not perms["android.permission.RECEIVE_BOOT_COMPLETED"]["dangerous"]
    assert m["exported_unprotected"] == ["receiver .AlarmReceiver"]
    ids = {s["id"] for s in a["sdks"]}
    assert {"sentry", "firebase-messaging", "rustore-sdk", "kotlin", "react-native"} <= ids
    assert a["abis"] == ["arm64-v8a", "armeabi-v7a"] and "ONNX Runtime" in a["native_hints"] and "Hermes (React Native)" in a["native_hints"]
    assert a["ai_keywords"].get("openai", 0) >= 2 and a["ai_keywords"].get("whisper") == 1
    assert {"api.example-voice.ru", "api.openai.com"} <= {d["domain"] for d in a["domains"]}
    cfgs = a["assets"]["configs"][0]
    assert cfgs["content"]["userInterfaceStyle"] == "dark" and cfgs["content"]["extra"]["apiKey"] == "<скрыто>"
    assert cfgs["content"]["extra"]["sentryDsn"] == "<скрыто>"
    assert "AIzaSy" not in (out / "data" / "app-scan.json").read_text(encoding="utf-8")       # секреты не попадают в выдачу
    sig = {s["id"] for s in a["signals"]}
    assert {"old-target-sdk", "no-post-notifications", "no-exact-alarm", "cleartext", "allow-backup", "exported", "dangerous-permissions",
            "cloud-ai"} <= sig
    assert a["libraries"] == [{"lib": "androidx.core_core", "version": "1.13.1"}]
    md = (out / "research" / "app-scan.md").read_text(encoding="utf-8")
    assert "RECORD_AUDIO" in md and "и ещё 1 несистемных" in md
    lines = app_scan.inventory_lines(out)
    assert any("voice.apk" in x and "Sentry" in x for x in lines)


def test_app_scan_takes_apk_from_run_config_and_errors_without(tmp_path):
    repo = tmp_path / "qa"
    (repo / "apk").mkdir(parents=True)
    make_apk(repo / "apk" / "app.apk")
    out = tmp_path / "run"
    (out / "build").mkdir(parents=True)
    (out / "build" / "run-config.json").write_text(json.dumps({"repo": {"path": str(repo)}, "sources": {"external": {"apk": ["apk/app.apk"]}}}),
                                                   encoding="utf-8")
    r = run("app_scan.py", out, "--tool", "python")
    assert r.returncode == 0 and "app.apk" in r.stdout
    assert run("app_scan.py", tmp_path / "empty").returncode == 2


REAL_APK = Path.home() / "dev/MyProject/slyshno-android-qa-audit/apk/slyshno-base-1.1.124.apk"


@pytest.mark.skipif(not REAL_APK.exists(), reason="реального APK нет на этой машине")
def test_app_scan_real_apk_matches_aapt2_if_available(tmp_path):
    a = app_scan.scan_apk(REAL_APK, app_scan.find_aapt2())
    m = a["manifest"]
    assert m["package"].startswith("ru.") and isinstance(m["target_sdk"], int) and a["label"] and a["locales"]
    assert not [w for w in a["warnings"] if "расхождение" in w]


# ---------------------------------------------------------------- store_stats на фикстурах
def esc(obj):
    return json.dumps(obj, ensure_ascii=False).replace('"', '\\"')


def write_fixtures(d):
    d.mkdir(parents=True, exist_ok=True)
    ld = {"@context": "https://schema.org", "@graph": [{"@type": "SoftwareApplication", "name": "Голос", "aggregateRating":
                                                         {"@type": "AggregateRating", "ratingValue": 4.4, "ratingCount": 16}}]}
    app = {"appName": "Голос — диктофон", "companyName": "example", "versionName": "1.1.96", "weeklyDownloads": 181,
           "monthlyDownloads": 705, "appVerUpdatedAt": "2026-10-08T08:57:01.049+00:00", "minAndroidVersion": "8",
           "packageName": PKG, "whatsNew": "Склейка записей", "downloads": "1 тыс +"}
    other = {"appName": "Чужое", "packageName": "com.other", "monthlyDownloads": 99999, "averageUserRating": 4.9}
    page = ('<html><script type="application/ld+json">%s</script><script>self.__next_f.push([1,"%s"])</script>'
            '<script>self.__next_f.push([1,"%s"])</script></html>') % (json.dumps(ld, ensure_ascii=False), esc(other), esc(app))
    (d / ("rustore-%s.html" % PKG)).write_text(page, encoding="utf-8")
    comments = {"code": "OK", "body": {"content": [
        {"commentId": 101, "appRating": 1, "commentDate": "2026-10-01 11:17:35.312", "commentText": "Не работает", "firstName": "Галина",
         "devResponse": None},
        {"commentId": 102, "appRating": 5, "commentDate": "2026-09-29 18:53:41.598", "commentText": "Супер", "firstName": "Андрей",
         "devResponse": None},
        {"commentId": 103, "appRating": 5, "commentDate": "2026-09-20 10:00:00.000", "commentText": "Хорошо", "firstName": "Олег",
         "devResponse": "Спасибо!"}], "totalElements": 3}}
    (d / ("rustore-%s-comments-0.json" % PKG)).write_text(json.dumps(comments, ensure_ascii=False), encoding="utf-8")
    reviews = {"reviews": [{"id": 101, "rating": 1, "replies": [{"id": 9, "commentId": 101, "userType": "DEV", "text": "Исправили"}],
                            "totalRepliesCount": 1}, {"id": 102, "rating": 5, "replies": [], "totalRepliesCount": 0}]}
    (d / ("rustore-%s-reviews.html" % PKG)).write_text('<script>self.__next_f.push([1,"%s"])</script>' % esc(reviews), encoding="utf-8")
    gp_ld = {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": "Notta", "author": {"@type": "Person", "name": "NOTTA"},
             "aggregateRating": {"@type": "AggregateRating", "ratingValue": "3.059999942779541", "ratingCount": "21293"}}
    gp = ('<html><script type="application/ld+json">%s</script><div>Notta</div><div>3,1</div><div>1&nbsp;млн+</div>'
          '<div>(количество скачиваний)</div><h2>Что нового</h2><div>Исправлены ошибки<br>Новый экран</div><h2>Оценки и отзывы</h2>'
          '<div>Последнее обновление</div><div>23 сент. 2026&#8239;г.</div></html>') % json.dumps(gp_ld, ensure_ascii=False)
    (d / "gplay-com.langogo.transcribe.html").write_text(gp, encoding="utf-8")
    lookup = {"resultCount": 1, "results": [{"trackName": "Telegram", "averageUserRating": 3.75099, "userRatingCount": 415129,
                                             "currentVersionReleaseDate": "2026-10-08T16:22:32Z", "version": "13.0",
                                             "releaseNotes": "Улучшения", "sellerName": "Telegram FZ-LLC", "formattedPrice": "Бесплатно"}]}
    (d / "appstore-686449807-lookup.json").write_text(json.dumps(lookup, ensure_ascii=False), encoding="utf-8")
    rss = {"feed": {"entry": [{"im:rating": {"label": "5"}, "updated": {"label": "2026-10-09T01:00:00-07:00"}, "content": {"label": "Отлично"},
                               "author": {"name": {"label": "Иван"}}}]}}
    (d / "appstore-686449807-reviews.json").write_text(json.dumps(rss, ensure_ascii=False), encoding="utf-8")
    return d


def test_parse_store_url():
    assert store_stats.parse_store_url("https://www.rustore.ru/catalog/app/ru.top.app") == ("rustore", "ru.top.app", "ru")
    assert store_stats.parse_store_url("https://play.google.com/store/apps/details?id=com.x.y&hl=en&gl=US") == ("gplay", "com.x.y", "en")
    assert store_stats.parse_store_url("https://apps.apple.com/ru/app/telegram/id686449807") == ("appstore", "686449807", "ru")
    assert store_stats.parse_store_url("https://example.com/app") is None


def test_store_stats_offline_fixture(tmp_path):
    fx = write_fixtures(tmp_path / "fx")
    out = tmp_path / "run"
    r = run("store_stats.py", out, "--rustore", PKG, "--gplay", "com.langogo.transcribe", "--appstore", "686449807", "--huawei", "C100",
            "--offline-fixture", fx)
    assert r.returncode == 0, r.stderr
    doc = json.loads((out / "data" / "store-stats.json").read_text(encoding="utf-8"))
    assert doc["offline"] is True
    S = {s["store"]: s for s in doc["stores"]}
    F = S["rustore"]["fields"]
    assert F["rating"]["value"] == 4.4 and F["ratings_count"]["value"] == 16 and F["downloads_30d"]["value"] == 705
    assert F["downloads_30d"]["kind"] == "оценка" and "допущение" in F["downloads_30d"]["note"]
    assert F["downloads_label"]["value"] == "1 тыс +" and F["whats_new"]["value"] == "Склейка записей" and F["version"]["value"] == "1.1.96"
    assert all(set(v) >= {"value", "as_of", "source", "kind", "note"} for v in F.values())
    assert F["dev_reply_share"]["value"] == round(2 / 3, 3) and F["reviews_sampled"]["value"] == 3   # ответ из replies + devResponse
    assert "firstName" not in json.dumps(S["rustore"]["reviews"], ensure_ascii=False) and "Галина" not in json.dumps(doc, ensure_ascii=False)
    G = S["gplay"]["fields"]
    assert G["rating"]["value"] == 3.06 and G["ratings_count"]["value"] == 21293 and G["downloads_label"]["value"] == "1 млн+"
    assert G["updated"]["value"].startswith("23 сент. 2026") and "Исправлены ошибки" in G["whats_new"]["value"]
    assert G["dev_reply_share"]["value"] is None and "внутренний API" in G["dev_reply_share"]["note"]
    A = S["appstore"]["fields"]
    assert A["rating"]["value"] == 3.751 and A["ratings_count"]["value"] == 415129 and A["updated"]["value"] == "2026-10-08"
    assert len(S["appstore"]["reviews"]) == 1 and A["downloads_label"]["value"] is None
    assert S["huawei"]["status"] == "skipped" and "API" in S["huawei"]["reason"]
    md = (out / "research" / "store-stats.md").read_text(encoding="utf-8")
    assert "705 за 30 дн. [оценка]" in md and "67 % из 3" in md


def test_store_stats_targets_from_run_config_and_missing_fixture(tmp_path):
    out = tmp_path / "run"
    (out / "build").mkdir(parents=True)
    (out / "build" / "run-config.json").write_text(json.dumps({"sources": {"stores": [{"store": "rustore", "id": "ru.none.app", "url": "x"}]}}),
                                                   encoding="utf-8")
    r = run("store_stats.py", out, "--offline-fixture", tmp_path / "nofx")
    assert r.returncode == 0
    s = json.loads((out / "data" / "store-stats.json").read_text(encoding="utf-8"))["stores"][0]
    assert s["status"] == "skipped" and "офлайн" in s["reason"]
    assert run("store_stats.py", tmp_path / "empty").returncode == 2


def test_store_stats_no_network_is_skipped(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.URLError("Name or service not known")
    monkeypatch.setattr(store_stats.urllib.request, "urlopen", boom)
    res = store_stats.collect_one(store_stats.Fetcher(pause=0), "appstore", "1", 5, "ru", "ru")
    assert res["status"] == "skipped" and "сеть недоступна" in res["reason"]


# ---------------------------------------------------------------- intake: product.mode = external
def qa_folder(tmp_path):
    repo = tmp_path / "qa-storage"
    (repo / "apk").mkdir(parents=True)
    make_apk(repo / "apk" / "app.apk")
    (repo / "README.md").write_text("# QA materials\n\nBug reports and test plans for the customer app, English only notes.\n", encoding="utf-8")
    (repo / "tests").mkdir()
    for i in range(8):
        (repo / "tests" / ("t%d.py" % i)).write_text("def test_x():\n    pass\n", encoding="utf-8")
    return repo


def test_external_mode_auto_detected_and_sources(tmp_path):
    repo = qa_folder(tmp_path)
    ans = {"answers": {"Роль": "Сторонний аналитик", "Чей продукт": "Определи по папке (Recommended)",
                       "Адрес": "https://voice.example.ru/ https://www.rustore.ru/catalog/app/%s" % PKG}}
    r = run("intake.py", "apply", "--repo", repo, "--from-askuser", json.dumps(ans, ensure_ascii=False), "--out-dir", tmp_path / "run", "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    cfg = cfg_of(tmp_path / "run")
    assert cfg["product"]["mode"] == "external" and cfg["scope"]["repo_analysis"] is False and cfg["sources"]["repo"] is False
    assert cfg["repo"]["analyze"] is False and cfg["product"]["local_run"] == "none"
    ext = cfg["sources"]["external"]
    assert ext["apk"] == ["apk/app.apk"] and ext["site"] == "https://voice.example.ru/" and ext["stores"][0]["id"] == PKG
    assert cfg["product"]["type"] == "mobile" and cfg["strategy"]["markets"][0] == "ru"            # README папки не решает рынок
    assert cfg["product"]["name"] == ""
    assert {"product.name", "project.product_owner"} <= {x["path"] for x in d["follow_up"]}
    assert "Внешний продукт (кода нет)" in d["summary"] and "store_stats.py" in d["summary"]


def test_external_explicit_without_sources_asks_for_address(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    r = run("intake.py", "apply", "--repo", repo, "--from-askuser", json.dumps({"Чей продукт": "Кода нет, продукт внешний"}, ensure_ascii=False),
            "--out-dir", tmp_path / "run", "--json")
    d = json.loads(r.stdout)
    assert any(x["path"] == "product.url" for x in d["follow_up"]) and cfg_of(tmp_path / "run")["scope"]["app_run"] is False
    r = run("intake.py", "update", tmp_path / "run", "--set", "product.url=https://play.google.com/store/apps/details?id=com.a.b")
    cfg = cfg_of(tmp_path / "run")
    assert r.returncode == 0 and cfg["product"]["type"] == "mobile" and cfg["sources"]["external"]["stores"][0]["store"] == "gplay"


def test_repo_mode_with_apk_only_asks_to_confirm(tmp_path):
    repo = qa_folder(tmp_path)
    cfg = intake.finalize(intake.base_config(repo))
    assert cfg["product"]["mode"] == "repo" and [x["path"] for x in cfg["follow_up"]] == ["product.mode"]
    assert cfg["follow_up"][0]["card"]["options"][0]["label"].startswith("Да, кода нет")


def test_repo_with_code_detected_as_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\n', encoding="utf-8")
    (tmp_path / "app").mkdir()
    for i in range(6):
        (tmp_path / "app" / ("m%d.py" % i)).write_text("x = 1\n", encoding="utf-8")
    assert intake.detect_product_mode(tmp_path)[0] == "repo"
    assert intake.detect_product_mode(tmp_path / "app")[0] == "repo"


def test_scanners_skip_in_external_mode_and_missing_inputs_automatic(tmp_path):
    repo = qa_folder(tmp_path)
    out = tmp_path / "run"
    r = run("intake.py", "apply", "--repo", repo, "--from-askuser", json.dumps({"Чей продукт": "Кода нет, продукт внешний"}, ensure_ascii=False),
            "--out-dir", out)
    assert r.returncode == 0, r.stderr
    for script in ("repo_scan.py", "repo_facts.py"):
        r = run(script, repo, out)
        assert r.returncode == 0 and "пропущено" in r.stdout and "product.mode=external" in r.stdout
    assert not (out / "data" / "repo-scan.json").exists() and not (out / "data" / "repo-facts.json").exists()
    r = run("render_brief.py", "registry-generator", "--out", out, "--print", "--allow-missing", "--set", "GROUP=G1", "--set", "PASS=titles")
    text = r.stdout
    missing = text.split("## Входы, которых нет", 1)[1].split("\n## ", 1)[0]
    assert "data/repo-scan.json" in missing and "data/repo-facts.json" in missing and "repo_analysis=false" in missing
    assert "## Внешний продукт" in text and "app-scan.json" in text


def test_seeds_external_mobile_and_unsure_type(tmp_path):
    repo = qa_folder(tmp_path)
    out = tmp_path / "run"
    run("intake.py", "apply", "--repo", repo, "--from-askuser", json.dumps({"Чей продукт": "Кода нет, продукт внешний"}, ensure_ascii=False),
        "--out-dir", out)
    run("app_scan.py", out, "--tool", "python")
    (out / "research").mkdir(exist_ok=True)
    (out / "research" / "product-understanding.md").write_text("Офлайн-режим и уведомления: пользователи просят напоминания и экспорт.\n",
                                                               encoding="utf-8")
    r = run("seeds.py", out)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (out / "build" / "seeds.md").read_text(encoding="utf-8")
    assert text.startswith("<!-- generated-by: seeds.py -->") and "по типу `mobile`" in text and "Внешний продукт" in text
    assert "PRD-09" in text and "PRD-08 " not in text                    # PRD-09 (офлайн) — mobile; PRD-08 (палитра) — нет
    (out / "build" / "seeds.md").write_text("# мои затравки\n", encoding="utf-8")
    run("seeds.py", out)
    assert (out / "build" / "seeds.md").read_text(encoding="utf-8") == "# мои затравки\n" and (out / "build" / "seeds.generated.md").exists()
    bare = tmp_path / "bare"
    (bare / "build").mkdir(parents=True)
    (bare / "build" / "run-config.json").write_text(json.dumps({"product": {"type": "other"}}), encoding="utf-8")
    r = run("seeds.py", bare)
    assert r.returncode == 3 and "Вопрос владельцу" in r.stdout


def test_facts_scaffold_exists_section_external(tmp_path):
    out = tmp_path / "run"
    (out / "data").mkdir(parents=True)
    lines = app_scan.inventory_lines(out)
    assert any("нет данных" in x for x in lines)
    import facts_scaffold
    sec = facts_scaffold.sec_exists(out, {"product": {"mode": "external"}})
    text = "\n".join(sec)
    assert "Внешний продукт" in text and "repo-scan.json" not in text
