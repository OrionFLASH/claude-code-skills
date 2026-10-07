# Самопроверка site-qa-audit

| Файл | Что проверяет | Как запускать |
|------|---------------|---------------|
| `unit.sh` | скрипты без сети и браузера: url_guard selftest, miniyaml, fingerprint, render_draft, read_templates parse, validate | `tests/unit.sh` |
| `dry-run-todomvc.md` | полный прогон скила в dry-run на публичном демо-стенде | попросить Claude: «выполни tests/dry-run-todomvc.md» |
| `fixtures/` | входные данные для unit.sh | — |

Перед релизом: `tests/unit.sh` без ошибок + dry-run по сценарию с проверкой ожидаемых результатов.
