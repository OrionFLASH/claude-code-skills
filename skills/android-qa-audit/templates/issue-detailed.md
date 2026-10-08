<!--
Подробный шаблон issue android-qa-audit (роль copies или репозиторий без своего шаблона).
Плейсхолдеры {{…}} заполняет scripts/render_draft.py из findings.json. Заголовок: [{{severity_upper}}] {{title}}
Пустые секции удаляются целиком. Всё — после маскирования (references/safety-rules.md §5).
-->
## Кратко
{{actual_one_line}}

| | |
|---|---|
| **Severity** | {{severity}} |
| **Направление** | {{direction}} (`{{check_id}}`) |
| **Тип** | {{type}} |
| **Статус сверки** | {{status}}{{status_links}} |
| **Приложение** | {{app}} |
| **Экран** | `{{screen}}` |
| **Элемент** | `{{element}}` |
| **Воспроизводимость** | {{repro_text}} |
| **Источник** | {{sources}} |
| **Прогон** | {{run_id}} ({{depth}}) |

## Шаги воспроизведения
{{steps_numbered}}

## Ожидаемый результат
{{expected}}

## Фактический результат
{{actual}}

## Окружение
- Android: {{android}}
- Устройство: {{device}}
- Экран: {{screen_cfg}}
- Настройки: {{settings}}
- Стенд: {{stand}}
- Дата проверки: {{date}}
- Воспроизводится также: {{environment_list}}

## Падение или ANR
{{crash_md}}

## Доказательства
{{screenshots_md}}
{{recordings_md}}

<details><summary>logcat</summary>

```text
{{logcat_excerpt}}
```
</details>

<details><summary>Метрики</summary>

```json
{{metrics_json}}
```
</details>

## Правовые нормы
{{legal_md}}

## Гипотеза причины
{{hypothesis}}

## Предложение
{{suggestion}}

## Связанные issues
{{related_links}}

---
_Создано android-qa-audit. Проверка через интерфейс приложения и adb без доступа к исходному коду; причина — гипотеза._
<!-- android-qa-audit:fp={{fingerprint}} -->
