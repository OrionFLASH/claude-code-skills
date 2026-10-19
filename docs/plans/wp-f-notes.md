# WP-F — заметки для оркестратора (дизайн-этап, макеты, скриншоты)

Готовый текст для файлов, которые правит оркестратор: `SKILL.md`, `product-concept/SKILL.md`, `references/concept-mode.md`, `CHANGELOG.md`, `README.md`.

## 1. `product-concept/SKILL.md` — таблица фаз, шаг C8 (заменить строку C8 тремя строками)

| Шаг | Что | Кто / чем |
|---|---|---|
| C8.0 | Набор макетов: `python3 <SKILL_DIR>/scripts/mockup_kit.py init <OUT>` — однократно, до волны макетов (формы из `run-config.design.forms` / `product.type` / `design.mobile_reserve`, режимы из `design.modes`); копирует набор, создаёт `M00-design-language.html` (демо всех форм), `tokens-<режим>.css`, `build/kit.lock`. Агенты набор не копируют. | оркестратор |
| C8a | Бриф `concept-design` с `STEPS=1`: `design/directions.md` (`directions_count` направлений, различаются компоновкой и метафорой, а не цветом; режимы; по 2–3 рабочих экрана на вариант для галереи) → `mockup_kit.py gallery <OUT>` → `mockups/gallery.html`. | агент (opus) + оркестратор |
| C8-ask | **Чекпоинт выбора направления** (не пропускать вне автопилота): `mockup_kit.py directions <OUT>` → AskUserQuestion (направления, рекомендованное первым; ссылка на галерею) → `mockup_kit.py choose <OUT> --direction <id> --by owner`. Автопилот: `choose --recommended --by default`. Без `design.chosen` `render_brief.py concept-design` шаги 2–3 не рендерит (`mockup_kit.py gate <OUT> --steps 2-3` → код 3). | оркестратор |
| C8b | Бриф `concept-design` с `STEPS=2-3` (токены выбранного направления, макеты с подсветкой `data-hs-*` 12–25 элементов) и/или `mockups` по ключам; после волны — `mockup_kit.py verify <OUT>`, `shoot_mockups.mjs <OUT>` (без `--only`), `link_mockups.py <OUT> --collect-gaps` (НУЖНО-ПРЕДЛОЖЕНИЕ/РАСХОЖДЕНИЕ → черновики G8 и `fact-check.json`), оценки черновиков → `merge_proposals.py <OUT> --append G8` → `link_mockups.py <OUT> --remap-drafts` → `link_mockups.py <OUT>`. | агенты + оркестратор |

Строку «Ветка/правила» не трогать. В блок «Перед стартом C8» добавить: «Индекс макетов заранее (для specs, до снимков) — `link_mockups.py <OUT> --index-only` (без браузера)».

## 2. `references/concept-mode.md`

- Строка 41: «Все макеты — концепт целиком: бейдж «Концепт продукта, не существующая функция».» → «Все макеты — концепт целиком: бейдж `.ps-concept-badge` с единым текстом «Концепт, не существующая функция · <продукт> · <дата>» (одна константа набора — `templates/mockup-kit/README.md`, «Бейдж концепта»; в режиме идеи текст тот же; проверка — по классу).» (FB-033: два разных текста в инструкциях.)
- Строки 55–56 (дизайн): заменить на ссылку «Дизайн-этап: C8.0 → C8a → C8-ask → C8b — `references/design.md` §2.1; принцип взаимодействия — §3.1».

## 3. `SKILL.md` (режим продукта, фаза 8)

В шаг «Набор компонентов»: «копирует `mockup_kit.py init <OUT>` (не вручную; идемпотентно, `build/kit.lock`); после волны макетов — `mockup_kit.py verify <OUT>` и `link_mockups.py <OUT> --collect-gaps`». В проверки макетов: «`shoot_mockups.mjs` 1.5: `--contrast` видит текст в SVG, `--other-theme` — вторая тема, `--layout` — обрезанные элементы, `--targets` — цели нажатия (сам при `design.pointer_first`), `--hotspots N`».

