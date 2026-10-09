# Самопроверка typesafe-triage

Тесты лежат рядом со скриптами (`scripts/test_*.py`), потому что импортируют соседние модули. `scripts/conftest.py` изолирует их от окружения запуска: модель и effort сессии, параметр effort у Agent и журнал проекта не берутся из переменных Claude Code и `~/.claude/settings.json`.

```bash
S=skills/typesafe-triage/scripts
python3 -m pytest $S -q -p no:cacheprovider      # офлайн: политика 4 уровней и 5 уровней effort, подтверждения, явные указания,
                                                 # история, окружение, идемпотентность хука, эвристика, защита,
                                                 # сквозные тесты хука на поддельном сервере;
                                                 # 2.2: хук не молчит (test_typesafe_hook_skip.py), --where, активная задача,
                                                 # наследование, тип qa, общее состояние (test_typesafe_context.py), документация;
                                                 # 2.3: строка «ДЕЙСТВИЕ», правила действия, модель сессии из стенограммы,
                                                 # «реже» (test_typesafe_action.py); регистрация хука, имя для Skill, «призраки»,
                                                 # синонимы (test_typesafe_install.py); --batch (test_typesafe_batch.py);
                                                 # журнал проекта и --fact (test_typesafe_projectlog.py);
                                                 # 2.4: автозапись факта хуком PostToolUse/SubagentStop, привязка к решению,
                                                 # ручной факт дополняет автоматический, счётчики и профиль сессии из служебных
                                                 # полей стенограммы, цена контекста (test_typesafe_autofact.py)
python3 $S/typesafe_triage.py --selftest --heuristic   # эталонные задачи только по эвристике (офлайн)
python3 $S/typesafe_triage.py --selftest         # эталонные задачи triage_cases.json через TypeSafe, нужны сеть и ключ
python3 $S/typesafe_triage.py --calibrate --split train     # подстройка порогов только по обучающей части …
python3 $S/typesafe_triage.py --calibrate --split holdout   # … и проверка на отложенной (~20 %)
```

Чтобы живой `--selftest` не трогал рабочее состояние в `~/.claude/typesafe-triage/`, задайте временный каталог: `TYPESAFE_TRIAGE_HOME=/tmp/ts-selftest`.

Ожидание: все тесты зелёные на Python 3.9 и 3.12+; в обоих `--selftest` «ниже ожидаемого» равно 0 и по модели, и по effort (код возврата 0).
