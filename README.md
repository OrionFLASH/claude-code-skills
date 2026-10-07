# claude-code-skills

Личная коллекция скилов для [Claude Code](https://claude.com/claude-code). Каждый скил — отдельный подпроект в `skills/<имя>/` и отдельный плагин в маркетплейсе `.claude-plugin/marketplace.json`.

Скилы универсальны: в них нет конкретных сайтов, репозиториев, логинов и токенов. Всё конкретное скил получает на входе при запуске.

## Скилы

<!-- skills-table:start -->
| Имя | Описание | Версия | Статус |
|-----|----------|--------|--------|
| [site-qa-audit](skills/site-qa-audit/) | Универсальный QA-аудит любого сайта через браузер: функциональность, логика, UX, UI, адаптивность, доступность, производительность, SEO, пассивная безопасность, продуктовые предложения; сверка с issues и публикация по правилам | 1.0.3 | стабильный |
<!-- skills-table:end -->

## Установка

### Через маркетплейс (обычное использование)

Репозиторий приватный, поэтому у git/gh на машине должен быть доступ к нему (`gh auth login`).

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

Скил ставится в `~/.claude/skills/<имя>`. Не держите один скил одновременно и симлинком, и плагином из маркетплейса — будет два одинаковых скила.

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
