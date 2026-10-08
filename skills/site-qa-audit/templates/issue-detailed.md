<!--
Подробный шаблон для репозитория-копии (роль copies). Плейсхолдеры {{…}} заполняются из findings.json.
Заголовок issue: [{{severity_upper}}] {{title}}
Пустые секции удалять целиком. Всё — после маскирования (safety-rules.md §5).
-->
## Кратко
{{actual_one_line}}

| | |
|---|---|
| **Severity** | {{severity}} |
| **Направление** | {{direction}} (`{{check_id}}`) |
| **Тип** | {{type}} |
| **Статус сверки** | {{status}}{{status_links}} |
| **Частота** | {{frequency_text}} |
| **Аккаунт** | {{account_state}} |
| **Платформа** | {{platform}} |
| **URL** | {{url}} |
| **Элемент** | `{{element}}` |
| **Внешняя оценка** | {{triage_text}} |
| **Источник** | {{sources}} |
| **Прогон** | {{run_id}} ({{depth}}) |

## Заявленное исправление
{{claim_md}}

## Шаги воспроизведения
{{steps_numbered}}

## Ожидаемый результат
{{expected}}

## Фактический результат
{{actual}}

## Окружение
- Браузер: {{browser}} {{browser_version}}
- Экран: {{viewport}}
- ОС: {{os}}
- Авторизация: {{auth}}
- Дата проверки: {{date}}
- Воспроизводится также: {{environment_list}}

## Доказательства
{{screenshots_md}}

<details><summary>Консоль</summary>

```text
{{console}}
```
</details>

<details><summary>Сеть</summary>

| Метод | URL | Статус |
|---|---|---|
{{network_rows}}
</details>

<details><summary>Данные проверки</summary>

```json
{{evidence_json}}
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
_Создано site-qa-audit. Проверка через браузер без доступа к исходному коду; причина — гипотеза._
<!-- site-qa-audit:fp={{fingerprint}} -->
