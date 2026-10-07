<!--
Комментарий к существующему issue (роль comment). Варианты: FIXED-INSUFFICIENT, REGRESSION.
Стиль brief — только первые два блока и маркер. Язык — из run-config.
-->
### {{status_title}}
<!-- FIXED-INSUFFICIENT: «Проверка исправления: проблема воспроизводится частично»
     REGRESSION:         «Регрессия: проблема снова воспроизводится» -->

Проверено {{date}} ({{browser}} {{browser_version}}, {{viewport}}) на {{url}}.

**Что работает:** {{what_fixed}}
**Что по-прежнему не так:** {{what_remains}}
**Почему исправления недостаточно:** {{why_insufficient}}
<!-- для REGRESSION: «Было исправлено: {{fixed_ref}} (закрыт {{closed_at}}). Сейчас воспроизводится полностью.» -->

<details><summary>Шаги воспроизведения</summary>

{{steps_numbered}}

Ожидаемо: {{expected}}
Фактически: {{actual}}
</details>

{{screenshots_md}}
{{copy_link}}
<!-- REGRESSION: «Предлагаю переоткрыть issue.» — сам не переоткрывать без подтверждения пользователя -->

<!-- site-qa-audit:fp={{fingerprint}} -->
