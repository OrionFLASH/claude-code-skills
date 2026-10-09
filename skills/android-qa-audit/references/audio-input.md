# Звук в микрофон эмулятора: `mic-status`, `mic-inject`

Для диктофонов, голосовых заметок, распознавания речи и звонков в приложении нужен «живой» звук в микрофоне. У скила три пути, по убыванию полезности. Каждый путь, который на этой машине работать не может, отвечает «не поддерживается: <причина>» и называет следующий; `--via auto` (по умолчанию) пробует их по порядку.

| Путь | Что нужно | Что проверяет | Ограничения |
|------|-----------|---------------|-------------|
| 1. `grpc` | свой эмулятор `qa-*`, запущенный с `--mic-inject` | полный путь «микрофон → кодек → запись → обработка» | только эмулятор скила; формат — WAV PCM |
| 2. `loopback` | виртуальное аудиоустройство хоста (BlackHole / Loopback на macOS, `snd-aloop` или null-sink PulseAudio/PipeWire на Linux, VB-Cable на Windows), выбранное пользователем входом по умолчанию | то же, звук идёт через устройство хоста | скил устройство **не ставит** и звуковые настройки хоста **не меняет**; Windows — воспроизвести файл вручную |
| 3. `file` | ничего | импорт файла в приложение | живой микрофон этим не проверяется — в отчёте так и написать |

```bash
python3 <SKILL_DIR>/scripts/adb_helpers.py mic-status --serial emulator-5554 --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py mic-inject --wav <RUN_DIR>/raw/speech-16k.wav --serial emulator-5554 --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py mic-inject --wav <файл.wav> --via grpc --loop 0 --duration 1800 --serial emulator-5554 --run-dir <RUN_DIR>
python3 <SKILL_DIR>/scripts/adb_helpers.py mic-inject --wav <файл.wav> --via file --folder Download --serial emulator-5554 --run-dir <RUN_DIR>
```
`mic-status` — какой путь доступен и почему нет остальных (`recommended`). `mic-inject` — `--loop N` (0 — без конца, до `--duration` или `job stop`), `--at-sec N` — с N-й секунды файла, `--realtime` — режим `MODE_REAL_TIME` (у эмулятора экспериментальный). Долгая подача звука — фоном: `adb_helpers.py job start --name voice --serial … --run-dir … -- mic-inject --wav … --loop 0 --duration 3600` (`long-runs.md`), одновременно с `soak` записи на том же эмуляторе.

## Путь 1. gRPC эмулятора (`injectAudio`)
**Запуск.** `avd_manager.py start <AVD> --mic-inject --run-dir <RUN_DIR> [--headless]` добавляет `-grpc <свободный порт 8554, 8556…> -grpc-use-token` и не выключает звук (без `--mic-inject` у `--headless` есть `-no-audio`). Порт gRPC — в `stands.json` (`grpc_port`). Открывать gRPC без авторизации (`-grpc <порт>` без `-grpc-use-token`) скил не даёт: `guard.py emulator-args` → код 3.

**Авторизация — как она работает.** С `-grpc-use-token` эмулятор сам создаёт токен для этого запуска и пишет его в **discovery-файл** запущенного эмулятора (`pid_<pid>.ini`; путь печатает консольная команда `adb emu avd discoverypath`). В файле: `grpc.port`, `grpc.token`, `port.serial`, `avd.name`. Клиент передаёт метаданные `authorization: Bearer <grpc.token>`. Отсюда две причины «token is invalid» в прошлых попытках: токен консоли `~/.emulator_console_auth_token` — **другой** секрет (для telnet-консоли, gRPC его отвергает), и без префикса `Bearer ` эмулятор токен не принимает. Скил читает discovery-файл сам, токен **нигде не печатает** (в выводе, журналах и ошибках — `abcd…(N)` или `***`, `masking.py`).

Запуск по умолчанию из Android Studio (без `-grpc`) использует JWT (`grpc.jwks`) — такие токены подписывает Studio, скил их не создаёт: для mic-inject эмулятор перезапускается с `--mic-inject`.

