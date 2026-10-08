# Самопроверка typesafe-triage

Тесты лежат рядом со скриптами (`scripts/test_*.py`), потому что импортируют соседние модули.

```bash
S=skills/typesafe-triage/scripts
python3 -m pytest $S -q -p no:cacheprovider      # офлайн: политика 4 уровней и 5 уровней effort, подтверждения, явные указания,
                                                 # история, окружение, идемпотентность хука, эвристика, защита,
                                                 # сквозные тесты хука на поддельном сервере
python3 $S/typesafe_triage.py --selftest --heuristic   # эталонные задачи только по эвристике (офлайн)
python3 $S/typesafe_triage.py --selftest         # эталонные задачи triage_cases.json через TypeSafe, нужны сеть и ключ
python3 $S/typesafe_triage.py --calibrate --split train     # подстройка порогов только по обучающей части …
python3 $S/typesafe_triage.py --calibrate --split holdout   # … и проверка на отложенной (~20 %)
```

Чтобы живой `--selftest` не трогал рабочее состояние в `~/.claude/typesafe-triage/`, задайте временный каталог: `TYPESAFE_TRIAGE_HOME=/tmp/ts-selftest`.

Ожидание: все тесты зелёные; в обоих `--selftest` «ниже ожидаемого» равно 0 и по модели, и по effort (код возврата 0).
