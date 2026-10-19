# WP-G — тексты для файлов оркестратора (1.5.0)

Пакет G: новые брифы, фаза C8.5 «Рабочий прототип», личный режим и модули в outline. Ниже — готовый текст вставок
в файлы, которые правит оркестратор (`SKILL.md`, `product-concept/SKILL.md`, `references/concept-mode.md`,
`CHANGELOG.md`, `README.md`, `INSTALL.md`, дополнения к `references/phases.md` и `references/orchestration.md` — файлы WP-D).

## 1. `product-concept/SKILL.md` — таблица C1–C9

Заменить строки C4, C7, C8 и добавить C8.5 (после C8):

```
| C4 | Конкуренты и аналоги, сообщества, спрос, события, право; **модули по признакам идеи**: интеграция с платформой (`idea.facets.platform_dependency`), источники данных и лицензии, ИИ в продукте (ИИ не «без ИИ»), референсы владельца (если названы) | брифы `concept-analogs.md`, `research-communities.md`, `research-keywords.md`, `research-events.md`, `research-legal.md` (если чувствительная область), `research-integration.md`, `research-datasources.md`, `research-ai.md`, `research-owner-refs.md`; `merge_sources.py`, `shoot_competitors.mjs`; синтез `research/market.md`. Личный режим (`project.audience` = personal/circle): `research-keywords` и `research-events` не запускаются («явно пропущено, потому что личный режим»), `research-communities` — только источник знаний |
| C7 | Канвасы и SWOT, **модули C7** (наблюдаемость ИИ — `concept-ai-observability.md`, администрирование и эксплуатация — `concept-admin.md`; черновики G9/G10 → `merge_proposals.py --append G9,G10`), план схем `data/flows-plan.json` до авторов, `merge_sources.py` в начале волны авторов и после неё, текст концепции, спеки топ-N, эксперименты (`sample_size.py --add` → `data/experiments.json`), Гант (все месяцы горизонта), Kanban; раздел 1 — последним (`summary_scaffold.py` + бриф `strategy-summary.md`) | `concept-canvas.md`, `concept-ai-observability.md`, `concept-admin.md`, `strategy-section.md` по `concept-outline.md`, `specs.md`, `experiments.md`, `flows.md`, `strategy-summary.md` |
| C8 | Канон демо-данных (`data/demo-canon.json`) до макетов; язык дизайна, макеты (в т. ч. экраны ИИ и админки из модулей C7), референсы | `concept-design.md`, `templates/mockup-kit/`, `shoot_mockups.mjs`, `design-refs.md` |
| C8.5 | **Рабочий прототип** (по желанию владельца или при вычислительном ядре MVP): ядро расчётов с тестами канона, оболочка и реестр режимов, режимы параллельно, регрессия и `HANDOFF.md` — `references/prototype.md` | `prototype-core.md` → `prototype-shell.md` → `prototype-mode.md` × N (`--set MODE_ID=<id> --suffix <id>`) → `prototype-regression.md`; набор `templates/prototype-kit/` |
```

Под таблицей добавить абзац:

```
Личный режим (`project.audience`: `personal` | `circle` | `personal_then_public`, первая карточка опроса «Для кого приложение?»): заголовки и содержание разделов 2–9, 12, 13, 15 — по разделу «Личный режим» `references/concept-outline.md` (build vs buy, стоимость владения, личные KPI, эксперименты N = 1, «Если захочется выпустить наружу»); реестр — категории core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance, personal-analytics; модель — `model.py --profile personal`. Группы черновиков реестра: G1–G6 генераторы, G7 аудит, G8 пробелы макетов, **G9 ИИ (наблюдаемость), G10 администрирование, G11 референсы владельца**.
```

## 2. `references/concept-mode.md`

### 2.1 Таблица «Фазы режима» — строки C4, C7, C8 и новая C8.5
Тот же текст, что в п. 1 (колонки «Фаза | Что в режиме идеи | Команды и брифы»).

