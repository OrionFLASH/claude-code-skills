# Локальное приложение: `file://` и каталоги на диске

Приложение без сервера (HTML-файлы на диске, офлайн-редактор, отчёт, выгруженный SPA) проверяется так же, как сайт: те же детекторы, guard и находки. Отличия — в правилах навигации и в том, что тестируется **копия** приложения.

## Порядок
1. **Копия в папке прогона** — тесты могут портить файлы и данные, оригинал (репозиторий, боевые данные) не трогается:
   ```bash
   python3 <SKILL_DIR>/scripts/local_app.py copy /abs/path/to/app <RUN_DIR> --update-config
   ```
   Копия — `<RUN_DIR>/app/` (`--name` — другое имя): независимые файлы, без `.git`, кэшей и `qa-runs/`; симлинки не копируются (список — в выводе). `--update-config` переводит `site.start_urls` и `site.local_roots` в `run-config.yaml` на копию (оригинал больше не разрешён) и пересобирает `rules.json`, если он есть. `--start report.html` — другой стартовый файл. Копия уже есть — код 3 (работать в ней или `--force`).
2. **Правила** (`run-config.yaml`, `templates/run-config.example.yaml`):
   ```yaml
   site:
     start_urls:
       - file:///abs/path/qa-runs/2026-10-09-app/app/index.html
     local_roots:              # каталоги, внутри которых разрешены file://-адреса
       - /abs/path/qa-runs/2026-10-09-app/app
     allowed_domains: []       # http(s)-хосты, если приложение ходит в сеть; иначе пусто
   ```
   Короткие формы: `allowed_domains: [file]` — разрешены каталоги file://-адресов из `start_urls`; `allowed_domains: ["file:///abs/dir/"]` — этот каталог. `intake.py from-text` распознаёт в запросе `file:///…` и абсолютные пути к `.html` и сам заполняет `start_urls` и `local_roots`.
3. Дальше — обычный порядок работы (SKILL.md): `url_guard.py export`, разведка, детекторы, находки.

## Что разрешает guard (`url_guard.py`, `node/guard.js`)
| Адрес | Решение | Правило |
|-------|---------|---------|
| файл или подкаталог внутри `local_roots` (в т.ч. `?query`, `#/маршрут`) | allow | — |
| соседний каталог, домашняя папка, любой файл вне `local_roots` | deny | `base:file-outside-roots` |
| `..` в пути (`/app/sub/../x`, `%2e%2e`) — даже если остаётся внутри | deny | `base:file-path` |
| симлинк внутри каталога (`app/data -> /боевые/данные`) | deny | `base:file-symlink` |
| `file://сервер/папка/…` (сетевой путь) | deny | `base:file-path` |
| `file://` без `local_roots` (обычный сайт) | deny | `base:file-no-roots` |
| `local_roots` относительный, `/`, корень диска, домашняя папка, не список | **код 4 — стоп** | `guard:unavailable` |

- Базовые запреты путей (`/checkout`, `/logout`, `/delete-account`…) проверяются по пути **от каталога** приложения: папка `billing-app` сама по себе не запрещает приложение, а `app/checkout/` — запрещает (чтение — `nav --read-only`). Регэкспы пользователя (`forbidden_url_patterns`, `exclude_patterns`) — по полному URL.
- Загрузка ресурсов (скрипты, картинки, кадры) — тоже только из `local_roots`: route-обработчик `guard.js` обрывает файл вне каталога и через симлинк (Chromium и WebKit перехватывают `file://`).
- Переход скриптом страницы (`location.href = '../другой.html'`) обрывается так же, как ссылка: в журнале `logs/blocked.jsonl` — `base:file-outside-roots`.
- Каталог указывать так же, как он записан в адресе (`/tmp/…` и `/private/tmp/…` на macOS — разные написания: адрес с другим написанием будет запрещён — это fail closed, не дыра).