**Допустимые флаги запуска** (белый список `guard.py emulator-args`, `stands.md` → «Дополнительные флаги»): `-grpc <порт>` только с `-grpc-use-token` или `-grpc-use-jwt`; gRPC слушает `127.0.0.1` («security: Local»); `-allow-host-audio` (эмулятор слышит микрофон хоста) — только после «да» пользователя (`--confirmed`); `-no-audio` с mic-inject несовместим.

**Клиент.** `scripts/grpc_emu.py` — gRPC на стандартной библиотеке Python (HTTP/2 без TLS на 127.0.0.1, HPACK, управление потоком), методы `EmulatorController/getStatus` (проверка токена), `injectAudio` (поток `AudioPacket`: формат один раз в первом пакете — частота, моно/стерео, 8/16 бит; пакеты по 100 мс, клиент держит не больше 200 мс впереди — буфер эмулятора 300 мс), `setClipboard` (ввод кириллицы, `device-control.md`). Ничего ставить не нужно: ни `grpcio`, ни `protoc`.

**Файл.** WAV PCM, 8 или 16 бит, моно или стерео, 8–48 кГц. Другой формат — подсказка перекодировать: `ffmpeg -i in.m4a -ac 1 -ar 16000 -sample_fmt s16 out.wav` (ffmpeg ставит пользователь). Речь для теста — своя запись пользователя или синтез на хосте (macOS `say -o speech.aiff …` и перекодирование) — без персональных данных.

**Ошибки.** `UNAUTHENTICATED` — токен не принят (эмулятор запущен без `-grpc-use-token` или перезапущен — discovery-файл новый, повторить `mic-status`); `FAILED_PRECONDITION` — микрофон уже занят другим источником; `INVALID_ARGUMENT` — частота или размер пакета; нет ответа — порт gRPC не тот. Всё выводится замаскированным.

## Путь 2. Виртуальное аудиоустройство хоста
`check_env` показывает строку «виртуальное аудиоустройство (loopback)»: найдено ли и что выбрано входом по умолчанию. Скил: **ничего не устанавливает** и **не переключает** устройства ввода и вывода хоста. Пользователь сам ставит драйвер (BlackHole: `brew install --cask blackhole-2ch`; Linux: `sudo modprobe snd-aloop` или null-sink; Windows: VB-Audio Virtual Cable) и выбирает его входом (на macOS — и выходом) по умолчанию. Тогда `mic-inject --via loopback`:
1. `adb emu avd hostmicon` — эмулятор слушает вход хоста; это **confirm** (`guard.py`): эмулятор слышит устройство ввода хоста — повтор с `--confirmed` после «да»;
2. файл воспроизводится в устройство (macOS `afplay` — в выход по умолчанию, Linux `paplay --device=<sink>`);
3. `adb emu avd hostmicoff` — всегда, даже при ошибке.
Не готово (нет устройства, не выбрано входом, Windows) — «не поддерживается: …» и путь `file`.

## Путь 3. Файл вместо микрофона
`mic-inject --via file` = `push-media` (файл → `/sdcard/<папка>/qa-<имя>` + медиасканер) и подсказка: открыть в приложении импорт аудио (системный выбор файла) и `import-file --name qa-<имя> --folder Download` (`device-control.md` → «Файлы»). В находках и отчёте: «звук подан импортом файла, путь через микрофон не проверен».

## Что не проверено вживую
Клиент gRPC проверен на поддельном сервере HTTP/2 в тестах (`tests/helpers/fake_grpc.py`: авторизация Bearer, Хаффман, управление потоком) и по примерам RFC 7541; путь discovery-файла и формат ключей — по документации эмулятора и открытым клиентам. Живой прогон на эмуляторе с `-grpc-use-token` в разработке скила не выполнялся — при первом использовании сначала `mic-status`, затем короткий файл (5–10 с) и проверка уровня записи в приложении.
