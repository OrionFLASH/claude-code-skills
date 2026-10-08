# Самопроверка site-qa-audit

| Файл | Что проверяет | Как запускать |
|------|---------------|---------------|
| `unit.sh` | скрипты без сети: url_guard selftest, miniyaml, fingerprint, render_draft, read_templates parse, validate, синтаксис всех новых скриптов; вызывает наборы A, v1.2, B, C (B и C — SKIP без node/playwright/Chromium или при `QA_SKIP_BROWSER=1`) | `tests/unit.sh` |
| `test_stream_a.sh` | claims, схема 1.1.0, render_draft (disclosure, ссылки, маркер), intake from-text, journal, build_report, read_templates fetch, check_env — без сети | `tests/test_stream_a.sh`; реальные данные — только через `REAL_REGISTRY=… REAL_FINDINGS=…` |
| `test_v12.sh` | 1.2.0: `gitignore_helper.py` (временные git-репозитории, изолированный HOME), `intake.py` — `parallel.max_workers` не больше 4, разделы `goal`/`context`/`report_destinations` в run-config, `build_report.py summary`, шаблон `site-context.md` — без сети | `tests/test_v12.sh` (git-часть — SKIP без git) |
| `test_stream_b.sh` + `stream_b.test.js` | браузерные: guard, invariants, occlusion, reachability, device_context, shot, frames на `fixtures/*.html` через `python3 -m http.server` | `tests/test_stream_b.sh [фильтр-регэксп]` |
| `test_stream_c.sh` | web-upload (`publish_web.mjs`, `comment_web.mjs`) на имитации интерфейса GitHub, headless Chromium по CDP, `helpers/fake_gh.py` вместо gh | `tests/test_stream_c.sh` (порты `QA_TEST_HTTP_PORT`, `QA_TEST_CDP_PORT`) |
| `dry-run-todomvc.md` | полный прогон скила в dry-run на публичном демо-стенде | попросить Claude: «выполни tests/dry-run-todomvc.md» |
| `fixtures/`, `helpers/` | обезличенные входные данные и локальные HTML-фикстуры; вспомогательные заглушки | — |

Перед релизом: `tests/unit.sh` без ошибок + dry-run по сценарию с проверкой ожидаемых результатов.
