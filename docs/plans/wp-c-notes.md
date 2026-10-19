# WP-C — тексты для файлов оркестратора (SKILL.md, product-concept/SKILL.md, concept-mode.md, CHANGELOG, README)

Пакет: реестр, аудит, отчёты агентов, fact-check. Справочники пакета уже обновлены: `references/scoring.md` (§10 — решения по парам, §11 — ёмкость now, §12 — категории и минимумы), `references/data-contract.md` (раздел «Реестр, отчёты агентов, fact-check (1.5…)»).

## 1. `product-concept/SKILL.md` — таблица фаз / шаги

Вставить в соответствующие строки (формулировки — готовые):

- **C5 (реестр)**, после команды слияния:
  > Однопроходный реестр (`registry.passes: 1`, по умолчанию для quick и deep с разведением тем): после `merge_proposals.py <OUT> --dry-run` отметьте пары `[x]`/`[ ]` в `build/merge-candidates.json` (или в сохранённом выводе) и запишите решения `merge_proposals.py <OUT> --write-distinct` — `build/merge-map.json` руками не правится. Если ёмкость ограничена (`registry.capacity_cap: true` или флаг `--cap-now`), слияние само держит сумму середин `effort_days` горизонта now в пределах ёмкости × 1,3 (`scripts/capacity.py`): лишнее уходит в next с `horizon_reason`, а при нарезке на очереди (`slicing.enabled`) — по очередям `queue`. Решения владельца о горизонтах — в `data/decisions.json → horizons[]` (или `forks[].apply`); слияние применяет их само, к готовому реестру — `merge_proposals.py <OUT> --sync-decisions`. Квоты для брифов генераторов: `check_registry.py <OUT> --quotas` (в личном режиме — свои категории).
- **C5.5 (аудит пробелов)**, после `merge_proposals.py --append G7`:
  > Зависимости от новых `G7-NN`, которые аудитор назвал текстом («P035 ← G7-02» или таблица «Предпосылки») или полем `unlocks` черновика, переводятся в `data/gap-audit-deps.json` автоматически при `--append`; `gap_audit.py --remap` после `--append` не нужен (если запустить — скажет «уже переведены»).
- **C7.5 (новый шаг «второй раунд зависимостей»)**, после волны авторов разделов:
  > `collect_reports.py <OUT> --deps --into-overrides` собирает строки `ПРЕДПОСЫЛКА: P038 ← P033, P111 | почему` из отчётов авторов (`build/agent-reports/*.md`) в `build/deps-patch.json`; затем `merge_proposals.py <OUT> --apply-overrides build/deps-patch.json`, `score.py <OUT>` и Гант. Число добавленных зависимостей — в REPORT (`deps-patch.json → _summary.added`).
- **C8 (дизайн)**, после макетов и `design-refs`:
  > Строки `НУЖНО-ПРЕДЛОЖЕНИЕ: …` и `РАСХОЖДЕНИЕ: …` из `design-refs/*.md` → `link_mockups.py <OUT> --collect-gaps` → `merge_proposals.py <OUT> --append G8`. Слияние само переводит `G8-NN` в P-id в макетах (`data-proposals`), `design-refs/*.json|md`, `data/mockups-index.json` и `data/fact-check.json`.
- **C9 (сборка)**, перед `build_all.py --strict`:
  > Сверка фактов: `collect_reports.py <OUT> --fact-check` → подтвердить записи `data/fact-check.json` (`resolved_value`) и для каждой указать `fix {file, path, value}` (что поправить в JSON-источнике: `data/competitors.json`, `build/model-params.json`…; подсказка — `fix_hint`) или `text_only: true` → `apply_fact_check.py <OUT>`. Запись с `resolved_value` без `applied` и без `text_only` роняет `build_all --strict` (`apply_fact_check.py --check`). В конце прогона: `collect_reports.py <OUT> --retro` → `build/retro.md` (журнал вмешательств `build/interventions.jsonl` + автообнаружение ручных брифов и правок) — раздел REPORT «Ручные вмешательства».
- **Личный режим** (если `project.audience` — personal/circle/personal_then_public), строка о реестре:
  > Категории реестра — `core, data-sources, reliability, privacy-security, ux, ai-quality (при ИИ), maintenance, personal-analytics`; минимумы — по приоритету (категория представлена и её лучшее предложение в now при `--cap-now`), порог A+B — 40 %. Прежние работы и репозитории владельца — `evidence.kind: owner_prior_work` (класс не выше C).

## 2. `SKILL.md` (общий) — раздел про реестр и проверки

