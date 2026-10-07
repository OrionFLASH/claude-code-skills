# Журнал изменений

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/). Версии отдельных скилов — в их собственных `CHANGELOG.md`.

## [Unreleased]

## 2026-10-07
### Добавлено
- Скил `site-qa-audit` 1.0.0 → 1.0.1 (dry-run на демо-стенде, исправления guard и черновиков).
- `shared/scripts`: `miniyaml.py` (подмножество YAML на stdlib), `envcheck.py`; вендоринг общих модулей в скилы через `.shared` (`tools/validate.sh --fix`).
- Каркас репозитория: README, CONVENTIONS, маркетплейс, `shared/`, `tools/` (install, new-skill, validate).
