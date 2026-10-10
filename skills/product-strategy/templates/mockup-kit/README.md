# Набор компонентов макетов (mockup-kit)

Стартовый набор для фазы 8 (`references/design.md`): оркестратор не пишет `_kit.css` с нуля, а копирует этот набор
и подставляет токены продукта. Все классы — с префиксом `ps-`.

## Файлы

| Файл | Куда копировать | Зачем |
|---|---|---|
| `_kit.css` | `<OUT>/mockups/concepts/_kit.css` | компоненты; токены `--c-*` берёт из `../tokens.css`, свои значения — только запасные (слой `ps-defaults`) |
| `_base.html` | `<OUT>/mockups/concepts/_base.html` (и как основа каждого `Mxx-<slug>.html`) | типовой экран: боковая навигация, верхняя панель, KPI, карточки, таблица, нижняя мобильная панель, бейдж концепта |
| `kit-demo.html` | `<OUT>/mockups/concepts/_kit-demo.html` | все компоненты в светлой и тёмной теме + автопроверка контраста |

Имена с `_` в начале shoot_mockups не добавляет в `data/mockups-index.json`; снять и проверить их можно так:

```
node <SKILL_DIR>/scripts/node/shoot_mockups.mjs <OUT> --kit
```

`--kit` снимает `_*.html` (полностраничные PNG рядом с HTML; для `data-viewports="1440x900,390x844"` — на каждой
ширине, суффикс `-390x844`) и пишет `data/mockups-check._kit-demo.json`. Проверка контраста в `kit-demo.html` пишет
каждое нарушение в консоль (`console.error`), поэтому замечание попадает в `console_errors`. Итог также в
`window.psContrast` и атрибуте `<html data-contrast="ok|fail:N">`. Посмотрите PNG через Read **до** раздачи макетов.

## Токены

`audit_site.mjs` пишет `<OUT>/mockups/tokens.css` с обеими темами: роли `--c-bg`, `--c-surface`, `--c-text`,
`--c-muted`, `--c-accent`, `--c-on-accent`, `--c-border`, `--radius`, `--radius-lg`, `--font`, `--font-heading`,
`--font-size`, `--shadow` и CSS custom properties продукта (`:root` и `[data-theme="dark"]`). Набор дополнительно
понимает `--c-success`, `--c-warning`, `--c-danger`, `--c-on-danger`, `--c-focus` (иначе — запасные значения).

Если `tokens.css` написан вручную и в нём нет блока `[data-theme="dark"]`, тёмные макеты возьмут светлые значения
продукта — добавьте блок или не делайте тёмных макетов. Производные цвета (мягкие фоны бейджей, «чернила» статусов)
считаются через `color-mix()` от токенов, поэтому контраст зависит от продукта: проверяйте `_kit-demo` с реальными
токенами.

## Темы и размеры

- Тёмная тема: `<html data-theme="dark">` или любой контейнер с `data-theme="dark"` (тема действует на поддерево —
  так `kit-demo.html` показывает обе темы на одной странице).
- Размер: `<html data-viewport="1440x900">` или `"390x844"`; раскладка мобильная при ширине ≤ 640 px (боковая
  навигация скрыта, сетки в одну колонку, видна `.ps-bottom-nav`). `.ps-g4.is-keep-2` — две колонки на телефоне.
- Связь с реестром: `<html data-proposals="P003,P017">` — shoot_mockups перенесёт в индекс при автообнаружении.

## Компоненты

Раскладка `.ps-app`, `.ps-rail` (боковая навигация: `.ps-brand`, `.ps-nav.is-active`, `.ps-nav-sep`), `.ps-main`,
`.ps-topbar` (= `.ps-top`), `.ps-page`, сетки `.ps-g2/.ps-g3/.ps-g4`, `.ps-row`, `.ps-stack`; карточка `.ps-card`
(`.is-accent`, `.is-flat`), `.ps-kpi`, `.ps-bar`, `.ps-steps`; кнопки `.ps-btn` + `.is-primary/.is-secondary/.is-danger/
.is-ghost/.is-small/.is-large`; поля `.ps-field`, `.ps-input` (`.is-error`), `.ps-hint`, `.ps-error`; сегментный
переключатель `.ps-segmented`; чипы-фильтры `.ps-chips > .ps-chip.is-active`; тумблер `.ps-switch` (input + `.ps-track`),
чекбокс `.ps-check`, радио `.ps-radio` (input + `.ps-box`); бейджи `.ps-badge` + `.is-success/.is-warning/.is-danger/
.is-neutral`; список `.ps-list > .ps-list-item`, `.ps-avatar`; таблица `.ps-table-wrap > .ps-table` (`.is-num`);
модальное окно `.ps-backdrop` (`.is-fixed` — на весь экран) `> .ps-modal`; пустое состояние `.ps-empty`; уведомления
`.ps-toast`, `.ps-alert` (+ статусы), `.ps-cookie`; закрытая функция `.ps-lock > .ps-lock-head + .ps-lock-body`;
выноска `.ps-tip` (`.is-floating` — абсолютная внутри `.ps-anchor`/`.ps-card`/`.ps-rail`/`.ps-page`); нижняя мобильная
панель `.ps-bottom-nav` (`.is-always` — показать и на десктопе); бейдж концепта `.ps-concept-badge` (`.is-top`,
`.is-above-nav`).

## Исправлено по сравнению с набором реального прогона

- бейдж концепта: `position: fixed`, одна строка (`white-space: nowrap` + многоточие), на мобильном с нижней панелью
  поднимается над ней автоматически (`body:has(.ps-bottom-nav)`), варианты `.is-top` и `.is-above-nav`;
- `.ps-badge` не выходит из капсулы (`nowrap`, `max-width: 100%`, многоточие);
- `.ps-btn.is-danger` — `--c-danger` с контрастом ≥ 4,5:1 в обеих темах (светлая: белый на `#b42318` ≈ 6,6:1;
  тёмная: тёмный текст на `#f97066`);
- `.ps-lock`: штриховка только поверх `.ps-lock-body`, заголовок `.ps-lock-head` всегда читается;
- `.ps-tip` по умолчанию в потоке (`position: relative`), плавающая — только `.is-floating`; `.ps-rail`, `.ps-card`,
  `.ps-main`, `.ps-page`, `.ps-topbar` — `position: relative`, выноски не уезжают;
- добавлены сегментный переключатель, чипы, тумблер, чекбокс, радио, список, алерты, тёмная тема.
