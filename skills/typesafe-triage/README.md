# typesafe-triage

Универсальный триаж **любых** задач (код, документы, письма, анализ, данные, исследование, планирование, ревью, ops, право, финансы, учёба): TypeSafe (модель Jev) отвечает на узкие вопросы, локальные сигналы считают текст, окружение и историю сессии, а код детерминированно выбирает **две независимые оси**:

- **модель** Claude — `haiku` < `sonnet` < `opus` < `fable` (способность исполнителя);
- **reasoning effort** — `low` < `medium` < `high` < `xhigh` < `max` (сколько думать).

Работает глобально через хук `UserPromptSubmit`: добавляет к запросу короткую заметку «модель + effort» и что с ней делать (`Agent(model=…, effort=…)`), а по команде `--run` сам запускает отдельного агента `claude -p --model … --effort …`.

- Без вопросов: `sonnet`/`opus` и `medium`/`high`/`xhigh`. **`haiku`, `fable`, `low`, `max` — только после подтверждения пользователя** (один `AskUserQuestion` на обе оси), иначе ближайшее безопасное: haiku → sonnet, fable → opus, low → medium, max → xhigh.
- Явные указания в тексте запроса («на opus», «effort max», «ultrathink», «тщательно», «кратко», "use haiku", "think hard") — согласие и приоритет; отрицания («не нужно глубоко») учитываются. Упоминания не считаются: слова в кавычках, коде, пересказе («ассистент ответил…») и во вставленных отчётах.
- Если у инструмента `Agent` нет параметра `effort` (бывает в части версий Claude Code), заметка не требует его: глубина задаётся готовой фразой в промпте агента, а для критичной изолируемой работы заметка даёт команду `--run` (`claude -p --effort …`).
- Повторы в сессии («опять не работает») поднимают effort (до +2 ступеней, не до max) и при втором повторе — модель на ступень (не выше opus).
- Без ответа TypeSafe (нет ключа, сеть, пауза защиты) обе оси выбирают локальные сигналы (sonnet/opus, medium..xhigh, «уверенность низкая»).
- Пропускаются короткие реплики и подтверждения, команды `/…`, служебные сообщения среды; повторный вызов хука на тот же запрос (ручной хук + хук плагина) молчит.

## Входные параметры
| Параметр | Обязательный | По умолчанию | Описание |
|----------|--------------|--------------|----------|
| `TYPESAFE_API_KEY` | нет (без него — только локальные сигналы) | — | ключ TypeSafe, переменная окружения (например, в `settings.json` → `env`) |
| `TYPESAFE_TRIAGE=off` | нет | — | выключить триаж полностью (или пустой файл `.typesafe-triage-off` в каталоге проекта или выше) |
| `.typesafe-triage-effort` | нет | — | файл в каталоге проекта: первое слово (`high`, `xhigh`…) — минимальный effort для проекта |
| `--set-budget USD` | нет | 2 | месячный потолок расходов на TypeSafe |
| `--confirmed` / `--confirmed-effort` (для `--run`) | нет | — | пользователь явно подтвердил haiku/fable / effort low/max |
| `--tier …` / `--effort …` (для `--run`) | нет | рекомендация | модель / effort вручную |

## Установка
Установка и обновление — одна инструкция [INSTALL.md](INSTALL.md): macOS, Linux, Windows, маркетплейс, ключ, хук, правило для CLAUDE.md, промпты для Claude Code (установка и обновление), проверка и откат. Кратко:

1. Поставить скил: `/plugin install typesafe-triage@claude-code-skills` (хук приходит с плагином: `hooks/hooks.json`) **или** `tools/install.sh typesafe-triage` (симлинк в `~/.claude/skills/typesafe-triage`, хук — вручную).
2. Задать `TYPESAFE_API_KEY`.
3. Для установки симлинком/копией — добавить хук в `~/.claude/settings.json`:

```json
"hooks": {
  "UserPromptSubmit": [
    { "hooks": [ { "type": "command", "timeout": 10,
      "command": "python3 \"$HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py\" --hook" } ] }
  ]
}
```

Если хук есть и в `settings.json`, и в плагине — заметка всё равно одна (второй вызов молчит), но лучше оставить один.

## Примеры вызова
```bash
S=~/.claude/skills/typesafe-triage/scripts
python3 $S/typesafe_triage.py --check
python3 $S/typesafe_triage.py "Сравни три предложения поставщиков и дай рекомендацию"   # JSON: model, effort, причины
python3 $S/typesafe_triage.py --signals "текст"                 # локальные сигналы и явные указания, без сети
python3 $S/typesafe_triage.py --run --edit --dry-run "текст задачи"   # claude -p --model … --effort … (haiku/fable, low/max понижаются)
python3 $S/typesafe_triage.py --run --tier fable --confirmed --effort max --confirmed-effort "…"  # только после явного согласия
python3 $S/typesafe_triage.py --calibrate --split holdout        # распределение effort и расхождения на отложенной части
```
Полный список команд и правила применения заметки — в [SKILL.md](SKILL.md); как считается модель — [references/levels.md](references/levels.md), effort — [references/effort.md](references/effort.md).

## Зависимости
Python 3, только стандартная библиотека; для тестов — `pytest`. Для точной оценки нужен аккаунт TypeSafe (без него работают локальные сигналы). Для `--run` — Claude Code CLI с опцией `--effort` (проверено на 2.1.292).

## Приватность и ограничения
- **В TypeSafe уходит каждый запрос от 40 символов любой тематики** (кроме реплик, команд и служебных сообщений) — дайджест до 4500 знаков, секреты маскируются; вопросы effort идут в том же запросе. Окружение проекта и история сессии считаются локально и никуда не отправляются. Где отправка недопустима — `.typesafe-triage-off` или `TYPESAFE_TRIAGE=off`. Подробнее — [references/privacy.md](references/privacy.md).
- Основную сессию Claude Code переключить нельзя (ни модель, ни effort) — совет применяется делегированием через `Agent(model=…, effort=…)`; для работы в самой сессии заметка может предложить `/effort …`. `effortLevel` в настройках не меняется.
- Защита от ухода баланса в минус и сбоев — [references/guard.md](references/guard.md). Модуль `typesafe_guard.py` используют и другие скилы.
- Состояние, журнал и метки идемпотентности: `~/.claude/typesafe-triage/`.
