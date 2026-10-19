# Самопроверка product-strategy

Тесты — pytest (кроме него — только стандартная библиотека), офлайн (локальные HTTP-серверы на 127.0.0.1 там, где нужны ссылки). Демо-данные создают `scripts/make_demo.py` (продукт), `scripts/make_concept_demo.py` (идея) и `scripts/make_progress_demo.py` (отслеживание) во временных папках; данные пользователя и сеть не нужны.

```bash
cd skills/product-strategy
python3 -m pytest tests -q -p no:cacheprovider                              # всё (≈ 860 тестов, несколько минут)
python3 -m pytest tests/test_concept_intake_banks.py -q -p no:cacheprovider # один файл
python3 -m pytest tests -q -p no:cacheprovider -k "concept and not browser" # по ключевым словам
```

Браузерные проверки (Playwright: smoke страницы, снимки макетов и конкурентов, смоук прототипа, PPTX/PDF) пропускаются со `SKIP`, если нет Node-модулей: поставить — `python3 scripts/check_env.py --install-node` (кэш `~/.cache/product-strategy/node`, другая папка — `PS_NODE_DIR`). WebKit — `npx playwright install webkit` в папке модулей (`check_env.py --print-node-dir`); Firefox необязателен. `openpyxl` (если есть) включает дополнительную проверку XLSX.

## Что покрыто

| Файлы | Что проверяют |
|---|---|
| `test_core.py`, `test_pipeline.py` | опрос, проверка инструментов, папка прогона, путь скилла, конвейер `build_all.py`, сквозная оценка (реестр → оценки → модель → графики), документация ссылается на существующие файлы |
| `test_scan.py`, `test_links_data.py`, `test_external.py` | сканеры репозитория и Issues, ссылки и выгрузки, перенос папки, режим внешнего продукта (магазины, APK, затравки) |
| `test_intake2.py` | опрос 1.4: раунд 0, валидация `--from-askuser`, `update`, бюджеты, ёмкость, `disclosure`, сводка |
| `test_concept.py` | режим идеи: банк вопросов, досье, предпроверка, фазы C0–C9, сквозной демо-прогон |
| `test_concept_intake_text.py` | 1.5: имя, slug и ключевые слова, перевод темы, свободные ответы «Форма» и «Рынки», вопросы запроса RQ, ссылки владельца, предзаполнение из текста |
| `test_concept_intake_banks.py` | 1.5: карточка «Начало», личный режим, условные блоки, быстрый режим, «по умолчанию для карточки», взаимоисключающий мультивыбор, формат AskUserQuestion |
| `test_concept_intake_checks.py` | 1.5: противоречия ответов, ёмкость MVP, нарезка на очереди, git (пустой репозиторий, ветка до записи, `--dry-run`), правила CLAUDE.md, `project.capacity` |
| `test_concept_intake_dossier.py` | 1.5: досье без `<EN:` при `--topic-en`, `--refresh` после пересмотра идеи, разделы RQ и материалов, совместимость с run-config 1.4 |
| `test_capacity.py`, `test_plan_baseline.py`, `test_model_web_direct_personal.py`, `test_model_profiles.py` | одна ёмкость, базовая линия плана и сверка текста, контракт Ганта, черновики резюме, решений и факт-листа, канон демо-данных; профили модели (`web-direct`, `personal`, `one_time_purchase`, `mobile-app`, `oss`), sensitivity-only |
| `test_decisions.py`, `test_sample_size.py`, `test_assemble.py` | решения и плейсхолдеры чисел, числа без метки, повторы; калькулятор выборок; склейка текста, методология, факт-лист |
| `test_registry2.py`, `test_registry3.py`, `test_registry_fb_{gap,check,merge,reports}.py` | слияние, проверка реестра, зависимости, аудит пробелов; 1.5: однопроходный реестр (`--write-distinct`), потолок now по ёмкости, очереди, горизонты по решениям, личный режим, `owner_prior_work`, второй раунд зависимостей, fact-check → источники, ретроспектива |
| `test_process_{init_run,dispatch,build_all,render_brief,paths_env,pivot}.py`, `test_dispatch.py`, `test_render_brief.py` | 1.5 процесс: журнал вмешательств, один чек-лист, статус с ETA, смена решений, диспетчер и прогноз, «быстрая концепция», ворота полноты, `--preview`, `report.py`, `--auto` в брифах, временные файлы агентов, git и среда, пересмотр идеи C4.5 |
| `test_wave2_{gates,process,texts}.py` | волна 2 (1.5): запросы пакетов друг к другу — ворота брифов, сверка ветки и политики моделей, таблицы REPORT, демо-схемы с `<title>` и бейджем |
| `test_briefs_concept.py`, `test_briefs_wave2.py` | новые брифы режима идеи (интеграция, данные, ИИ, референсы владельца, модули C7, резюме), личный режим в outline и брифах, `{ARCH}`, `experiments.json`, источники авторов, ключи схем, временные папки = имя брифа |
| `test_prototype_kit.py` | набор рабочего прототипа по `file://`, тесты ядра и контракта режимов (node), расхождения канона, смоук в браузере (если есть Playwright) |
| `test_design.py`, `test_mockups2.py`, `test_design_fb_{kit,competitors}.py`, `test_mockups_fb_tools.py` | токены, набор макетов (в т. ч. мобильный), `shoot_mockups.mjs` (цели нажатия, обрезка, вторая тема, бейдж по классу), cookie-баннеры конкурентов без кликов, `mockup_kit.py` (набор, выбор направления, галерея), `link_mockups.py --collect-gaps / --index-only / --remap-drafts` |
| `test_build_html.py`, `test_site_mode.py`, `test_site_interactive.py`, `test_site_viewer_ui.py`, `test_site_flow_a11y.py`, `test_qa_page.py` | страница-сайт и режимы `--single/--lite/--zip`, хуки `build/extra`, слой интерактивности (просмотр с живым SVG, поиск, сущности, макеты) в Chromium и WebKit, доступность схем, smoke |
| `test_charts_interactive.py`, `test_charts_ui.py`, `test_charts_gantt_horizon.py` | разметка и пояснения графиков, панель на странице, Гант на весь горизонт с пробелами плана |
| `test_export.py`, `test_handoff.py` | XLSX, колода, PPTX/PDF (при наличии Node), файл задач для Claude Code |
| `test_tracking.py`, `test_progress_demo.py` | режим «Отслеживание выполнения» на временном git-репозитории, демо-прогресс |

Новый тест — в своём файле `tests/test_<тема>.py`, без сети и без данных пользователя; браузерные части — со `SKIP`, если нет Playwright.
