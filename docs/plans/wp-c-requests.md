# WP-C — запросы на правку чужих файлов

Каждый пункт: файл → что → зачем. Код WP-C уже поддерживает описанное (скрипты и тесты готовы), правки ниже замыкают процесс.

## Без владельца в таблице пакетов (оркестратор)

1. **`templates/briefs/_report-footer.md`** — дописать в конец (после блока JSON) два раздела, чтобы их разбирал `collect_reports.py` (FB-051, FB-004):

   ~~~markdown
   ## Предпосылки, которых нет в реестре (авторы разделов, макетов, схем)

   Если пишешь, что одно предложение нельзя сделать без другого, а в `dependencies` реестра этой связи нет, — отдельной строкой
   (её собирает `collect_reports.py --deps` в `build/deps-patch.json`):

   ```
   ПРЕДПОСЫЛКА: P038 ← P033, P111 | почему без них не работает
   ```

   Слева — одно предложение, справа — его предпосылки (только P-id из реестра); после « | » — одна фраза. Нет таких — строк не писать.

   ## Отступления от брифа

   Отдельный блок отчёта: что сделано не так, как велит бриф (другой путь выдачи, пропущенный шаг, временный скрипт, чтение
   не перечисленного входа), и почему. Нет — одна строка `нет`. Блок собирает `collect_reports.py --retro` в `build/retro.md`.

   ```
   ## Отступления от брифа
   - <что> — <почему>
   ```
   ~~~

2. **`scripts/handoff.py`, `scripts/build_xlsx.py`, `scripts/build_deck_json.py`** — подписи категорий личного режима: брать `check_registry.CATEGORY_LABELS_RU` (там же — публичные), неизвестную категорию показывать как есть. Зачем: в личном режиме категории `core`, `data-sources`… иначе выводятся сырыми ключами.

## WP-D (оркестрация)

3. **`references/orchestration.md`** (FB-005, FB-021, FB-029, FB-051, FB-052):
   - в блоке про проходы реестра (≈ стр. 117–136) — правило выбора `registry.passes`: «1 проход (только details, группы с разведением тем через OTHER_TITLES) — quick и deep, если групп ≤ 5 и темы разведены квотами; 2 прохода (titles → details) — exhaustive и deep с пересекающимися группами. Решения по парам в обоих режимах: `merge_proposals.py <OUT> --dry-run` → отметки `[x]`/`[ ]` → `merge_proposals.py <OUT> --write-distinct` (пишет `build/merge-map.json`) → слияние»;
   - стр. ≈ 133: «после `merge_proposals.py --append G7` команда `gap_audit.py --remap` не нужна — ссылки (в т. ч. названные текстом в `research/gap-audit.md` и полем `unlocks`) переводятся при слиянии»;
   - стр. ≈ 134: пример правки текстового поля в overrides: `{"P064": {"description": "…короткая цитата… [факт: URL]"}}` и строка «заготовка — `check_registry.py <OUT> --suggest-overrides`»; про `_add`: `{"P038": {"_add": {"dependencies": ["P033"]}}}`;
   - шаг C7.5 и сверка фактов (≈ стр. 153): `collect_reports.py --deps` → `--apply-overrides build/deps-patch.json` → `score.py` → Гант; `collect_reports.py --fact-check` → подтверждение → `fix`/`text_only` → `apply_fact_check.py`.
4. **`scripts/build_all.py`** (FB-052, FB-058): шаг `factcheck` — `apply_fact_check.py <OUT> --check` (код 1 — провал в `--strict`, без `--strict` — предупреждение; нет `data/fact-check.json` — OK). В сводке `completeness` — строка «fact-check применён».
5. **`scripts/init_run.py --intervention`** (FB-004): писать строку JSON в `build/interventions.jsonl` в формате, который читает `collect_reports.py --retro`: `{"ts": "<ISO>", "by": "owner|orchestrator", "what": "…", "why": "…", "file": "…", "phase": "C5"?, "kind": "brief|edit|decision|other"?}` (формат — `references/data-contract.md`, раздел 1.5 WP-C). Разбор «что, почему, файл» из одной строки — на стороне init_run.
6. **`scripts/report.py` / `templates/report.md`** (FB-004, FB-051, FB-052, FB-009): раздел «Ручные вмешательства» — из `build/retro.json` (`entries`, `by_owner`, `by_orchestrator`); «Зависимостей добавлено вторым раундом» — `build/deps-patch.json → _summary.added`; «fact-check: применено/только текст/открыто» — `build/fact-check-apply.json`; «Перенесено из now по ёмкости» — `build/merge-report.json → cap_now.demoted` (число и сумма дней); «G8 из макетов: добавлено» — `merge-report.json → added` при `groups: ["G8"]`.
7. **`scripts/render_brief.py`** (FB-005, SM разд. 4): `{QUOTAS}` по умолчанию — вывод `check_registry.py <OUT> --quotas` (функция `check_registry.quotas(cfg, min_n)`; в личном режиме — личные категории); `--auto-other-titles` — по плану FB-005 (сторона D).

