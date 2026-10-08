# Установка typesafe-triage

Скилл выбирает уровень модели Claude (haiku / sonnet / opus / fable) для каждой задачи через TypeSafe и подсказывает Claude, кому её делегировать. Работает через хук `UserPromptSubmit`: скилл и хук ставятся отдельно.

## Быстрый способ: попросите Claude Code всё сделать за вас

Откройте Claude Code в любой папке и вставьте промпт ниже целиком. Claude сам определит ОС, задаст вопросы (куда и как ставить), поставит скилл, пропишет хук и проверит работу. Ключ в чат присылать не нужно: его вы вставляете сами в файл настроек (Claude покажет, куда).

````text
Установи на этой машине скилл typesafe-triage из публичного репозитория
https://github.com/OrionFLASH/claude-code-skills (папка skills/typesafe-triage).
Ориентируйся на файл INSTALL.md внутри этой папки (прочитай его первым) и на
README.md/SKILL.md скилла. Отвечай мне по-русски.

ПРАВИЛА
- Ничего не делай, пока я не ответил на вопросы ниже. Задай их через AskUserQuestion
  (или обычным списком, если инструмента нет), максимум по 1-3 вопроса за раз.
- Перед правкой любого существующего файла (settings.json, CLAUDE.md) покажи, что именно
  добавишь, и сделай резервную копию рядом (файл.bak-ГГГГММДД). JSON правь аккуратно:
  читай существующий, добавляй свои ключи, ничего не затирай; результат проверь парсером.
  Если уже есть блок hooks/UserPromptSubmit или env - допиши в него, а не создавай второй.
- Ключ TypeSafe не проси присылать в чат и не печатай его в выводе. Создай место для ключа
  (пустое значение-заглушка "ВСТАВЬТЕ_КЛЮЧ") и скажи мне, какой файл открыть и что вписать.
  Ключ берётся на https://console.typesafe.ai (нужен аккаунт и баланс).
- Не публикуй и не коммить ключ. Если файл настроек лежит внутри git-репозитория проекта,
  предупреди об этом и предложи settings.local.json.
- Не делай ничего вне выбранных мной мест. Если права Claude Code не разрешают правку
  settings.json, не обходи запрет: покажи мне точный текст, чтобы я вставил его сам.

ШАГ 0. РАЗВЕДКА (без вопросов, только чтение)
- Определи ОС и оболочку; найди рабочую команду Python 3 из: python3, python, py -3
  (запусти --version у каждой). Запомни, какая работает - она пойдёт в команду хука.
- Проверь, есть ли git, уже ли стоит скилл typesafe-triage (в ~/.claude/skills,
  .claude/skills проекта, в плагинах), есть ли хук с typesafe_triage.py в settings.json,
  есть ли уже TYPESAFE_API_KEY в env. Покажи мне краткую сводку.

ШАГ 1. ВОПРОСЫ (мне)
1) Где ставить: глобально для всех проектов (папка ~/.claude, Windows %USERPROFILE%\.claude)
   или только в текущий проект (папка .claude внутри проекта)?
2) Как ставить: (а) маркетплейс плагинов (/plugin marketplace add ... - хук тогда нужно
   будет прописать вручную, путь зависит от версии), (б) клонировать репозиторий и скопировать
   папку скилла (постоянный путь, рекомендуется), (в) только скопировать папку без git.
   Если выбран пункт (а) или уже есть установленная копия - предупреди о дубле.
3) Куда положить ключ TYPESAFE_API_KEY: в settings.json -> env (глобальный или проектный
   settings.local.json), в переменную окружения системы, или я добавлю ключ позже сам?
4) Включить хук UserPromptSubmit, который добавляет к каждому запросу заметку
   «TypeSafe-триаж» (уровень модели)? Напомни, что в TypeSafe уходит дайджест каждого
   запроса длиннее 40 символов (секреты маскируются) и как выключить: файл
   .typesafe-triage-off в папке проекта или TYPESAFE_TRIAGE=off.
5) Добавить в CLAUDE.md (глобальный или проектный) короткое правило «выполнять заметку
   TypeSafe-триаж без напоминаний» (текст возьми из INSTALL.md, шаг 5)?
6) Если скилл с таким именем уже есть - заменить (старую копию переименуй в *.bak-ГГГГММДД,
   не удаляй), оставить или отменить?

