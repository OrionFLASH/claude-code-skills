# typesafe-triage

Универсальный триаж **любых** задач (код, документы, письма, анализ, данные, исследование, планирование, ревью, ops): TypeSafe (модель Jev) отвечает на узкие вопросы-шкалы, локальные эвристики считают сигналы по тексту, а код детерминированно выбирает уровень модели Claude — `haiku` < `sonnet` < `opus` < `fable` — и при необходимости запускает отдельного агента на этом уровне. Работает глобально через хук `UserPromptSubmit`: добавляет к запросу короткую заметку, что делать с этим уровнем.

- `sonnet` и `opus` применяются без вопросов; **`haiku` и `fable` — только после подтверждения пользователя** (`AskUserQuestion`), иначе ближайший безопасный: haiku → sonnet, fable → opus.
- Без ответа TypeSafe (нет ключа, сеть, пауза защиты) уровень выбирает локальная эвристика (только sonnet/opus, пометка «уверенность низкая»).
- Пропускаются короткие реплики и подтверждения, команды `/…`, служебные сообщения среды.

## Входные параметры
| Параметр | Обязательный | По умолчанию | Описание |
|----------|--------------|--------------|----------|
| `TYPESAFE_API_KEY` | нет (без него — только эвристика) | — | ключ TypeSafe, переменная окружения (например, в `settings.json` → `env`) |
| `TYPESAFE_TRIAGE=off` | нет | — | выключить триаж полностью (или пустой файл `.typesafe-triage-off` в каталоге проекта или выше) |
| `--set-budget USD` | нет | 2 | месячный потолок расходов на TypeSafe |
| `--confirmed` (для `--run`) | нет | — | пользователь явно подтвердил haiku/fable |

## Установка
Подробная пошаговая инструкция (macOS, Linux, Windows, маркетплейс, ключ, хук) — в [INSTALL.md](INSTALL.md). Кратко:

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
python3 $S/typesafe_triage.py "Сравни три предложения поставщиков и дай рекомендацию"
python3 $S/typesafe_triage.py --signals "текст"                 # локальные сигналы, без сети
python3 $S/typesafe_triage.py --run --edit "текст задачи"        # haiku/fable будут понижены до sonnet/opus
python3 $S/typesafe_triage.py --run --tier fable --confirmed "…"  # только после явного согласия пользователя
```
Полный список команд и правила применения заметки — в [SKILL.md](SKILL.md); как считается уровень — [references/levels.md](references/levels.md).

## Зависимости
Python 3, только стандартная библиотека; для тестов — `pytest`. Для точной оценки нужен аккаунт TypeSafe (без него работает эвристика).

## Приватность и ограничения
- **В TypeSafe уходит каждый запрос от 40 символов любой тематики** (кроме реплик, команд и служебных сообщений) — дайджест до 4500 знаков, секреты маскируются, файлы и данные проекта не отправляются. Где это недопустимо — `.typesafe-triage-off` или `TYPESAFE_TRIAGE=off`. Подробнее — [references/privacy.md](references/privacy.md).
- Основную сессию Claude Code переключить нельзя — совет применяется делегированием через `Agent`.
- Защита от ухода баланса в минус и сбоев — [references/guard.md](references/guard.md). Модуль `typesafe_guard.py` используют и другие скилы.
- Состояние и журнал: `~/.claude/typesafe-triage/`.
