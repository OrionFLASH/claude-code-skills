# typesafe-triage

Триаж задач разработки через TypeSafe (модель Jev): код по типизированным ответам выбирает уровень модели Claude (`haiku` / `sonnet` / `opus`, Fable — никогда) и при необходимости запускает отдельного агента на этом уровне. Работает глобально через хук `UserPromptSubmit`.

## Входные параметры
| Параметр | Обязательный | По умолчанию | Описание |
|----------|--------------|--------------|----------|
| `TYPESAFE_API_KEY` | да | — | ключ TypeSafe, переменная окружения (например, в `settings.json` → `env`) |
| `TYPESAFE_TRIAGE=off` | нет | — | выключить триаж (или пустой файл `.typesafe-triage-off` в каталоге проекта) |
| `--set-budget USD` | нет | 2 | месячный потолок расходов |

## Установка
1. Поставить скил: `/plugin install typesafe-triage@claude-code-skills` или `tools/install.sh typesafe-triage` (симлинк в `~/.claude/skills/typesafe-triage`).
2. Задать `TYPESAFE_API_KEY`.
3. Добавить хук в `~/.claude/settings.json` (плагином он не ставится):

```json
"hooks": {
  "UserPromptSubmit": [
    { "hooks": [ { "type": "command",
      "command": "python3 \"$HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py\" --hook" } ] }
  ]
}
```

Если скил поставлен плагином, путь в команде — каталог плагина (`~/.claude/plugins/cache/...`); для постоянного пути используйте `tools/install.sh`.

## Примеры вызова
```bash
S=~/.claude/skills/typesafe-triage/scripts
python3 $S/typesafe_triage.py --check
python3 $S/typesafe_triage.py "текст задачи"
python3 $S/typesafe_triage.py --run --edit "текст задачи"
```
Полный список команд — в [SKILL.md](SKILL.md).

## Зависимости
Python 3, только стандартная библиотека; для тестов — `pytest`. Нужен аккаунт TypeSafe.

## Ограничения
- Каждый запрос от 40 символов уходит в TypeSafe (дайджест до 4500 знаков, секреты маскируются).
- Основную сессию Claude Code переключить нельзя — совет применяется делегированием через `Agent`.
- Состояние и журнал: `~/.claude/typesafe-triage/`.