ШАГ 2. УСТАНОВКА (по моим ответам)
- Скопируй скилл в выбранное место: <корень .claude>/skills/typesafe-triage
  (клонирование - во временную папку или ~/dev/claude-code-skills; на macOS/Linux можно
  tools/install.sh typesafe-triage вместо копирования). Не оставляй в копии __pycache__.
- Пропиши в выбранный settings.json: env.TYPESAFE_API_KEY (заглушка или значение, которое
  я укажу сам) и хук UserPromptSubmit с командой вида
  <рабочий python> "<ПОЛНЫЙ путь>/skills/typesafe-triage/scripts/typesafe_triage.py" --hook
  (timeout 10). На Windows - прямые слеши и полный путь вместо $HOME. Для проектной установки
  путь - к папке проекта.
- Если выбрал CLAUDE.md - добавь раздел из INSTALL.md, не трогая остальное содержимое.

ШАГ 3. ПРОВЕРКА
- Запусти: <python> <путь>/typesafe_triage.py --check и покажи вывод (ключ не печатай).
  Если ключ ещё не вписан - скажи об этом и покажи, как вписать, затем повтори проверку.
- Запусти офлайн-тесты, если установлен pytest: python -m pytest <путь>/scripts -q -p no:cacheprovider
  (необязательно).
- Проверь хук без сети: echo '{"prompt":"Подготовь план миграции базы данных с проверкой отката","cwd":"."}' | <python> <путь>/typesafe_triage.py --hook
  Должен вернуться JSON (при отсутствии ключа допустимо пустой вывод).
- Скажи мне итог: что установлено и где, что изменено (с путями резервных копий), что мне
  осталось сделать вручную (вписать ключ, перезапустить Claude Code), как откатить
  (вернуть .bak, удалить папку скилла и блок хука).
````

Если у Claude Code нет доступа в интернет или к GitHub, скачайте репозиторий ZIP-ом, распакуйте и добавьте в промпт строку «Репозиторий уже лежит в папке <путь>».

## Что понадобится
- Claude Code.
- Python 3 (только стандартная библиотека, `pip` не нужен). Проверка: macOS/Linux — `python3 --version`, Windows — `python --version` (или `py -3 --version`).
- Git (для способов 1 и 2).
- Ключ TypeSafe: https://console.typesafe.ai → создать API-ключ, пополнить баланс. Расход небольшой, по умолчанию стоит потолок $2 в месяц.

## Шаг 1. Поставить скилл (один из способов)

**Способ 1. Маркетплейс** (в Claude Code, любая ОС):

```text
/plugin marketplace add OrionFLASH/claude-code-skills
/plugin install typesafe-triage@claude-code-skills
```

Обновление: `/plugin marketplace update claude-code-skills`. Файлы лежат в `~/.claude/plugins/cache/…/typesafe-triage/<версия>/`; **эта папка меняется при обновлении**.

**Способ 2. Клонирование (постоянный путь, рекомендуется для хука)**

macOS / Linux:

```bash
git clone https://github.com/OrionFLASH/claude-code-skills.git ~/dev/claude-code-skills
cd ~/dev/claude-code-skills && tools/install.sh typesafe-triage
```

Windows (PowerShell):

```powershell
git clone https://github.com/OrionFLASH/claude-code-skills.git $HOME\dev\claude-code-skills
New-Item -ItemType Directory -Force $HOME\.claude\skills | Out-Null
Copy-Item -Recurse $HOME\dev\claude-code-skills\skills\typesafe-triage $HOME\.claude\skills\typesafe-triage
```

Обновление: `git pull` и повторить установку (на macOS/Linux симлинк подхватит сам).

