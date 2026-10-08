# Перепроверка заявленных исправлений

Отдельный режим прогона. Владелец репозитория пишет в комментариях, что исправлено («Исправили (v1.2.359): …», «Частично сделали: …, осталось …»). Скил проверяет каждое такое заявление на сайте и ставит статус по заявлению, а не по нечёткому совпадению отпечатков: новая находка описывается другими словами, и `fingerprint.py match` её не свяжет.

## Команды
```bash
python3 <SKILL_DIR>/scripts/claims.py extract <RUN_DIR>/registry.json --repo owner/repo --out <RUN_DIR>/claims.json
python3 <SKILL_DIR>/scripts/claims.py plan <RUN_DIR>/claims.json --site https://example.com/ \
    --out <RUN_DIR>/claims-plan.md --json <RUN_DIR>/rechecks.json
python3 <SKILL_DIR>/scripts/claims.py set <RUN_DIR>/rechecks.json --number 51 --status FIXED-INSUFFICIENT \
    --by "Chrome 1440×813, /lab, шаги 1–3, скриншот F-003" --finding F-003
python3 <SKILL_DIR>/scripts/claims.py set <RUN_DIR>/rechecks.json --number 14 --status NOT-CHECKED \
    --reason other-account-type --reason-text "нужен аккаунт без Pro"
```
- `extract` принимает `registry.json` (`fetch_issues.py registry`) или файл кэша (`fetch_issues.py sync`). Берёт issues с `fix_claimed`; `--all` — все.
- Владелец: `--owners login1,login2`, иначе `author_association` комментария (OWNER, MEMBER, COLLABORATOR), иначе логин из `owner/repo`.
- Из комментария владельца: вид заявления (`fixed`, `partial`, `reply`), версия, цитата (первый абзац, с продолжением списка после двоеточия), пункты списка, «Осталось: …», URL и пути (`/quests`), тексты в кавычках.
- Из тела issue (формы `### Где`, `### Шаги`, `### Что ожидали`, `### Адрес страницы`): раздел, шаги, ожидаемое, URL. Картинки из `user-attachments` идут отдельным списком.
- Подсказки для плана: `logout-required`, `other-account-type`, `side-effect` (загрузка, рейтинг, публикация), `device`.
- `plan --site` пропускает issues, где все URL с другого хоста. `--since-days N` оставляет только закрытые за N дней (для smoke — 90). Пункт без цитаты владельца в план не попадает (`--include-unquoted` — включить).
- Коды выхода: 0 — есть пункты, 1 — план пуст, 2 — ошибка входных данных.

## Порядок
1. `extract` → `plan` сразу после выгрузки реестра (шаг 3). Показать пользователю число пунктов и пункты с подсказками `side-effect`, `logout-required`, `other-account-type`. Спросить, что из этого можно проверять.
2. Для каждого пункта: шаги из issue + каждый пункт списка из заявления («проверить: …»). Действия идут через `url_guard` и правила `side_effects`. Записывать в `journal.md` (`journal.py done`).
3. Результат — `claims.py set`:
   | Статус | Когда |
   |---|---|
   | `FIXED-OK` | всё заявленное работает, исходная проблема не воспроизводится |
   | `FIXED-INSUFFICIENT` | часть заявленного не работает, или проблема осталась в другом месте, браузере или состоянии аккаунта |
   | `REGRESSION` | было подтверждено исправленным и снова воспроизводится полностью |
   | `NOT-CHECKED` + причина | `logout-required` (нужен выход из аккаунта), `other-account-type` (нужен другой тип аккаунта, например без Pro), `forbidden` (запрет), `steps-unclear`, `environment`, `other` |
4. Недоработка → находка в `findings.json` с `claim_ref: {repo, number, quote}` и статусом `FIXED-INSUFFICIENT` или `REGRESSION`; `claims.py set … --finding F-NNN` связывает строку перепроверки с находкой.
5. Публикация недоработки в закрытом issue — по `closed_claims` репозитория (`repo-sync.md` §4).
6. Отчёт: `build_report.py report` добавляет таблицу «№, Issue, Заявлено, Статус, Что проверено, Чем» из `rechecks.json`, из `findings.json → rechecks` и из находок с `claim_ref`.

## Ограничения
- Цитата — первый абзац заявления. Если владелец описал исправление в нескольких комментариях, в план попадает последнее явное заявление, но шаги проверки берутся из всех.
- `fixed` или `partial` определяется по словам («Частично», «Осталось:», «пока не делали»). Названия в кавычках («Осталось найти») не считаются. Агент читает цитату сам.
