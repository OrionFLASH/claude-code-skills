# Внешний продукт без кода (`product.mode = external`)

Режим для прогона **не из репозитория продукта**: продукт чужой или код закрыт, а в рабочей папке — материалы QA, APK,
выгрузки. Фаза 1 по коду (`repo_scan.py`, `repo_facts.py`) тогда бесполезна; источники понимания продукта — сайт,
карточки в магазинах, APK, трекер, справка в приложении и обход приложения.

## Как включается

- Опрос, раунд 0 «Заказчик и продукт» (`intake.py questions --round 0`, задаётся первым), карточка «Чей продукт»:
  «Определи по папке» (`product.mode: auto`), «Код в этой папке» (`repo`), «Кода нет, продукт внешний» (`external`).
- `auto`: в папке сборки (`*.apk`, `*.aab`, `*.ipa`) без исходников приложения или нет кода продукта (файлы кода вне
  `tests/`, `qa/`, `docs/`, `scripts/`… меньше 5 и нет манифестов) → `external`; решение — в `assumptions`.
- Без карточки (`product.mode: repo` по умолчанию) и с APK без исходников в папке — уточняющий вопрос в `follow_up`.
- Вручную: `intake.py apply … --set product.mode=external` или `intake.py update <OUT> --set product.mode=external`.

## Что меняется в run-config

| Поле | Значение в external |
|---|---|
| `product.mode` | `external` |
| `scope.repo_analysis`, `sources.repo`, `repo.analyze` | `false` — `repo_scan.py`/`repo_facts.py` печатают «пропущено» и выходят с кодом 0 (`--force` — сканировать всё равно) |
| `sources.external` | `site` (адрес сайта), `stores` (`[{store, id, url}]`), `apk` (пути от рабочей папки), `tracker` (`github:<owner/repo>`, если включены Issues), `other_urls` |
| `sources.stores` | карточки магазинов из ответа «Адрес» (в любом режиме; их читает `store_stats.py`) |
| `scope.app_run` | `false`, если сайта нет (обход приложения — отдельно, см. фазу 2) |
| `product.type` | `mobile` при магазинах или APK; только сайт — `other` и вопрос «какой это продукт» |
| `product.name` | имя рабочей папки не используется — вопрос «как называется продукт» |
| `project.requester_role`, `project.product_owner` | роль заказчика (owner / analyst / partner / investor / other) и владелец продукта; не владелец без указанного владельца — вопрос в `follow_up` |
| `sources.internal_authors` | логины внутренних авторов трекера (заказчик, тестировщики) — их обращения не спрос (вопрос в `follow_up`, если трекер есть) |

Ответ «Адрес» может содержать несколько ссылок через пробел: карточки RuStore, Google Play, App Store, AppGallery
распознаются и уходят в `sources.stores`, первая прочая ссылка — `product.url` (сайт).

## Фазы

| Фаза | В режиме external |
|---|---|
| 1 | `store_stats.py <OUT>` → `data/store-stats.json`, `research/store-stats.md`; `app_scan.py <OUT>` → `data/app-scan.json`, `research/app-scan.md`; сайт — `audit_site.mjs` (если есть `product.url`); трекер — `issues_export.py` с учётом `sources.internal_authors`; справка и FAQ на сайте. Итог — `research/product-understanding.md` (инвентарь функций — по APK, карточкам и обходу). `repo_scan`/`repo_facts` — в STATUS.md со статусом «—» |
| 2 | обход приложения на эмуляторе — скилл `android-qa-audit` (APK, adb); скриншоты → `mockups/current/`, замеры — структурированно в `data/` |
| 3 | `seeds.py <OUT>` → `build/seeds.md`: затравки `growth-library.md` по типу (`mobile` при APK/магазинах) с отметкой найденных сигналов |
| 4–9 | как обычно; входы брифов — через `render_brief.py`: `{MISSING_INPUTS}` сам перечисляет `repo-scan.json`/`repo-facts.json` (по `scope.repo_analysis=false`); в брифах `registry-generator`, `gap-audit`, `research-competitors`, `specs` есть раздел «Внешний продукт» |