**Способ 3. Архив:** скачайте репозиторий как ZIP на GitHub и скопируйте папку `skills/typesafe-triage` в `~/.claude/skills/` (Windows: `%USERPROFILE%\.claude\skills\`).

Не ставьте один и тот же скилл двумя способами одновременно — будет дубль.

## Шаг 2. Ключ

Ключ задаётся переменной окружения `TYPESAFE_API_KEY`. Самый простой и переносимый путь — файл настроек Claude Code:

| ОС | Файл |
|---|---|
| macOS / Linux | `~/.claude/settings.json` |
| Windows | `%USERPROFILE%\.claude\settings.json` |

```json
{
  "env": {
    "TYPESAFE_API_KEY": "ваш_ключ"
  }
}
```

Если блок `env` уже есть, допишите строку в него. Ключ нигде не публикуйте и не коммитьте. Альтернатива — системная переменная окружения (Windows: `setx TYPESAFE_API_KEY "ваш_ключ"`, затем перезапустить Claude Code).

## Шаг 3. Хук (без него заметки «TypeSafe-триаж» не появятся)

Скилл, поставленный любым способом, сам хук в `settings.json` **не добавляет**. Добавьте в тот же файл `settings.json`:

macOS / Linux, способ 1 или 2 через `tools/install.sh`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ {
        "type": "command",
        "command": "python3 \"$HOME/.claude/skills/typesafe-triage/scripts/typesafe_triage.py\" --hook",
        "timeout": 10
      } ] }
    ]
  }
}
```

Windows (имя пользователя подставьте своё, слеши прямые):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ {
        "type": "command",
        "command": "python \"C:/Users/ИМЯ/.claude/skills/typesafe-triage/scripts/typesafe_triage.py\" --hook",
        "timeout": 10
      } ] }
    ]
  }
}
```

Если блок `hooks`/`UserPromptSubmit` уже есть, добавьте элемент в существующий массив, а не заводите второй блок.

Если скилл поставлен через маркетплейс (способ 1), путь в команде должен вести в папку плагина в `~/.claude/plugins/cache/…`; после обновления версия в пути меняется, и хук придётся поправить. Поэтому для хука надёжнее способ 2.

### Что известно про хуки плагинов (по документации Claude Code)
- Плагин **может** нести свои хуки: файл `hooks/hooks.json` в корне плагина с путём `${CLAUDE_PLUGIN_ROOT}/…`; после `/plugin install` они включаются без правки `settings.json`. Этот плагин такого файла пока **не содержит**, поэтому хук ставится вручную, как выше.
- Если один и тот же хук будет и в `settings.json`, и в плагине, выполнятся **оба** (дубль). Оставляйте один.
- На Windows команда хука выполняется в Git Bash (а если его нет — в PowerShell). Какой именно Python-запуск переносим (`python`, `python3`, `py`), документация не уточняет: проверьте у себя командой из шага 4.

## Шаг 4. Проверка

Перезапустите Claude Code и выполните:

```text
# macOS / Linux
python3 ~/.claude/skills/typesafe-triage/scripts/typesafe_triage.py --check
# Windows (PowerShell)
python $HOME\.claude\skills\typesafe-triage\scripts\typesafe_triage.py --check
```

Должно быть «ключ: есть» и ответ сервиса. Затем отправьте в Claude Code любую задачу длиннее 40 символов: в контексте запроса появится заметка «TypeSafe-триаж: уровень …».

## Шаг 5 (по желанию). Применение без напоминаний

Добавьте в `~/.claude/CLAUDE.md` (Windows: `%USERPROFILE%\.claude\CLAUDE.md`):

```markdown
## Триаж модели (TypeSafe)
- Если в запросе есть заметка «TypeSafe-триаж», выполняй её всегда, без напоминаний.
- Содержательная работа, где уровень выше моей модели, или большая изолируемая задача: Agent с model=<уровень> и самодостаточным промптом.
- Уровни haiku и fable только после подтверждения через AskUserQuestion; нет «да» → sonnet/opus.
- Субагентам скилл typesafe-triage не применять.
```

## Приватность и выключатели
- В TypeSafe уходит дайджест каждого запроса длиннее 40 символов (до 4500 знаков; ключи, токены и пароли заменяются на «[скрыто]»). Файлы проекта не отправляются.
- Отключить в проекте: пустой файл `.typesafe-triage-off` в папке проекта. Отключить везде: переменная `TYPESAFE_TRIAGE=off`.
- Состояние, журнал и потолок расходов: `~/.claude/typesafe-triage/` (Windows: `%USERPROFILE%\.claude\typesafe-triage\`). Статус: `… typesafe_triage.py --status`.

## Если не работает
| Симптом | Что проверить |
|---|---|
| Заметок нет | хук в `settings.json`, перезапуск Claude Code, `--check`, запрос длиннее 40 символов |
| «ключ: нет» | `TYPESAFE_API_KEY` в `env` или в окружении |
| На Windows хук молчит | `python` в PATH; попробуйте `py -3` в команде хука; полный путь с прямыми слешами |
| Пауза / нет средств | `--status`, пополнить баланс на console.typesafe.ai, затем `--resume` |
| Ошибка сертификатов | `--check`: у сборки Python может не быть корневых сертификатов |

Подробности — в [SKILL.md](SKILL.md) и [README.md](README.md).
