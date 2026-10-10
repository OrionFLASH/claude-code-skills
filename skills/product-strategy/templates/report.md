# Итоговый отчёт: стратегия развития {PRODUCT}

Дата: {DATE} · Автор: {AUTHOR} · Глубина: {DEPTH} · Вид стратегии: {KIND} · Горизонт: {HORIZON} мес. + видение на {VISION} лет
Главный результат: `deliverables/index.html` · Текст стратегии: `research/strategy.md` · Таблица: `deliverables/strategy.xlsx` · Презентация: `deliverables/strategy.pptx`, `deliverables/strategy.pdf`

## 1. Продукт в моём понимании
- Что это, для кого, какую задачу решает (2–4 предложения).
- Как запускал: <локально командой … / публичный адрес … / только по коду> — <успешно / с ограничениями>.
- Что изучил: <N экранов, M путей, K функций в инвентаре, Issues: да/нет>.
- Уверенность выше: <где и почему>. Ниже: <где и почему>.

## 2. Что сделано по фазам и где лежит
| Фаза | Сделано | Файлы |
|---|---|---|
| 0. Подготовка | | `build/env.json`, `TASKS.md`, `build/STATUS.md` |
| 1. Понимание продукта | | `research/product-understanding.md`, `data/repo-scan.json` |
| 2. Приложение | | `research/ui-inventory.md`, `mockups/current/`, `mockups/tokens.css` |
| 3. Тип и адаптация | | `research/product-understanding.md` (раздел «Тип и акценты») |
| 4. Рынок | | `data/competitors.json`, `data/communities.json`, `data/keywords.json`, `data/events.json`, `research/market.md`, `research/legal.md` |
| 5. Реестр | | `data/proposals.json` |
| 6. Оценка | | `data/scores.json`, `data/sensitivity.json`, `data/model.json`, `research/methodology.md` |
| 7. Стратегия | | `research/strategy.md`, `research/specs/`, `research/experiments/`, `data/gantt.json`, `data/kanban.json` |
| 8. Визуал | | `charts/`, `mockups/concepts/`, `design-refs/` |
| 9. Сборка | | `deliverables/` |

## 3. TypeSafe и навыки
- TypeSafe: <применён к N предложениям — `data/typesafe-jev.json` / пропущен: причина>.
- Выбор моделей субагентов: <typesafe-triage --batch / правило по умолчанию>.
- Использованные навыки: <список>. Отсутствовали: <список> — чем заменено.

## 4. Реестр
Всего: **N** предложений (кандидатов до дедупликации: M).

| Категория | Число | Доля |
|---|---|---|
| product | | |
| acquisition | | |
| conversion | | |
| retention | | |
| monetization | | |
| analytics | | |
| partnerships | | |
| localization | | |
| new_lines | | |
| platform | | |

Классы доказательств: A — …, B — …, C — …, D — … (A+B = …%).

### Топ-20
| Ранг | ID | Название | Категория | Класс | Composite | RICE | Приоритет | Квадрант | Горизонт |
|---|---|---|---|---|---|---|---|---|---|

Устойчивость топ-20 к весам: … (`data/sensitivity.json`).

## 5. Ключевые выводы и три главные ставки
1. **Ставка 1:** … (P…, P…) — ожидаемый эффект … [оценка].
2. **Ставка 2:** …
3. **Ставка 3:** …

Ключевые выводы (3–7 пунктов).

## 6. Что не удалось получить
| Что | Почему | Как повлияло |
|---|---|---|

## 7. Вопросы владельцу и запросы данных
1. …
(не больше 10; полный список — `research/questions-owner.md`)

## 8. Что сокращено
- …

## 9. Как продолжить
- Чекпоинты: `build/STATUS.md`; чек-лист: `TASKS.md` (раздел «Где остановился»).
- Пересборка: `python3 <SKILL_DIR>/scripts/build_all.py <OUT>` (подробно — `deliverables/README.md`).
- Следующий шаг: …

## 10. Решения, принятые за владельца (на проверку)
| Решение | Почему так | Как поменять |
|---|---|---|

## 11. Использованные инструменты и токены
| Волна / агент | Модель | Токены | Минуты | Итог |
|---|---|---|---|---|

Инструменты: Python …, Node …, Playwright …, gh …, браузер …. Веб-поиск: использовано … из бюджета ….

## Проверки
| Проверка | Результат |
|---|---|
| `check_registry.py` | |
| `validate_scores.py` | |
| `check_links.py` | живых …, мёртвых …, анти-бот … |
| `smoke_html.mjs` | ошибок консоли …, внешних запросов … |
| Поиск секретов в `<OUT>` | |
| `git status` репозитория вне `<OUT>` | без изменений / … |

## Замечания
- Обращения к ИИ, найденные в данных (цитата < 15 слов, источник): …

© {YEAR} {AUTHOR}
