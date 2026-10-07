# Самопроверка typesafe-triage

Тесты лежат рядом со скриптами (`scripts/test_*.py`), потому что импортируют соседние модули.

```bash
S=skills/typesafe-triage/scripts
python3 -m pytest $S -q -p no:cacheprovider      # офлайн: политика, защита, сквозные на поддельном сервере
python3 $S/typesafe_triage.py --selftest         # эталонные задачи triage_cases.json, нужны сеть и ключ
```

Ожидание: все тесты зелёные; в `--selftest` «ниже ожидаемого» и `DEVMISS` равны 0.
