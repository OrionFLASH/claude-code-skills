# Долгие сценарии: `soak` и фоновые задачи `job`

Запись 30–60 минут, долгая обработка, работа в фоне с выключенным экраном — их не ждут «глазами» и не отдают субагенту: ожидание выполняет фоновый скрипт, а агент тем временем работает с другим стендом.

## soak — один долгий прогон с метриками
```bash
python3 <SKILL_DIR>/scripts/adb_helpers.py soak --minutes 30 --every 60 --tag rec30 \
    --start-desc "Начать запись" --expect-text "Идёт запись" --service RecordingService \
    --metrics meminfo,df,focus,service,battery,thermal --screenshots 10 --screen-off-at 3 --screen-on-at 28 \
    --stop-xy 540,2040 --expect-duration --serial emulator-5556 --run-dir <RUN_DIR>
```
1. **Старт** (необязательно): `--start-text/--start-desc/--start-id` — нажатие через guard, как `tap`; `--start-xy X,Y` — по координатам без дерева (экран с анимацией), guard по пакету и экрану.
2. **Предусловие — обязательно для записи и обработки.** `--expect-text` (текст на экране) и/или `--service` (сервис приложения работает, `dumpsys activity services`) в течение `--expect-timeout` (15 с). Не выполнено → статус **`invalid`** сразу, а не через 30 минут: прогон о приложении ничего не говорит (нажатие попало не туда, открылся лист). Скриншот `soak-<tag>-<serial>-start.png` — посмотреть.
3. **Метрики** каждые `--every` секунд → `raw/soak-<tag>-<serial>.jsonl`: PSS / Java / Native (`meminfo`), свободно в `/data` (`df`), фокус окна, PID (перезапуск процесса), сервис, батарея и температура, тепловой статус, **загрузка хоста** (эмуляторов рядом, load average). Скриншоты каждые `--screenshots` минут; `--screen-off-at` / `--screen-on-at` — выключить и включить экран на N-й минуте (включение — с `wm dismiss-keyguard`).
4. **Потеря по ходу**: процесс умер или сервис пропал → статус **`interrupted`** с минутой события — это находка (например, «запись остановилась на 6:49»); `--continue-on-loss` — снимать дальше.
5. **Стоп и итог**: `--stop-…` — нажатие стоп; `--expect-final-text` — текст после стопа; `--expect-duration` — на экране есть длительность `м:сс` / `ч:мм:сс` ≈ `--minutes` (`--expect-minutes`, допуск `--tolerance` 5 %, не меньше 30 с); `--result-file "/sdcard/Recordings/*.m4a"` — длительность файла из общей папки (`adb pull`; WAV, MP4/M4A/3GP, Ogg; приватная папка приложения — «не поддерживается»). Не совпало → **`result-mismatch`** (находка).
6. Сводка — `raw/soak-<tag>-<serial>.json` (статус, причина, минуты, события, PSS мин/макс/рост в МБ/ч, свободное место, нагрузка хоста, скриншоты) и вывод команды. Коды: 0 — `ok` / `interrupted` / `result-mismatch` (смотреть `status`), 5 — `invalid` / `failed`.

## job — фоном, пока агент занят другим
```bash
python3 <SKILL_DIR>/scripts/adb_helpers.py job start --name rec60 --serial emulator-5558 --run-dir <RUN_DIR> -- soak --minutes 60 --every 60 --tag rec60 --start-desc "Начать запись" --expect-text "Идёт запись" --screen-off-at 3 --screen-on-at 58 --stop-xy 540,2040 --expect-duration
python3 <SKILL_DIR>/scripts/adb_helpers.py job status --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py job status rec60 --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py job log rec60 --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py job stop rec60 --run-dir <RUN_DIR>
```
После `--` — любая подкоманда `adb_helpers.py` (`soak`, `mic-inject`, `monkey`…) с её аргументами; `--serial`, `--run-dir`, `--config`, `--confirmed` задачи берёт из `job start`. Задача отвязана от сессии: состояние — `raw/jobs/<id>.json` (`running` / `done` / `failed` / `stopped`, код выхода), вывод — `logs/job-<id>.log`, по окончании — строка в `journal.md`. `job status` у soak показывает прогресс (минута, PSS, сервис) и итог. `job stop` останавливает задачу, soak успевает записать сводку (`stopped`).

**Один стенд — одна задача с действиями в интерфейсе:** второй `soak` на том же serial не запускается (код 2). `mic-inject` рядом с `soak` на том же эмуляторе — можно (звук идёт по gRPC, не через экран). Пока на стенде идёт soak, агент на нём **не нажимает** — работает с другим стендом; чтение (`meminfo`, `screenshot`) — можно.

## План «запись + обработка + ручное исследование»
1. Эмулятор B: `job start --name rec60 … -- soak --minutes 60 …` (+ `job start --name voice … -- mic-inject --wav … --loop 0 --duration 3600` на том же B).
2. Эмулятор C: `job start --name proc … -- soak --minutes 70 --start-desc "Расшифровать" --service <сервис обработки> …`.
3. Основной поток (эмулятор A): разведка и проверки по чек-листам.
4. Время от времени `job status`; `invalid` — исправить старт и перезапустить, `interrupted` — оформить находку и воспроизвести ещё раз.
Ячейки матрицы с долгими сценариями — `matrix.cells` с `background_minutes` (`depth-matrix.md`).

## Замеры времени и параллельные эмуляторы
Работающие рядом эмуляторы делят процессор хоста: время обработки на «нагруженном» хосте бывает в разы больше, чем на свободном. Поэтому:
- **замеры скорости** (`start-time`, `gfxinfo`, длительность обработки в soak) — на свободном хосте: один эмулятор, без фоновых задач; параллельные стенды — для функциональных и долгих проверок (память, стабильность, фон);
- каждый замер пишет загрузку хоста (`raw/metrics.jsonl → host`, `soak → host`); `build_report.py` помечает замеры при нескольких эмуляторах («⚠ рядом работало эмуляторов: N») и в «Длинных сценариях» пишет, что время искажено, а память и стабильность — достоверны.

## Отчёт
`build_report.py report` — раздел «Длинные сценарии»: сценарий, стенд, статус (прошёл / прервался — находка / итог не совпал — находка / **недействителен** — предусловие не выполнено), длительность, итог, PSS (мин–макс, рост в час), события (смерть процесса, потеря сервиса, экран), нагрузка хоста. Недействительные прогоны в выводы не входят.