## 4. `CHANGELOG.md` (раздел 1.5.0, «Дизайн-этап и макеты»)

- Новый `scripts/mockup_kit.py`: `init` (набор и `M00-design-language.html` с демо всех форм продукта, `tokens-<режим>.css`, `build/kit.lock`; однократно и идемпотентно), `verify` (агенты не меняли набор), `directions`/`choose`/`gate` (чекпоинт выбора направления, `design.chosen`, `design.chosen_by`; функция `design_gate()`), `gallery` (`mockups/gallery.html`: 2–3 рабочих экрана на вариант, таблица «один сценарий в N стилях», отклонённые варианты), `params` (FB-007, FB-008, SM 9).
- `link_mockups.py`: `--collect-gaps` (строки `НУЖНО-ПРЕДЛОЖЕНИЕ:`/`РАСХОЖДЕНИЕ:` из design-refs и комментариев макетов → `data/proposals-draft-G8.json` и `data/fact-check.json`, итог `build/collect-gaps.json`), `--index-only` (индекс макетов без браузера), `--remap-drafts` (G8-NN в макетах → P-id по `build/id-map.json`) (FB-009, SM А15).
- Набор макетов 1.3: цели нажатия 32/44 px (`--k-target`, было 28–30 px), `.ps-segmented` переносит варианты вместо скрытой прокрутки, `.ps-badge`/`.ps-btn` не сжимаются, `.ps-brand` без отступов меню в шапке, `.ps-steps` в одну строку на телефоне, снекбар над своей нижней панелью, режимы `data-mode` и токены на режим; новые компоненты — шапка/подвал сайта, нижняя панель действий, счётчик −/+, ячейки «да/нет/не нашли», график с легендой и уровнями, `kbd`, ползунок, «свежесть данных», степпер с линиями, «пузырь» чата, сноски; иконки undo/box/coin/wifi-off; одно правило и один текст бейджа; шаблоны `_hotspots.js` (подсветка элементов `data-hs-*`), `gallery.html`, `tokens-mode.css` (FB-032, FB-033, SM 6.4, SM 8–9).
- `shoot_mockups.mjs`: бейдж по классу `.ps-concept-badge` (обрезанный текст — замечание), `--targets` (pointer/touch, перетаскивание без кнопок; сам при `design.pointer_first` и в `--kit`), `--layout` (обрезанные элементы flex-рядов, скрытая прокрутка; сам в `--kit`), `--other-theme` (вторая тема, `<ключ>.theme-<тема>.png`), SVG-контраст, зоны подсветки `hotspots.zones`, `--hotspots N`, `--only` с G8-xx, локальная дата (SM 6.4).
- `shoot_competitors.mjs`: cookie-баннеры по умолчанию скрываются стилем без кликов, поле `cookie: hidden|accepted|none`, клик — только `--accept-cookies` (FB-031).
- Брифы `concept-design`, `mockups`, `design-refs`, `competitor-cards`: этапы C8a/C8-ask/C8b, `directions_count`, «компоновка и метафора, а не цвет», режимы и токены на режим, галерея, pointer/touch-first, мобильный задел, стандарт подсветки 12–25 элементов, канон демо-данных, фиксированный формат пробелов/расхождений, «набор скопирован — не копировать».

## 5. `README.md` / `INSTALL.md`

README, раздел скриптов: добавить строку «`mockup_kit.py` — набор макетов, M00, выбор направления дизайна, галерея вариантов». INSTALL — без изменений (только стандартная библиотека; Playwright — как раньше).

## 6. Поля run-config (контракт уже в плане; что читает WP-F)

`design.directions_count`, `design.modes[]`, `design.default_mode`, `design.forms[]` (`web|mobile|mobile-later`), `design.mobile_reserve`, `design.pointer_first`, `design.gallery`, `design.chosen`, `design.chosen_name`, `design.chosen_by`, `design.chosen_at` (последние четыре пишет `mockup_kit.py choose`). Все необязательны: без них поведение 1.4.0 (три направления, одна тема токенов, без проверки целей).
