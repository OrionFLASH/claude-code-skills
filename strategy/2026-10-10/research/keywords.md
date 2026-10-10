# Спрос по поисковым запросам: claude-code-skills

Дата: 2026-10-10. Запросов: 82 (en 52, ru 30), кластеров: 12. Объёмов нет: `volume: null` у всех [факт: экспорта владельца нет, вход в Вордстат/GSC не выполнялся]. Конкуренция (`competition` 1–5) — `[оценка: по составу результатов поиска 2026-10-10; страницы не открывались]`: 5 — официальные доки, крупные awesome-списки и каталоги; 1 — выдача почти без точных ответов. У запросов без точной проверки оценка косвенная (по аналогии с кластером). Запросы без внутренних имён и кода продукта.

## Кластеры
| Кластер | Запросов | Намерение | Примеры | Ср. конкуренция | Страница у нас |
|---|---|---|---|---|---|
| Каталоги и маркетплейсы плагинов | 12 | navigational | claude code plugin marketplace; плагины claude code | 3.9 | README/INSTALL (без оптимизации) |
| Что такое скилы и как писать | 11 | informational | what are claude code skills; как создать скилл для claude code | 3.5 | нет |
| QA сайта и веб-тесты через агента | 9 | commercial | claude code QA skill; QA сайта с помощью ИИ | 3.6 | README site-qa-audit |
| Доступность a11y и WCAG с ИИ | 6 | informational | AI accessibility audit playwright | 3.8 | нет |
| Производительность и SEO-аудит агентом | 5 | commercial | claude code lighthouse audit | 3.0 | нет |
| Черновики issues из находок QA | 4 | informational | claude code create github issues from audit | 2.5 | нет |
| Android QA через adb и эмулятор | 7 | commercial | android QA agent adb emulator | 2.7 | README android-qa-audit |
| Выбор модели и effort | 10 | informational | claude subagent model effort; какую модель claude выбрать для кода | 3.7 | README typesafe-triage |
| Хуки и автоматизация Claude Code | 3 | informational | claude code hooks UserPromptSubmit | 2.7 | нет |
| Стратегия продукта по репозиторию | 7 | informational | AI product strategy from repo | 2.9 | README product-strategy |
| Продвижение open source и devtool | 4 | informational | как продвигать open source проект | 4.0 | нет |
| Альтернативы и сравнения | 4 | commercial | claude code skills vs cursor rules | 3.0 | нет |

## Топ-возможности (соответствие продукту × слабая выдача; спрос неизвестен)
1. **Android QA через adb/эмулятор** (en и ru): выдача — MCP-серверы и мелкие скилы, русскоязычных точных ответов почти нет [оценка: 3 и 1–3].
2. **Выбор модели и effort для субагентов** (`claude subagent model effort`, `CLAUDE_CODE_SUBAGENT_MODEL`): выдача — заметки и доки, при этом про effort пишут мало (HumanLayer прямо отмечает, что `inherit` effort не задаёт); у typesafe-triage уникальный угол.
3. **Стратегия продукта по репозиторию**: найденные скилы работают с вводом пользователя, а не с кодом [источник: SK015]; запрос «AI product strategy from repo» слабо закрыт.
4. **Черновики issues из находок аудита**: узкая тема, конкуренция 2–3, прямое соответствие site-qa-audit.
5. **RU-запросы «скилы/плагины claude code»**: выдача — обзорные статьи Хабра и DataCamp, каталогов с русскоязычным описанием маркетплейса нет [оценка: 2–3]; единственный рынок, где у документации на русском есть преимущество.

## GEO-кандидаты (вопросы, на которые отвечают ассистенты; наблюдалось только по выдаче, ответы ассистентов не снимались)
- how to install claude code plugins / как установить плагин в claude code
- claude code skills vs plugins / чем скилл отличается от плагина claude code
- opus vs sonnet vs haiku for coding; как сэкономить токены claude code
- claude code model routing / claude subagent model effort
- what are claude code skills / agent skills standard

Страница-ответ в формате «вопрос → краткий ответ → команда `/plugin marketplace add OrionFLASH/claude-code-skills`» подходит для первых двух.

## Языковые различия
- en: выдача насыщена каталогами (claudemarketplaces, vibeindex, skills.sh, awesome-списки) и официальными доками; конкурировать по общим запросам нереалистично, узкие (a11y, adb, effort) — реально.
- ru: меньше точных страниц, доминируют Хабр, DTF, DataCamp RU; терминология плавает («скилы», «скиллы», «навыки», «плагины») — нужны все написания; морфология Яндекса.
- Продукт документирован по-русски, поэтому ru-кластеры (30 ru-запросов из 82) — естественное преимущество, но объём рынка неизвестен.

## Что даст экспорт владельца
Яндекс Вордстат (частотность ru-запросов, нужна выгрузка владельца), Яндекс Вебмастер и Google Search Console (реальные запросы после появления сайта/страниц; сейчас у репозитория 36 просмотров за 14 дней [факт: product-understanding.md]), GitHub Traffic (referrers, popular content) — для проверки, откуда приходят. Без них приоритизация идёт только по конкуренции и соответствию.

## Открытые вопросы
- Есть ли у кого-либо реальный спрос: объёмов нет, ранжирование — по оценке.
- Будет ли отдельный сайт/GitHub Pages: без него индексируются только README и GitHub-страницы.
- Какие написания («скилы»/«скиллы») использовать в заголовках.
- Проверить ответы ассистентов по GEO-кандидатам вручную.