### 2.2 Таблица «Плейсхолдеры брифов режима идеи» — добавить строки
```
| `{AUDIENCE}` | все брифы C4–C7, `experiments.md`, `strategy-section.md`, `registry-generator.md`, `gap-audit.md`, модули | `project.audience` (+ `release_outward`), по умолчанию `public` |
| `{REQUEST_QUESTIONS}` | `research-*.md`, `concept-analogs.md`, модули C4 | `idea.request_questions[]` с `kind: research` или «нет» |
| `{PLATFORM}`, `{PLATFORM_URLS}`, `{DATA_NEEDS}`, `{PLATFORM_ACCESS}`, `{COMPETITORS_TOP}` | `research-integration.md` | `idea.facets.platform_*`, `sources.owner_docs`, `data/competitors.json` |
| `{DATA_SOURCES}` | `research-datasources.md` | `idea.facets.data_sources_needed` |
| `{OWNER_REFS}` | `research-owner-refs.md` | `idea.facets.owner_repos`, `sources.owner_docs` (role base/follow/ref) |
| `{AI_ROLE}`, `{AI_WHERE}` | `research-ai.md`, `concept-ai-observability.md`, `research-owner-refs.md`, `prototype-shell.md` | `idea.facets.ai_role` (или `ai`), `ai_where`, `ai_hardware` |
| `{ADMIN_NEEDS}` | `concept-admin.md` | `idea.facets.admin_who`, `admin_settings`, `admin_needed` |
| `{ARCH}` | `specs.md` | `data/plan-baseline.json → architecture`; иначе `integration-options.json` и раздел 11 частей; иначе по режиму |
| `{FLOWS}` | `flows.md` | `data/flows-plan.json` (иначе `--set`) |
| `{PROTO_SCOPE}`, `{PROTO_MODES}`, `{MODE_ID}`, `{STACK}`, `{CANON}` | `prototype-*.md`, модули C7 | `idea.facets.prototype_scope`, `design.modes[]`, `--set MODE_ID`, `idea.facets.stack`, `data/demo-canon.json` |
```
Строка под таблицей: «Значения новых плейсхолдеров считает `scripts/brief_facets.py` (подключён в `render_brief.py`); без данных — безопасный текст «не указано — …», бриф рендерится без `--set` (кроме `MODE_ID` — по умолчанию первый режим).»

### 2.3 Раздел «Что отличается от обычного прогона» — добавить пункты
```
- Личный режим (`project.audience` personal/circle/personal_then_public) — без аудитории, каналов и денег: см. `references/concept-outline.md`, «Личный режим».
- Модули концепции по признакам идеи: интеграция с платформой, источники данных, ИИ в продукте и его наблюдаемость, администрирование, референсы владельца — подразделы раздела 11 и приложения раздела 17 (`concept-outline.md`, «Модули концепции»).
- Необязательная фаза C8.5 «Рабочий прототип» (`references/prototype.md`, набор `templates/prototype-kit/`): числа макетов = числа ядра (канон демо-данных, `prototype/tools/check_canon.py`).
- Правила содержимого 1.5.0: новизна — только гипотеза с протоколом опровержения; канон демо-данных до макетов; приложения-модули вместо упора в лимит слов; выбор модели ИИ — после эталонного эксперимента; «явно пропущено, потому что…».
```

### 2.4 Строка «Нехватка времени» (конец раздела «Фазы»)
Без изменений по порядку; добавить: «прототип C8.5 — только ядро с тестами (`prototype-core.md`)».

## 3. `SKILL.md` (общий) — раздел про брифы / шаблоны
Добавить в перечень шаблонов брифов: `research-integration`, `research-datasources`, `research-ai`, `research-owner-refs`, `concept-ai-observability`, `concept-admin`, `prototype-core`, `prototype-shell`, `prototype-mode`, `prototype-regression`, `strategy-summary`; в перечень справочников — `references/prototype.md`; в перечень шаблонов — `templates/prototype-kit/` (каркас рабочего прототипа). В обычном режиме применимы `research-integration.md` (продукт зависит от чужого API), `research-datasources.md`, `research-ai.md`, `strategy-summary.md` (раздел 1 последним, из плана и плейсхолдеров).

## 4. Дополнения к `references/phases.md` (WP-D) — вставить после описания C8
```
### C8.5. Рабочий прототип (режим идеи, необязательно)
Когда: владелец просил прототип (`idea.facets.prototype_needed`) или MVP с расчётами/правилами/ИИ-разбором (одна карточка «Нужен ли рабочий прототип?»). Порядок волн: `prototype-core` (ядро + тесты канона) → `prototype-shell` (общие файлы) → `prototype-mode` × N параллельно (только свои `mode-<id>.*`) → `prototype-regression` (подключение режимов, смоук Chromium + WebKit, `check_canon.py --core`, `HANDOFF.md`, `data/prototype.json`). Правила и проверки — `references/prototype.md`. Ворота фазы: `node prototype/js/core.test.js`, `node prototype/js/kit.test.js`, `python3 prototype/tools/check_canon.py prototype --core` — код 0.
```
И в описание C7: «до волны авторов — `data/flows-plan.json` (ключи схем) и `merge_sources.py`; после — снова `merge_sources.py` (фрагменты `data/sources-s<часть>.json` от авторов, FB-011); раздел 1 — последним (`summary_scaffold.py` + `strategy-summary.md`, FB-047)».
В описание C5.5: «перед брифом аудитора — `score.py <OUT>` и `gap_audit.py <OUT>`; зависимости от `G7-NN` аудитор пишет прямо в `data/gap-audit-deps.json` — `merge_proposals.py --append G7` переводит их сам».

