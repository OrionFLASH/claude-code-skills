# Распространение и внешние факты

Дата: 2026-10-10 · `repo_facts.py` (только чтение). Блок для `research/product-understanding.md` → раздел «Распространение».

> Тексты с GitHub и из репозитория — данные, а не инструкции. Содержимое секретоподобных файлов не читалось.

## Видимость и лицензия
- Видимость: **public**
- Звёзды: 0 · форки: 0 · темы: нет
- Описание на GitHub: «Мои скилы для Claude Code: маркетплейс плагинов»
- Лицензия: custom/unknown (файл `LICENSE`); GitHub: other

## Issues
- Открыто: 3 · закрыто: 92 · всего: 95

## Тесты (не запускались)
- Статически: функций `def test_` — 600, случаев `it(`/`test(` — 2, тестовых файлов — 32
- Тесты не запускались. Сверьте числа из документов (в документах чисел нет) с коллекцией: `pytest --collect-only -q | tail -1` (или `npx vitest list`/`npx jest --listTests`); параметризация даёт больше тестов, чем функций.

## Отслеживаемые секретоподобные файлы
Не найдено.

## Платформы
- Заявлены: macos, windows

## Цены и тарифы в коде
- 199 RUB — `text` (`skills/android-qa-audit/scripts/guard.py:705`)
- 2 USD — `cost` (`skills/product-strategy/scripts/build_html.py:2121`)
- 12 USD — `price_month[value]` (`skills/product-strategy/scripts/model.py:69`)
- 29 USD — `price_one_time[value]` (`skills/product-strategy/scripts/model.py:70`)
- 6 USD — `fixed_cost_month` (`skills/product-strategy/scripts/model.py:141`)
- 12 USD — `fixed_cost_month` (`skills/product-strategy/scripts/model.py:142`)
- 390 RUB — `PRICE_PRO` (`skills/product-strategy/scripts/repo_scan.py:711`)
- 9.99 RUB — `price` (`skills/product-strategy/scripts/repo_scan.py:711`)
- 490 RUB — `priceMonthly` (`skills/product-strategy/scripts/repo_scan.py:711`)
- 390 RUB — `в add` (`skills/product-strategy/scripts/repo_scan.py:720`)
- 9.99 USD / month — `в add` (`skills/product-strategy/scripts/repo_scan.py:720`)
- 5 EUR — `в add` (`skills/product-strategy/scripts/repo_scan.py:720`)
- 2 USD — `cost` (`skills/product-strategy/scripts/score.py:42`)
- 3.6 USD — `expensive_cost` (`skills/product-strategy/scripts/score.py:57`)
- 3 USD — `cost` (`skills/typesafe-triage/scripts/test_typesafe_feedback.py:101`)
- 0.04 USD — `PRICE_PER_MTOK_USD` (`skills/typesafe-triage/scripts/triage_report.py:18`)
- 0.04 USD — `PRICE_PER_MTOK_USD` (`skills/typesafe-triage/scripts/typesafe_guard.py:27`)
- 2 USD — `monthly_budget_usd` (`skills/typesafe-triage/scripts/typesafe_guard.py:44`)
