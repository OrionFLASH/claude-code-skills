# claude-code-skills

Личная коллекция скилов для [Claude Code](https://claude.com/claude-code). Каждый скил — отдельный подпроект в `skills/<имя>/` и отдельный плагин в маркетплейсе `.claude-plugin/marketplace.json`.

Скилы универсальны: в них нет конкретных сайтов, репозиториев, логинов и токенов. Всё конкретное скил получает на входе при запуске.

## Скилы

<!-- skills-table:start -->
| Имя | Описание | Версия | Статус |
|-----|----------|--------|--------|
| [android-qa-audit](skills/android-qa-audit/) | Универсальное QA-тестирование Android-приложений по APK, AAB или установленному пакету на эмуляторах и устройствах через adb: функциональность, логика, UX, UI, версии Android и конфигурации устройств (ОЗУ, ядра, экран, шрифт, тема, язык, сеть), жизненный цикл, доступность, производительность, пассивная безопасность, тексты; матрица стендов, до 4 потоков; звук в микрофон эмулятора, долгие сценарии с метриками, аннотированные скриншоты и короткие ролики находок без звука; черновики GitHub issues по их формам, со скриншотами веткой | 1.5.0 | в разработке |
| [product-strategy](skills/product-strategy/) | Подробнейшая стратегия развития продукта по текущему репозиторию: опрос владельца, проверка и установка инструментов, анализ кода и приложения, конкуренты, сообщества, спрос, право; реестр 50–200 предложений с оценками (RICE, ICE, WSJF, Кано, чувствительность, TypeSafe), план на месяцы и видение на годы, юнит-экономика, Гант, Kanban, макеты и референсы дизайна, интерактивная веб-страница, XLSX, PPTX, PDF | 1.1.0 | в разработке |
| [site-qa-audit](skills/site-qa-audit/) | Универсальный QA-аудит любого сайта или локального веб-приложения (file://) через браузер: функциональность, логика, UX, UI, адаптивность, доступность, производительность, SEO, тексты и локализация, пассивная безопасность, продуктовые предложения; параллельные исполнители, сверка с issues, перепроверка исправлений, группы по первопричине и публикация по правилам | 1.7.0 | стабильный |
| [typesafe-triage](skills/typesafe-triage/) | Универсальный триаж любых задач через TypeSafe (Jev) и локальные сигналы: уровень модели haiku/sonnet/opus/fable, reasoning effort low…max и одно действие — сам, Agent или спросить (haiku, fable, low и max — только с подтверждения пользователя); проверка хука, пакетный режим, журнал фактов и их автозапись после субагента (опция) | 2.9.2 | стабильный |
<!-- skills-table:end -->

## Установка

Подробные инструкции «Установка и обновление» для macOS и Windows — с промптами, которые можно вставить в Claude Code, — лежат в каждом скиле: [android-qa-audit/INSTALL.md](skills/android-qa-audit/INSTALL.md) (с настройкой Android SDK и эмулятора), [site-qa-audit/INSTALL.md](skills/site-qa-audit/INSTALL.md), [typesafe-triage/INSTALL.md](skills/typesafe-triage/INSTALL.md).

### Через маркетплейс (обычное использование)

Репозиторий публичный, отдельный доступ не нужен (для приватного форка — `gh auth login`).

```text
/plugin marketplace add OrionFLASH/claude-code-skills
/plugin install <имя-скила>@claude-code-skills
```

### Обновление

Для каждого установленного скила; после этого — перезапуск Claude Code (новая версия и хуки плагинов видны только в новой сессии, либо `/reload-plugins`):

```text
/plugin marketplace update claude-code-skills
/plugin update <имя-скила>@claude-code-skills
```

То же в терминале: `claude plugin marketplace update claude-code-skills`, `claude plugin update <имя-скила>@claude-code-skills`. Версии — `claude plugin list`. Что нужно после обновления:

| Скил | Что сделать |
|------|-------------|
| `site-qa-audit` | в папке новой версии `cd scripts/node && npm install` (и `npx playwright install …`, если сменилась версия `playwright`); `SITE_QA_AUDIT_DIR`, если задана, поменять на новую папку. С 1.7.0 для коротких роликов находок рекомендуется ffmpeg (`brew install ffmpeg`); без него ролики сохраняются несжатыми |
| `android-qa-audit` | `npm install` в `scripts/node` — только для аннотаций скриншотов. С 1.5.0 для коротких роликов находок рекомендуется ffmpeg (`brew install ffmpeg`); без него ролики сохраняются несжатыми |
| `typesafe-triage` | `python3 <папка скилла>/scripts/typesafe_triage.py --check` (ключ, хук, имя для `Skill`) |

Старые папки версий остаются в кэше плагинов (`~/.claude/plugins/cache/claude-code-skills/<скил>/<версия>/`) — это нормально. Ключи, результаты прогонов и журналы лежат вне папки скила и при обновлении сохраняются.

### Хуки плагинов и принудительный запуск

Хуки приходят вместе с плагином (`hooks/hooks.json`) и работают только при установке плагином; у симлинка или копии хука нет (слэш-вызов скила работает всегда).

| Скил | Хук | Принудительный запуск |
|------|-----|-----------------------|
| `typesafe-triage` | заметка «ДЕЙСТВИЕ: …» к каждому запросу | слэш `/typesafe-triage:typesafe-triage <задача>`, метка `triage:` / `!триаж opus/high`, фраза «сделай триаж» — снимают пропуски хука |
| `site-qa-audit` | строка «ЯВНЫЙ ВЫЗОВ» (без вопроса о намерении) | метка `!qa` / `qa:` / `!site-qa` с опциями `autopilot`, `smoke`/`standard`/`deep`, фраза «запусти скилл site-qa-audit» |
| `android-qa-audit` | то же | `!qa` / `qa:` / `!android-qa`, фраза «запусти скилл android-qa-audit»; `!qa` без названия выбирает скил по содержимому (URL → site, APK → android) |

Публикацию в GitHub метки не включают. Подробности — `SKILL.md`, `README.md` и `INSTALL.md` скила.

### Симлинками (разработка)

Правки в репозитории подхватываются сразу, без переустановки.

```bash
tools/install.sh               # все скилы
tools/install.sh site-qa-audit # выбранные
tools/install.sh --uninstall site-qa-audit
```

```powershell
tools\install.ps1                 # на Windows создаются junction
tools\install.ps1 site-qa-audit
```

Скил ставится в `~/.claude/skills/<имя>`. Не держите один скил одновременно и симлинком, и плагином из маркетплейса — будет два одинаковых скила. После установки у скила могут быть свои шаги (Node-зависимости, хук, ключ) — см. его `INSTALL.md`.

## Новый скил

```bash
tools/new-skill.sh my-skill "Короткое описание"
```

Создаёт каркас по [CONVENTIONS.md](CONVENTIONS.md), добавляет скил в таблицу выше и в `marketplace.json`.

## Проверка перед коммитом

```bash
tools/validate.sh          # все скилы
tools/validate.sh my-skill # один
```

Проверяет frontmatter, README, CHANGELOG, plugin.json, запись в marketplace.json и таблице, отсутствие секретов.

## Структура

```text
.claude-plugin/marketplace.json  каталог плагинов
skills/<имя>/                    подпроект скила (SKILL.md, README, INSTALL, CHANGELOG, references/, templates/, scripts/, hooks/, tests/)
shared/                          общее для нескольких скилов (скрипты, шаблон каркаса)
tools/                           install, new-skill, validate (sh + ps1, логика в tools/lib на Python stdlib)
```

Журнал изменений репозитория — [CHANGELOG.md](CHANGELOG.md).