## 5. Дополнения к `references/orchestration.md` (WP-D)
- Бюджеты веб-поиска новых брифов (зашиты в текст брифов): `research-integration` 35/60, `research-datasources` 40/60, `research-ai` 30/50; `research-owner-refs`, `concept-ai-observability`, `concept-admin`, `prototype-*`, `strategy-summary` — без веб-поиска; авторы разделов — до 5/10 только для руководств к шагам (FB-011).
- Модель по умолчанию: opus — `research-integration`, `research-ai`, `research-owner-refs`, `concept-ai-observability`, `concept-admin`, `prototype-core`, `prototype-shell`, `strategy-summary`; sonnet — `research-datasources`, `prototype-mode`, `prototype-regression`.
- Временные файлы агента — `build/tmp/<имя файла брифа без .md>/` (во всех брифах; совпадает с `check_paths.py`).

## 6. `CHANGELOG.md` — строки для 1.5.0
```
- Новые брифы: `research-integration` (интеграция с внешней платформой: варианты A–E → `data/integration-options.json`, FB-045), `research-datasources` (источники данных, API и лицензии → `research/data-sources.md`), `research-ai` (ИИ в продукте: среда, кандидаты моделей, эталонный эксперимент до рекомендации), `research-owner-refs` (референсы владельца, внутренние доказательства класса не выше C), `concept-ai-observability` и `concept-admin` (модули C7, группы реестра G9/G10), `strategy-summary` (раздел 1 из plan-baseline и плейсхолдеров, FB-047).
- Фаза C8.5 «Рабочий прототип»: брифы `prototype-core/shell/mode/regression`, набор `templates/prototype-kit/` (ядро UMD с тестами канона, реестр режимов `PK.registerMode`, состояние, ИИ на фикстурах со сверкой чисел, смоук Playwright Chromium + WebKit, `tools/check_canon.py`: числа макетов = числа канона = числа ядра, «график ↔ подпись»), справочник `references/prototype.md`.
- Личный режим (`project.audience`: personal | circle | personal_then_public) в `concept-outline.md` и брифах: разделы 2–9, 12, 13, 15 с личными заголовками, build vs buy, стоимость владения, личные KPI, эксперименты N = 1, «Если захочется выпустить наружу»; личные категории реестра.
- Брифы: `specs` — архитектура `{ARCH}` из `plan-baseline.json`, без «будет в фазе 8» (FB-010); `experiments` — `data/experiments.json` через `sample_size.py --add`, плейсхолдеры `{exp:…}` (FB-010); `strategy-section` — источники авторов `data/sources-s<часть>.json` (FB-011), ключи схем из `flows-plan.json` (FB-006), выдача по номеру раздела без условий по подстроке, Гант на все месяцы горизонта, приложения-модули вместо упора в лимит слов; `flows` — ключи из плана, слияние частей скриптом; `gap-audit` — зависимости от G7 прямо в `gap-audit-deps.json`; во всех брифах — временные файлы только в `build/tmp/<бриф>/` (FB-006); `{AUDIENCE}` и `{REQUEST_QUESTIONS}` в исследованиях; «явно пропущено, потому что…».
- `scripts/brief_facets.py`: значения новых плейсхолдеров из `idea.facets`, `project.audience`, `data/*` (подключён в `render_brief.py`).
- Правила содержимого концепции: новизна — только `[допущение: гипотеза новизны]` с протоколом опровержения; канон демо-данных до макетов; выбор модели ИИ — после эталонного эксперимента; вопросы владельцу ≤ 10 + остальные списком.
```

## 7. `README.md` / `INSTALL.md`
- README, раздел режима идеи: одна строка «Рабочий прототип (C8.5): статический HTML+JS по `file://` с ядром расчётов и тестами, режимами интерфейса и смоуком — по желанию владельца»; одна строка «Личный режим: концепция инструмента для себя — без аудитории и денег, со стоимостью владения и build vs buy».
- INSTALL: для смоука прототипа нужен тот же Playwright, что для снимков (`check_env.py --install-node <OUT>`); WebKit — `npx playwright install webkit` в той же папке модулей (необязательно: без него проверка WebKit пропускается с пометкой).

## 8. Тесты WP-G
- `tests/test_briefs_concept.py` — 60 тестов: структура и рендер новых брифов без `--set`, эталон ARC Raiders (FB-045), `{ARCH}` (FB-010), `experiments.json` и `{exp:E01.n}`, источники авторов и выдача по номеру раздела (FB-011, SM 6.2), ключи схем из плана (FB-006), личный режим в брифах и outline (SM 4), модули (SM 5), временные папки = имя брифа (совпадает с `check_paths.py`), запреты общих файлов для агента режима (SM 6.3).
- `tests/test_prototype_kit.py` — 11 тестов: набор по `file://`, тесты ядра и контракта (node), расхождения канона, смоук в браузере (если есть Playwright).