`facts_scaffold.py` в разделе «Что уже есть» берёт APK и «что нового» из магазинов, а не `repo-scan.json`.

## Как читать доказательства A+B без кода

- Внутренние доказательства (класс A) — не код, а наблюдения: APK (`data/app-scan.json`: манифест, SDK, строки),
  карточки и отзывы (`data/store-stats.json`), обход приложения и сайта (`research/ui-inventory.md`). В реестре —
  `kind: own_app` с файлом данных или URL карточки; `kind: repo` невозможен.
- Внешние (класс B) — конкуренты, сообщества, спрос — как обычно; цифры конкурентов в магазинах можно снять тем же
  `store_stats.py` для сопоставимости.
- Чего нет без владельца (консоли магазинов, аналитика, выручка) — не допущение «данных нет», а шаг «запросить у
  владельца» в «Вопросах владельцу»; при `requester_role ≠ owner` вопросы адресуются владельцу через заказчика.

## Роль заказчика и публичные тексты

- `project.requester_role` меняет формулировки: «мы» — только у владельца; аналитик пишет «продукт», «команда продукта»;
  этика публикаций — без внутренних данных владельца и без оценок команды в публичных текстах.
- `disclosure` (раунд 0, «Раскрытие»): `full` — раздел «Инструменты и токены» в отчёте; `summary` — одна строка без
  моделей и токенов; `none` — в `deliverables/` нет упоминаний автоматизации, служебный отчёт об инструментах — в
  `build/`. Проверка: `intake.py disclosure-check <OUT>` (код 1 и адреса строк, если найдено: Claude, субагент, LLM,
  число токенов, TypeSafe …; «дизайн-токены» не считаются).

## `data/store-stats.json`

```json
{"generated": "2026-10-11T09:30:00Z", "tool": "store_stats.py", "offline": false, "lang": "ru", "country": "ru",
 "stores": [{"store": "rustore|gplay|appstore|huawei", "id": "<пакет или id>", "url": "…", "status": "ok|skipped|error",
             "reason": "почему skipped/error", "fetched_at": "…", "warnings": [],
             "fields": {"<поле>": {"value": 4.4, "as_of": "2026-10-11", "source": "URL", "kind": "факт|оценка", "note": "смысл и оговорка"}},
             "reviews": [{"id": 1, "date": "2026-10-01", "rating": 1, "text": "≤ 400 знаков", "has_reply": true}]}],
 "summary": [{"store": "…", "rating": 4.4, "ratings_count": 16, "downloads_30d": 705, "downloads_label": "1 тыс +",
              "updated": "…", "dev_reply_share": 0.077, "reviews_sampled": 13, "status": "ok"}],
 "assumptions": ["…"]}
```

Поля `fields`: `name`, `rating`, `ratings_count`, `downloads_30d`/`downloads_7d` (RuStore, `monthlyDownloads`/
`weeklyDownloads` страницы — смысл не документирован, `kind: оценка`), `downloads_label` (метка «1 тыс +», «1 млн+»),
`version`, `updated`, `whats_new`, `developer`, `min_android`, `price`, `reviews_sampled`, `dev_reply_share`,
`reviews_avg_rating`. Имена авторов отзывов не сохраняются.

Источники и ограничения: RuStore — страница карточки (JSON-LD и данные Next.js), отзывы `backapi.rustore.ru/comment/comment`
и страница отзывов (ответы разработчика лежат в `replies`, поле `devResponse` API часто пустое); Google Play — HTML
карточки (JSON-LD, метки «скачиваний», «Последнее обновление», «Что нового» — может сломаться при смене вёрстки), отзывы
и ответы не собираются (внутренний API); App Store — Lookup API и RSS отзывов, загрузок и ответов нет; AppGallery —
`skipped`. Нет сети или TLS без корневых сертификатов — `skipped` с причиной, файл пишется. `--offline-fixture DIR` —
повтор без сети (тесты), `--save-fixture DIR` — сохранить ответы.

## `data/app-scan.json`

