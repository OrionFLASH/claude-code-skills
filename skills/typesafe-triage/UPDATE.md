# Обновление typesafe-triage

Для тех, кто уже поставил скилл ([INSTALL.md](INSTALL.md)). Ключ, журнал и настройки лежат вне папки скилла (`~/.claude/typesafe-triage/`, Windows: `%USERPROFILE%\.claude\typesafe-triage\`) и при обновлении сохраняются.

## Быстрый способ: промпт для Claude Code

Вставьте в Claude Code на своей машине. Он сам найдёт установку, спросит что нужно, обновит и проверит.

````text
Обнови на этой машине скилл typesafe-triage до последней версии из публичного репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/typesafe-triage).
Ориентируйся на UPDATE.md в этой папке. Отвечай мне по-русски.

ПРАВИЛА
- Сначала разведка (только чтение), потом вопросы, затем действия.
- Ничего не удаляй: старую копию скилла переименуй в *.bak-ГГГГММДД. Перед правкой settings.json
  и CLAUDE.md сделай резервную копию рядом и покажи, что изменишь. JSON правь аккуратно
  (читай, дополняй, ничего не затирай, проверь парсером).
- Ключ TypeSafe не печатай и не проси присылать в чат; существующий ключ не трогай.
- Если права Claude Code не разрешают правку settings.json, не обходи запрет: покажи точный
  текст, я вставлю сам.

ШАГ 0. РАЗВЕДКА
1) Найди, где и как стоит скилл: ~/.claude/skills/typesafe-triage (симлинк или папка; для
   симлинка покажи, куда ведёт), .claude/skills проекта, плагин из маркетплейса
   (claude plugin list), клон репозитория.
2) Сравни текущую версию (.claude-plugin/plugin.json) с последней в репозитории. Если версии
   совпадают - скажи и остановись.
3) Найди хук typesafe_triage.py --hook в settings.json (глобальном и проектном) и его путь;
   проверь, нет ли ручного хука и плагинного одновременно (дубль); найди в CLAUDE.md
   (глобальном и проектном) раздел про триаж и строку про effort; проверь наличие
   TYPESAFE_API_KEY (только факт).
4) Определи ОС и рабочую команду Python 3 (python3, python, py -3).
Покажи краткую сводку.

ШАГ 1. ВОПРОСЫ (мне; через AskUserQuestion, по 1-3 за раз)
1) Обновить с версии X до Y?
2) Способ обновления (предложи подходящий по разведке): git pull в клоне, замена копии,
   обновление плагина из маркетплейса.
3) Если найден дубль хука - какой оставить?
4) Добавить в CLAUDE.md строку про effort (текст ниже), если её нет, или заменить старую
   безусловную («ставь effort=…») на условную?

ШАГ 2. ОБНОВЛЕНИЕ
- Симлинк на клон: git pull в клоне.
- Копия: переименуй старую папку в *.bak-ГГГГММДД, скопируй новую папку скилла без __pycache__.
- Маркетплейс: claude plugin marketplace update claude-code-skills, затем
  claude plugin update typesafe-triage@claude-code-skills (потом нужен перезапуск Claude Code).
- Путь хука в settings.json правь, только если он вёл в старую версионную папку плагина или
  если выбрано убрать дубль. Остальное в settings.json не трогай.
- Если я согласился, добавь в раздел про триаж в CLAUDE.md строку (старую строку про effort замени):
  - Заметка содержит и `effort` (low…max): если у `Agent` есть параметр effort — ставь `effort=<значение из заметки>`; если нет — не ссылайся на него (это не ошибка), глубину задай фразой в промпте агента из заметки, а для критичной изолируемой работы используй команду `--run` из заметки. `low` и `max` — только после подтверждения (один AskUserQuestion с моделью); нет «да» → medium / xhigh.

ШАГ 3. ПРОВЕРКА
- Версия после обновления совпадает с последней.
- Запусти: <python> <путь>/typesafe_triage.py --check (ключ не печатай). Если стоит пауза -
  покажи --status и спроси, снять ли (--resume).
- Проверь хук: echo '{"prompt":"Подготовь план миграции базы данных с проверкой отката","cwd":".","session_id":"upd1"}' | <python> <путь>/typesafe_triage.py --hook
  В JSON должна быть заметка «уровень … effort …».
- Итог: что обновлено (версии, пути), что изменено (с путями резервных копий), что осталось
  сделать вручную (перезапуск Claude Code), как откатить.
````

## Вручную

**Версия сейчас:**

```text
# macOS / Linux
grep '"version"' ~/.claude/skills/typesafe-triage/.claude-plugin/plugin.json
# Windows (PowerShell)
Select-String '"version"' $HOME\.claude\skills\typesafe-triage\.claude-plugin\plugin.json
```

**Обновление (по тому, как ставили):**

| Установка | Команды |
|---|---|
| Клон + симлинк (macOS / Linux) | `cd ~/dev/claude-code-skills && git pull` |
| Клон + копирование | `git pull` в клоне, затем переименовать старую папку скилла в `typesafe-triage.bak` и скопировать новую из `skills/typesafe-triage` |
| Маркетплейс | `/plugin marketplace update claude-code-skills`, затем `/plugin update typesafe-triage@claude-code-skills` (или `claude plugin update typesafe-triage@claude-code-skills`), перезапуск Claude Code |
| ZIP | скачать репозиторий заново, заменить папку `skills/typesafe-triage` в `~/.claude/skills/` |

**После обновления проверьте:**
1. Хук не дублируется: при установке плагином не держите ещё и ручной хук `typesafe_triage.py --hook` в `settings.json`. Если ручной хук ведёт в версионную папку плагина, поправьте путь.
2. В `CLAUDE.md` в разделе про триаж есть строка про `effort` (текст в промпте выше), и она условная: «если у Agent есть параметр effort». В части версий Claude Code у `Agent` такого параметра нет — Claude может написать, что передать effort не может; это нормально, с 2.1.2 заметка в этом случае даёт фразу глубины для промпта агента и, для критичных задач, команду `--run`.
3. `--check`:

```text
# macOS / Linux
python3 ~/.claude/skills/typesafe-triage/scripts/typesafe_triage.py --check
# Windows (PowerShell)
python $HOME\.claude\skills\typesafe-triage\scripts\typesafe_triage.py --check
```

**Откат:** верните переименованную папку `typesafe-triage.bak` на место. При установке из клона можно взять нужную версию по тегу `typesafe-triage/v<версия>`.
