# claude-code-skills

Личная коллекция скилов для [Claude Code](https://claude.com/claude-code). Каждый скил — отдельный подпроект в `skills/<имя>/` и отдельный плагин в маркетплейсе `.claude-plugin/marketplace.json`.

Скилы универсальны: в них нет конкретных сайтов, репозиториев, логинов и токенов. Всё конкретное скил получает на входе при запуске.

## Скилы

<!-- skills-table:start -->
| Имя | Описание | Версия | Статус |
|-----|----------|--------|--------|
| [android-qa-audit](skills/android-qa-audit/) | Универсальное QA-тестирование Android-приложений по APK, AAB или установленному пакету на эмуляторах и устройствах через adb: функциональность, логика, UX, UI, версии Android и конфигурации устройств (ОЗУ, ядра, экран, шрифт, тема, язык, сеть), жизненный цикл, доступность, производительность, пассивная безопасность, тексты; матрица стендов, до 4 потоков; звук в микрофон эмулятора, долгие сценарии с метриками, аннотированные скриншоты; черновики GitHub issues по их формам, со скриншотами веткой | 1.2.0 | в разработке |
| [site-qa-audit](skills/site-qa-audit/) | Универсальный QA-аудит любого сайта или локального веб-приложения (file://) через браузер: функциональность, логика, UX, UI, адаптивность, доступность, производительность, SEO, тексты и локализация, пассивная безопасность, продуктовые предложения; параллельные исполнители, сверка с issues, перепроверка исправлений, группы по первопричине и публикация по правилам | 1.4.0 | стабильный |
| [typesafe-triage](skills/typesafe-triage/) | Универсальный триаж любых задач через TypeSafe (Jev) и локальные сигналы: уровень модели haiku/sonnet/opus/fable, reasoning effort low…max и одно действие — сам, Agent или спросить (haiku, fable, low и max — только с подтверждения пользователя); проверка хука, пакетный режим, журнал фактов | 2.3.0 | стабильный |
<!-- skills-table:end -->

## Установка

Подробные инструкции «Установка и обновление» для macOS и Windows — с промптами, которые можно вставить в Claude Code, — лежат в каждом скиле: [android-qa-audit/INSTALL.md](skills/android-qa-audit/INSTALL.md) (с настройкой Android SDK и эмулятора), [site-qa-audit/INSTALL.md](skills/site-qa-audit/INSTALL.md), [typesafe-triage/INSTALL.md](skills/typesafe-triage/INSTALL.md).

### Через маркетплейс (обычное использование)

Репозиторий публичный, отдельный доступ не нужен (для приватного форка — `gh auth login`).

```text
/plugin marketplace add OrionFLASH/claude-code-skills
/plugin install <имя-скила>@claude-code-skills
```

Обновление: `/plugin marketplace update claude-code-skills`.

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
skills/<имя>/                    подпроект скила (SKILL.md, README, CHANGELOG, references/, templates/, scripts/, tests/)
shared/                          общее для нескольких скилов (скрипты, шаблон каркаса)
tools/                           install, new-skill, validate (sh + ps1, логика в tools/lib на Python stdlib)
```

Журнал изменений репозитория — [CHANGELOG.md](CHANGELOG.md).