## WP-G (брифы)

8. **`templates/briefs/gap-audit.md`** (SM 6.1): в «Выдаче» заменить запрет «Зависимости от новых G7-NN сюда не писать — перечислить их в research/gap-audit.md…» на: «Зависимости от новых `G7-NN` — строкой `P035 ← G7-02` в `research/gap-audit.md` (или в таблице «Предпосылки») либо полем `"unlocks": ["P035"]` у черновика G7; `merge_proposals.py --append G7` сам перенесёт их в `data/gap-audit-deps.json` в P-id». Пункт 4 «Формата отчёта» — оставить как сводку.
9. **`templates/briefs/registry-generator.md`** (SM разд. 4, 6.1): блок «Личный режим» (`project.audience` personal/circle/personal_then_public) — категории `core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance, personal-analytics` (без acquisition/conversion/retention/monetization/partnerships/localization; для personal_then_public — только в later/vision); квоты — `{QUOTAS}`; прежние работы владельца — `evidence.kind: "owner_prior_work"`, класс не выше C.
10. **`templates/briefs/strategy-section.md`, `flows.md`, `specs.md`, `experiments.md`** (FB-051): в «Формате отчёта» — ссылка на хвост `_report-footer.md` (строки `ПРЕДПОСЫЛКА:` и блок «Отступления от брифа»).

## WP-F (дизайн)

11. **`scripts/link_mockups.py --collect-gaps`** (FB-009): черновики `data/proposals-draft-G8.json` — полные объекты контракта (класс D с цепочкой в `evidence[].note`, `merged_from`/`source_group` не заполнять — `check_proposal(draft=True)` их не требует); записи `data/fact-check.json` из `РАСХОЖДЕНИЕ:` — с `kind: "mockup"`, `resolved_value: null`, `fix: null`, `applied: false` (их затем закрывает `apply_fact_check.py` или `text_only`). Переводить `G8-NN` → P-id в макетах не нужно: это делает `merge_proposals.py --append G8` (`remapped_files` в отчёте).
12. **`templates/briefs/design-refs.md`**: формат строк — ровно `НУЖНО-ПРЕДЛОЖЕНИЕ: <заголовок> | <категория> | <P-id через запятую>` и `РАСХОЖДЕНИЕ: <P-id> | <ключ макета> | <суть>` (описан в `references/data-contract.md`, раздел 1.5 WP-C).

## WP-E (страница)

13. **`scripts/charts.py` (`CAT_RU`), `references/chart-glossary.ru.json`, `scripts/build_html.py`** (SM разд. 4): категории личного режима — подписи из `check_registry.CATEGORY_LABELS_RU`; соответствие разделам для ссылок `#s<N>` в личном режиме: core, ux → 10; data-sources, reliability, privacy-security, maintenance → 11; ai-quality → 10 (или подраздел «ИИ в продукте», если G его вводит); personal-analytics → 12. Фильтр реестра по категориям — по фактическим категориям реестра, а не по фиксированному списку.
14. **Гант / таблица реестра** (SM 3.3): если у предложений есть `queue` (`slicing.queues`), показывать очередь (группировка Ганта по очередям; колонка в реестре). Данные: `proposals[].queue`, `scores.json → queue`, названия — `run-config.slicing.queues[].name`.

## WP-B (решения, модель)

15. **`scripts/decisions.py --check` и `references/decisions.md`**: принять необязательные `horizons[] {proposals: [P-id], horizon: now|next|later|vision, tag?: mvp|v1|v2|later, why?, date?}` и `forks[].apply {proposals, horizon, tag?}` (или список); проверять P-id и горизонты. Применяет и сверяет — WP-C (`merge_proposals.py --sync-decisions`, `check_registry.py`).

## WP-A (опрос)

16. **`scripts/intake.py concept-apply`**: писать `registry {passes, capacity_cap, category_minimums}` (passes: 1 для quick/deep, 2 — exhaustive; `capacity_cap: true` при светофоре yellow/red или `project.capacity` меньше суммы MVP), `slicing` после ответа «нарезать на очереди». Значения по умолчанию в WP-C: `capacity_cap` выкл., `category_minimums` = priority в личном режиме, иначе count.