```json
{"generated": "…", "tool": "app_scan.py", "aapt2": "путь или null",
 "apps": [{"file": "…", "name": "app.apk", "size_bytes": 1, "sha256": "…", "kind": "apk|aab", "tools": ["python", "aapt2"],
           "label": "Название", "label_locales": ["default", "ru"], "locales": ["…все локали строк, вместе с библиотеками"],
           "manifest": {"package": "…", "version_code": 1, "version_name": "1.0", "min_sdk": 26, "target_sdk": 36, "compile_sdk": 36,
                        "permissions": [{"name": "android.permission.RECORD_AUDIO", "dangerous": true, "special": false, "max_sdk": null}],
                        "features": [], "component_counts": {"activity": 6}, "components": {"activity": ["…"]}, "launcher": "…",
                        "intent_filters": [], "deep_links": ["scheme://host"], "exported_unprotected": [], "flags": {"allowBackup": false}},
           "abis": ["arm64-v8a"], "native_libs": ["libhermes.so"], "native_hints": ["Hermes (React Native)"],
           "frameworks": ["React Native"], "sdks": [{"id": "sentry", "name": "Sentry", "category": "краши", "evidence": "classes.dex"}],
           "ai_keywords": {"whisper": 29}, "domains": [{"domain": "api.example.com", "count": 3}],
           "assets": {"count": 3, "configs": [{"path": "assets/app.config", "keys": ["…"], "content": {"apiKey": "<скрыто>"}}], "largest": []},
           "libraries": [{"lib": "androidx.core_core", "version": "1.13.0"}], "strings": {"count": 1, "cyrillic_share": 0.1},
           "signals": [{"id": "no-exact-alarm", "level": "info|warn|error", "text": "…"}], "limitations": [], "warnings": []}],
 "limitations": ["…"]}
```

Разбор без установки: свой парсер бинарного `AndroidManifest.xml` и `resources.arsc` (стандартная библиотека) — всегда;
`aapt2` (PATH, `$ANDROID_HOME/build-tools/*`, `~/Library/Android/sdk/build-tools/*`) — если найден, для названия, локалей
и сверки (расхождения — в `warnings`). Ограничения: AAB — манифест в protobuf, разбирается только состав архива; SDK — по
сигнатурам классов в dex, обфускация может скрыть часть; секретоподобные значения в конфигах скрываются; сигналы —
эвристики «проверить»; экраны, скорость и поведение не проверяются (это `android-qa-audit`).

## Опрос: что ещё добавлено вместе с режимом

- Раунд 0 «Заказчик и продукт»: роль, чей продукт и где код, ёмкость в человеко-днях в месяц
  (`project.capacity_days_month`; «Определи по команде» — 12 дней для одного, 15 × команда), раскрытие (`disclosure`).
- «Бюджет»: суммы в карточке; `strategy.budget.small/medium` в валюте проекта в месяц (по умолчанию 50 000 / 300 000 ₽
  или 500 / 3000 $), своя сумма в «Other» («до 30 тыс ₽») разбирается.
- `--from-askuser`: обёртка `{"answers": {…}}` разворачивается; неизвестный ключ — ошибка (код 2) с подсказкой и
  списком заголовков (`--lenient` — предупреждение); значения-объекты — ошибка.
- `follow_up`: «Уточню сам» без текста, противоречие рынков (README против адреса, названия и магазинов), владелец
  продукта, тип продукта, внутренние авторы трекера — готовые вопросы; задать **до** «Начинаю?», ответ —
  `intake.py update <OUT> --set путь=значение` или `--from-askuser '{"<вопрос>": "<ответ>"}'`.
- Сводка: «получится только веб-страница, верно?» при одном формате; предупреждение о пустых `keywords-volume`,
  `events-calendar` и разделе «Спрос» при выключенных «Спрос и события»; прогноз размера прогона (агенты, токены
  субагентов, часы; оценка ±50 % по двум прогонам глубины deep 2026-10 — `intake.py` `FORECAST`), пишется в
  run-config `forecast`.
- `intake.py questions --json` принимается (вывод и так JSON).