Добавить абзац:
> Ручные правки реестра — только `build/overrides.json` (переживают слияние). Ошибка цитаты ≥ 15 слов подсказывает правку; заготовка — `check_registry.py <OUT> --suggest-overrides` → `build/overrides.suggested.json`. Патч понимает `_add` (дописать в список: `{"P038": {"_add": {"dependencies": ["P033"]}}}`). Расхождения фактов исправляются в источниках (`apply_fact_check.py`), а не только в тексте.

## 3. `references/concept-mode.md`

- В строку C5 таблицы: «`--cap-now` / `registry.capacity_cap` — потолок now по ёмкости; `--write-distinct` — решения слияния без ручной правки merge-map.json».
- Новая строка C7.5: «второй раунд зависимостей: `collect_reports.py --deps` → `merge_proposals.py --apply-overrides build/deps-patch.json` → `score.py` → Гант».
- В строку C9: «`collect_reports.py --fact-check` → `apply_fact_check.py` → `build_all --strict`; `collect_reports.py --retro`».

## 4. CHANGELOG.md (раздел 1.5.0)

```
### Реестр, аудит, отчёты агентов (WP-C)
- gap_audit.py: без SyntaxWarning (все скрипты компилируются с -W error::SyntaxWarning, тест); черновики G7 без ложных «нет поля merged_from» (check_proposal(draft=True)); --remap различает «уже переведено merge_proposals.py» и «переведено N из K» (FB-019, FB-020, FB-021).
- Зависимости от G7 из текста аудита («P035 ← G7-02», таблица «Предпосылки») и поля unlocks черновиков сами попадают в data/gap-audit-deps.json при --append (SM 6.1).
- merge_proposals.py --write-distinct: решения [x]/[ ] из --dry-run/--suggest → build/merge-map.json; --suggest печатает решения в формате --dry-run (FB-005).
- merge_proposals.py --cap-now [K] и registry.capacity_cap: сумма now ≤ ёмкость × 1,3 (scripts/capacity.py, один day_hours), перенос лишнего в next с horizon_reason, закрепление решений владельца; очереди нарезки slicing → proposals[].queue, scores.json → queue (SM п. 6, 3.3).
- Решения владельца о горизонтах: data/decisions.json → horizons[] / forks[].apply применяются при слиянии и --sync-decisions; расхождение — ошибка check_registry.py.
- Личный режим реестра: категории core, data-sources, reliability, privacy-security, ux, ai-quality, maintenance, personal-analytics; минимумы «по приоритету» (registry.category_minimums), порог A+B 40 %; check_registry.py --quotas для брифов генераторов (SM разд. 4).
- evidence.kind = owner_prior_work: класс не выше C, вне знаменателя доли A+B (SM 6.1).
- check_registry.py: ошибка цитаты подсказывает build/overrides.json, --suggest-overrides пишет заготовку (FB-029); тег релиза ↔ horizon в режиме идеи; сверка now с ёмкостью.
- Патч overrides понимает "_add" (дописать в список без повторов).
- collect_reports.py --deps: строки «ПРЕДПОСЫЛКА: P038 ← P033 | почему» → build/deps-patch.json (без циклов и повторов), --into-overrides (FB-051).
- collect_reports.py --fact-check (= --merge) с полями fix/applied и подсказкой fix_hint; новый apply_fact_check.py исправляет JSON-источники и ставит applied; --check для build_all --strict (FB-052).
- collect_reports.py --retro: build/retro.md и retro.json из журнала build/interventions.jsonl, ручных брифов и правок (overrides, model-params, merge-map), отступлений агентов и ворот build_all (FB-004).
- --append G8: ссылки G8-NN переводятся в макетах, design-refs, mockups-index и fact-check (FB-009, SM А15).
```

## 5. README.md / INSTALL.md

README, список скриптов — добавить строку:
> `apply_fact_check.py` — исправляет JSON-источники по подтверждённым записям `data/fact-check.json` (`fix {file, path, value}`), `--check` — ворота для `build_all --strict`.

INSTALL — изменений нет (только стандартная библиотека).

## 6. Полный прогон и обратная совместимость

- Новые тесты: `tests/test_registry_fb_gap.py`, `tests/test_registry_fb_check.py`, `tests/test_registry_fb_merge.py`, `tests/test_registry_fb_reports.py` (25 тестов).
- Существующие тесты по затронутым модулям не менялись и проходят; 2 падения в моём прогоне — чужие незавершённые правки WP-D (`test_assemble.py::test_relocate_run` — поле `dir_rel` у relocate_run; `test_dispatch.py::test_triage_file_and_apply` — поле `shared_out` у dispatch.py).
- Прогоны 1.4.0: без `project.audience`, `registry`, `slicing`, `horizons` в decisions.json поведение прежнее; новые предупреждения появляются только при заданной ёмкости (`project.capacity`, профиль solo, `idea.facets.hours_week`).