## Детекторы и скрипты
Все браузерные скрипты принимают `--url file:///…` (можно несколько раз), позиционный `file:///…` и **путь к файлу** без схемы (`./app/index.html`, `~/…` — превращается в `file://`):
```bash
node <SKILL_DIR>/scripts/node/occlusion.js --url file:///abs/app/index.html --frames all --sizes 1440x900,720x450 \
  --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/occlusion.json
node <SKILL_DIR>/scripts/node/reachability.js --url file:///abs/app/index.html --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/reachability.json
node <SKILL_DIR>/scripts/node/a11y.js --url file:///abs/app/index.html --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/a11y.json
node <SKILL_DIR>/scripts/node/targets.js --url file:///abs/app/index.html --device pixel7 --rules <RUN_DIR>/rules.json
node <SKILL_DIR>/scripts/node/shot.js --url file:///abs/app/index.html --rules <RUN_DIR>/rules.json \
  --out <RUN_DIR>/screenshots/F-001-badge.png "#badge|Значок закрывает кнопку"
node <SKILL_DIR>/scripts/node/links.js file:///abs/app/index.html --frames all --rules <RUN_DIR>/rules.json --out <RUN_DIR>/raw/links.json
```
| Скрипт | На `file://` |
|--------|--------------|
| `occlusion.js`, `reachability.js`, `targets.js`, `rtl.js`, `shot.js`, `a11y.js`, `repro.js`, `device_context.js run`, `invariants.js`, `legal_guest.js` | как на сайте; вложенные кадры (`iframe` с `file://`) — `--frames all` |
| `links.js` | страницы читаются с диска; отсутствующий локальный файл — битая ссылка `404`; файлы вне каталога — `skipped`; http-ссылки — внешние |
| `headers.js`, `lighthouse.js` | **не применимо** (нет HTTP): адрес попадает в `notApplicable`, в отчёт — «не проверено: file://» |

## playwright-cli и Playwright MCP
- **playwright-cli** по умолчанию запрещает `file://` («Access to "file:" protocol is blocked»). Разрешение — файл `<RUN_DIR>/playwright-cli.json` (`allowUnrestrictedFileAccess: true` при `local_roots`, там же окно прогона): его пишут `local_app.py copy --update-config` и `browser_mode.py show|set`. Исполнитель открывает сессию так:
  ```bash
  python3 <SKILL_DIR>/scripts/url_guard.py nav file:///abs/app/index.html --config <RUN_DIR>/run-config.yaml
  playwright-cli -s=qa-ux open file:///abs/app/index.html --config <RUN_DIR>/playwright-cli.json
  ```
  Флаг снимает ограничения playwright-cli на файлы вообще, поэтому граница — `url_guard.py nav` перед **каждым** переходом (правило §4 п. 1), как и на сайте.
- **Playwright MCP** тоже блокирует `file://` и открывает его только с флагом запуска `--allow-unrestricted-file-access` (переменная `PLAYWRIGHT_MCP_ALLOW_UNRESTRICTED_FILE_ACCESS`), который заодно снимает ограничение доступа к файлам вне рабочих папок. На лету он не включается: для локального приложения MCP-поток заменить node-скриптами скила и `playwright-cli`; отдельный MCP с этим флагом — только по решению пользователя.

## Ограничения
- `file://`-страницы в Chromium — отдельные непрозрачные источники: `fetch`/XHR к соседним файлам приложение может не выполнить (это поведение браузера, а не находка — сравнить с тем, как приложение запускают пользователи). Хранилище (`localStorage`) у `file://` общее для всех файлов — очищать между проходами.
- Скорость загрузки (Lighthouse) и заголовки не измеряются; производительность интерфейса — только наблюдением (долгие операции, зависания) с замером времени в сценарии.
- В черновиках issues путь к каталогу приложения заменяется на `<app>`, домашняя папка — на `~` (`render_draft.py`), отпечатки находок считаются от каталога (`fingerprint.py`): копия приложения в другой папке даёт те же отпечатки.
