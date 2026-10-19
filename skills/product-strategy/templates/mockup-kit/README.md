# Набор компонентов макетов (mockup-kit)

Стартовый набор для фазы 8 (`references/design.md`), версия 1.3. Набор копирует **скрипт** — однократно и
идемпотентно, до волны макетов: `python3 <SKILL_DIR>/scripts/mockup_kit.py init <OUT> [--forms web,mobile|mobile-later]
[--modes a,b]` (копирует файлы, создаёт `M00-design-language.html` с демо всех форм продукта, пустой `tokens.css`,
`tokens-<режим>.css` и замок `build/kit.lock`). Агенты макетов набор не копируют и не меняют — `mockup_kit.py verify <OUT>`
сверяет файлы с замком после волны. Все классы — с префиксом `ps-`.

## Бейдж концепта — одно правило и одна константа

Текст бейджа во всех шаблонах и брифах — константа **`Концепт, не существующая функция`** (+ ` · <продукт> · <дата>`);
в режиме идеи текст тот же. Элемент — всегда с классом `.ps-concept-badge` (`shoot_mockups.mjs` ищет бейдж по классу,
текст не сравнивает; старые макеты без класса находятся по тексту с предупреждением). Где ставить:

| Экран | Класс | Почему |
|---|---|---|
| телефон (`.pm-phone`, в том числе кадры раскадровки) | `ps-concept-badge is-strip` первым элементом телефона | полоса над строкой состояния, снимок кадра можно вырезать без потери пометки; текст в одну строку — не влезает 390 px: убрать дату, затем название |
| десктоп с нижней панелью (`.ps-bottom-nav.is-always`, `.ps-actionbar.is-fixed`) | `ps-concept-badge is-above-nav` | над панелью, не закрывает кнопки |
| длинная страница, раскадровка (шапка), полностраничный снимок | `ps-concept-badge is-inline` | в потоке, переносится по словам |
| обычный десктоп | `ps-concept-badge` (`.is-top` — сверху) | фиксированный, в углу |

Обрезанный текст бейджа (не влез в полосу) — замечание `shoot_mockups.mjs`.

## Файлы

| Файл | Куда копировать | Зачем |
|---|---|---|
| `_kit.css` | `<OUT>/mockups/concepts/_kit.css` | компоненты; токены `--c-*` берёт из `../tokens.css`, свои значения — только запасные (слой `ps-defaults`) |
| `_base.html` | `<OUT>/mockups/concepts/_base.html` (и как основа каждого `Mxx-<slug>.html`) | типовой экран: боковая навигация, верхняя панель, KPI, карточки, таблица, нижняя мобильная панель, бейдж концепта |
| `kit-demo.html` | `<OUT>/mockups/concepts/_kit-demo.html` | все компоненты в светлой и тёмной теме + автопроверка контраста |
| `_icons.css` | `<OUT>/mockups/concepts/_icons.css` | 80 контурных иконок `ps-i ps-i-<имя>` (маски из `data:` URI, без сети), цвет — `currentColor`; для десктопа и мобильных |
| `mobile/_mobile.css` | `<OUT>/mockups/concepts/_mobile.css` | мобильный слой `pm-*`: экран телефона 390×844 и его компоненты, раскадровка |
| `mobile/_base-mobile.html` | `<OUT>/mockups/concepts/_base-mobile.html` (и основа мобильных `Mxx-<slug>.html`) | один экран телефона во весь viewport 390×844 |
| `mobile/_storyboard.html` | `<OUT>/mockups/concepts/_storyboard.html` (и основа раскадровок) | 2–4 экрана в ряд с подписями (`1720x1000` для четырёх) |
| `mobile/kit-demo-mobile.html` | `<OUT>/mockups/concepts/_kit-demo-mobile.html` | все мобильные компоненты в обеих темах, галерея иконок, автопроверка контраста |
| `mobile/kit-demo-mobile.png`, `mobile/storyboard.png` | не копировать | пример: как выглядят демо и раскадровка на запасной палитре |
| `_hotspots.js` | `<OUT>/mockups/concepts/_hotspots.js` | подсказки к элементам макета «что это и для чего» (`data-hs-*`), кнопка «Подсказки», `#hs` |
| `gallery.html` | не копировать: шаблон для `mockup_kit.py gallery` → `<OUT>/mockups/gallery.html` | галерея вариантов: 2–3 рабочих экрана на вариант, таблица «один сценарий в N стилях» |
| `tokens-mode.css` | `mockup_kit.py init --modes` → `<OUT>/mockups/tokens-<режим>.css` | заготовка токенов режима интерфейса (`[data-mode="<режим>"]`) |
| (генерируется) | `<OUT>/mockups/concepts/M00-design-language.html` | демо всех форм продукта (веб + мобильный) — карточка design-refs 00 |

Какой набор: `product.type` = `mobile` (или мобильные экраны продукта: приложение, PWA, бот-мини-приложение) — `_kit.css` +
`_icons.css` + `_mobile.css`, макеты на `_base-mobile.html` и `_storyboard.html`; веб-приложение, сайт, дашборд,
`desktop` — `_kit.css` (+ `_icons.css`), макеты на `_base.html`; смешанный продукт — оба (мобильный слой не мешает
десктопным классам).

Имена с `_` в начале shoot_mockups не добавляет в `data/mockups-index.json`; снять и проверить их можно так:

```
node <SKILL_DIR>/scripts/node/shoot_mockups.mjs <OUT> --kit
```

`--kit` снимает `_*.html` (полностраничные PNG рядом с HTML; для `data-viewports="1440x900,390x844"` — на каждой
ширине, суффикс `-390x844`) и пишет `data/mockups-check._kit-demo.json`. Проверка контраста в `kit-demo.html` пишет
каждое нарушение в консоль (`console.error`), поэтому замечание попадает в `console_errors`. Итог также в
`window.psContrast` и атрибуте `<html data-contrast="ok|fail:N">`. Посмотрите PNG через Read **до** раздачи макетов.

Полностраничные снимки (`--kit`, `--full-page`): бейдж `.ps-concept-badge` с `position: fixed` уезжает в низ полного снимка —
на длинных страницах и раскадровках используйте `.ps-concept-badge.is-inline` (в потоке) или `.is-strip` внутри телефона.

## Токены

`audit_site.mjs` пишет `<OUT>/mockups/tokens.css` с обеими темами: роли `--c-bg`, `--c-surface`, `--c-text`,
`--c-muted`, `--c-accent`, `--c-on-accent`, `--c-border`, `--radius`, `--radius-lg`, `--font`, `--font-heading`,
`--font-size`, `--shadow` и CSS custom properties продукта (`:root` и `[data-theme="dark"]`). Набор дополнительно
понимает `--c-success`, `--c-warning`, `--c-danger`, `--c-on-danger`, `--c-focus` (иначе — запасные значения).

**Мост.** `tokens.css` написан вручную (мобильное приложение, нет сайта для `audit_site.mjs`) и `--c-*` в нём нет —
набор берёт привычные имена сам: `--bg`/`--background` → `--c-bg`, `--surface`/`--card` → `--c-surface`, `--text`/
`--foreground` → `--c-text`, `--text-muted`/`--muted-foreground`/`--muted` → `--c-muted`, `--border`/`--line` →
`--c-border`, `--primary`/`--brand` → `--c-accent`, `--on-primary` → `--c-on-accent`, `--success`, `--warning`,
`--danger`/`--error`, `--focus`/`--ring`, `--font-sans` → `--font`, `--font-display` → `--font-heading` (а также
`--color-<роль>`). Значения моста — цвета целиком; «голые» тройки HSL (`--primary: 222 47% 11%`) набор не понимает —
для них пишите `--c-*` сами (`shoot_mockups` сообщит «значение роли — не цвет»).

**Запасные цвета — громко.** Запасная палитра (`--k-def-*`, синий акцент `#2f5bd3`) работает, только если для роли нет
ни `--c-*`, ни имени моста. `shoot_mockups.mjs` (и `--kit`, и обычные макеты на наборе) сравнивает вычисленные
`--c-bg/surface/text/muted/border/accent` в каждой теме страницы с запасными и проверяет, объявлена ли роль в
`tokens.css` или своих стилях страницы: «использован запасной цвет набора» — FAIL, если у продукта есть свои
переменные (токены не дошли до набора), и предупреждение, если `tokens.css` пуст (нейтральная палитра осознанно).

Тёмная тема: если в `tokens.css` нет блока `[data-theme="dark"]` (или `@media (prefers-color-scheme: dark)`), тёмное
поддерево рисуется запасной тёмной палитрой набора — `shoot_mockups` сообщит об этом как о запасных цветах (`dark: …`).
Добавьте блок или не делайте тёмных макетов. Производные цвета (мягкие фоны бейджей, «чернила» статусов, `--k-muted-
strong` для приглушённого текста на градиентах) считаются через `color-mix()` от токенов, поэтому контраст зависит от
продукта: проверяйте `_kit-demo` и `_kit-demo-mobile` с реальными токенами.

**Моноширинный шрифт.** `--font-mono: Menlo, "SF Mono", Consolas, "Liberation Mono", "DejaVu Sans Mono", monospace` —
системные шрифты перед `monospace`: иначе Chromium на macOS рисует кириллицу шрифтом с засечками. Свой `--font-mono` в
`tokens.css` без Menlo/SF Mono/Consolas — предупреждение `shoot_mockups`.

## Режимы интерфейса (набор токенов на режим)

Режимы (например «Терминал», «Дашборд», «Мастер») — одна дизайн-система и одни данные, разные компоновки. Общий
`../tokens.css` — база; `../tokens-<режим>.css` переопределяет только отличия, **переменными `--c-*`** под
`[data-mode="<режим>"]` (имена моста `--primary`/`--bg` под режимом не пересчитываются). Макет режима:
`<html data-mode="terminal" data-theme="dark">` + обе ссылки. Производные цвета (`--k-*`) пересчитываются на каждом
элементе с `data-mode`, поэтому режим работает и для поддерева; `shoot_mockups` проверяет запасные цвета по каждой паре
«тема : режим».

## Цели нажатия и принцип pointer/touch-first

`--k-target` — минимальный размер цели: **32 px** для мыши (десктоп), **44 px** для касания (ширина ≤ 640 px или
`<html data-input="touch">`; `data-input="pointer"` — принудительно 32). Кнопки (в том числе `.is-small`), чипы, сегменты,
тумблеры, чекбоксы, радио, счётчик, ползунок, ссылки шапки и подвала сайта, «Все» в заголовке карточки, действие тоста —
не ниже `--k-target`. `shoot_mockups.mjs --targets` (сам — в `--kit` и при `run-config.design.pointer_first`) находит
интерактивные элементы меньше порога (ссылки внутри строки текста — исключение WCAG 2.5.8) и перетаскивание без
дублирования кнопками (`[draggable]`/`[data-drag]` без `data-drag-alt="<селектор кнопок>"`). Клавиши — только
ускорение: подсказка `kbd.ps-kbd` рядом с кнопкой, не вместо неё.

## Подсветка элементов макета (`_hotspots.js`)

Стандарт макета — **12–25 размеченных элементов**: `data-hs="<id>" data-hs-title="…" data-hs-what="что это"
data-hs-why="для чего" data-hs-p="P001 G8-02" data-hs-sec="5 12"` у существующих элементов (вид не меняется; тот же
`data-hs` без `-title` — «часть» элемента, рамка — объединение) + `<script src="_hotspots.js"></script>` последней
строкой `<body>`. В браузере — кнопка «Подсказки» (рамки с номерами, подсказка по наведению/фокусу, закрепление кликом,
список элементов, Esc), ссылка `<макет>.html#hs` включает режим, `#hs=<id>` — закрепляет элемент. Под автоматизацией
кнопка скрыта (не попадает в PNG). `shoot_mockups.mjs` пишет зоны в `data/mockups-check.<ключ>.json → hotspots.zones`
(для лайтбокса страницы стратегии), `--hotspots 12` — замечание при меньшем числе.

## Галерея вариантов

`python3 <SKILL_DIR>/scripts/mockup_kit.py gallery <OUT>` собирает `mockups/gallery.html` по атрибутам макетов:
`data-variant` (вариант: направление или режим), `data-screen-id` (сценарий, одинаковый у вариантов),
`data-variant-note`, `data-variant-status="rejected"` (отклонён — в конце). Нужно 2–3 рабочих экрана на вариант.

## Темы и размеры

- Тёмная тема: `<html data-theme="dark">` или любой контейнер с `data-theme="dark"` (тема действует на поддерево —
  так `kit-demo.html` показывает обе темы на одной странице).
- Размер: `<html data-viewport="1440x900">` или `"390x844"`; раскладка мобильная при ширине ≤ 640 px (боковая
  навигация скрыта, сетки в одну колонку, видна `.ps-bottom-nav`). `.ps-g4.is-keep-2` — две колонки на телефоне.
- Связь с реестром: `<html data-proposals="P003,P017">` (или `<meta name="ps:proposals" content="P003,P017">`) — shoot_mockups
  перенесёт в индекс при автообнаружении и обновит при правке HTML (записи `discovered: true`). Так же — `ps:viewport`,
  `ps:title`, `ps:kind` (`component` — служебный макет, например `M00-design-language`: с предложениями не связывается).

## Компоненты

Раскладка `.ps-app`, `.ps-rail` (боковая навигация: `.ps-brand`, `.ps-nav.is-active`, `.ps-nav-sep`), `.ps-main`,
`.ps-topbar` (= `.ps-top`; `.ps-brand` в шапке — без отступов меню), `.ps-page`, сетки `.ps-g2/.ps-g3/.ps-g4`, `.ps-row`, `.ps-stack`; карточка `.ps-card`
(`.is-accent`, `.is-flat`), `.ps-kpi`, `.ps-bar`, `.ps-steps`; кнопки `.ps-btn` + `.is-primary/.is-secondary/.is-danger/
.is-ghost/.is-small/.is-large`; поля `.ps-field`, `.ps-input` (`.is-error`), `.ps-hint`, `.ps-error`; сегментный
переключатель `.ps-segmented`; чипы-фильтры `.ps-chips > .ps-chip.is-active`; тумблер `.ps-switch` (input + `.ps-track`),
чекбокс `.ps-check`, радио `.ps-radio` (input + `.ps-box`); бейджи `.ps-badge` + `.is-success/.is-warning/.is-danger/
.is-neutral`; список `.ps-list > .ps-list-item`, `.ps-avatar`; таблица `.ps-table-wrap > .ps-table` (`.is-num`);
модальное окно `.ps-backdrop` (`.is-fixed` — на весь экран) `> .ps-modal`; пустое состояние `.ps-empty`; уведомления
`.ps-toast`, `.ps-alert` (+ статусы), `.ps-cookie`; закрытая функция `.ps-lock > .ps-lock-head + .ps-lock-body`;
выноска `.ps-tip` (`.is-floating` — абсолютная внутри `.ps-anchor`/`.ps-card`/`.ps-rail`/`.ps-page`); нижняя мобильная
панель `.ps-bottom-nav` (`.is-always` — показать и на десктопе); бейдж концепта `.ps-concept-badge` (`.is-top`,
`.is-above-nav`, `.is-inline`, `.is-strip` — правило выше). Знак бренда `.ps-brand-mark` — две буквы (`.is-2`) или иконка:
одна «З»/«О»/«Ч» в жирном шрифте читается как цифра.

Компоненты 1.3 (их не хватало агентам макетов; все показаны в `kit-demo.html` и `mobile/kit-demo-mobile.html`):
- шапка и подвал публичного сайта: `.ps-site-header` (`.ps-brand`, `.ps-site-nav > a.is-active`, `.ps-row` с кнопками),
  `.ps-site-footer` (колонки `div > b + a`, `.ps-legal`);
- нижняя панель действий: `.ps-actionbar` (`.ps-grow` — итог; `.is-fixed` — к низу окна, бейдж сам поднимается),
  мобильная `.pm-actionbar` (снекбар сам поднимается над ней);
- счётчик −/+: `.ps-counter > button + output + button`;
- ячейки сравнения: `.ps-yes` / `.ps-no` / `.ps-unk` («да / нет / не нашли» — значок и слово), столбец «мы» — `.ps-cmp-us`;
- график: `.ps-chart > .ps-chart-plot > svg` (цвета `var(--k-chart-1…6)`, подписи `text.ps-axis`, линии `.ps-grid-line`),
  уровни `.ps-levels > .ps-level.is-target|.is-stop|.is-entry > span`, легенда `.ps-legend > li > i.ps-swatch(.is-line|.is-dash|.is-2…6)`;
- клавиша `kbd.ps-kbd`; ползунок `label.ps-slider > span(output) + input[type=range]`;
- свежесть данных `.ps-fresh.is-live|.is-delayed|.is-stale` (точка + текст, не только цвет);
- степпер с линиями `ol.ps-stepper > li.is-done|.is-now > b`; «пузырь» чата `.ps-chat > .ps-msg(.is-me|.is-typing)`
  (`.ps-msg-who` — «ИИ», `.ps-msg-meta`);
- сноски `sup.ps-fn > a` + `ol.ps-footnotes > li`.
Иконки 1.3: `undo`, `box`, `coin`, `wifi-off`.

Метки новизны: `.ps-new` («НОВОЕ») и `.ps-changed` («ИЗМЕНЕНО») — пунктирный контур и ярлык в `::after` (свой текст —
`data-label`); `::before` элемента остаётся свободным. Ярлык выступает над рамкой на 10 px: внутри контейнера с
`overflow: hidden` — `.is-inside` (ярлык внутри рамки) или обёртка `<div class="ps-new">…</div>` снаружи. Градиентная
карточка `.ps-card.is-gradient` (приглушённый текст внутри — `--k-muted-strong`), моноширинный блок `.ps-code`.

## Мобильный слой (`mobile/_mobile.css`, префикс `pm-`)

Подключение: `../tokens.css`, `_kit.css`, `_icons.css`, `_mobile.css`. Цвета — те же токены `--c-*`, обе темы.

- Экран: `.pm-phone` (390×844, скругление; `.is-flat` — без) `> .ps-concept-badge.is-strip` (полоса-бейдж над строкой
  состояния) `+ .pm-status` (время, отверстие камеры, `.pm-status-icons`) `+ .pm-appbar` (`.pm-iconbtn`, `h1`; `.is-large` —
  крупный заголовок с `.pm-appbar-row` и `.pm-sub`; `.is-surface` — на поверхности) `+ .pm-body` (`.is-center`) `+ .pm-tabbar`
  `+ .pm-gesture`. Один экран в макете: `<body class="pm-single">`, `data-viewport="390x844"`.
- Содержимое: `.pm-search`, `.pm-chips` (с `.ps-chip`), `.pm-overline`, `.pm-card` (`.is-gradient`), список `.pm-list >
  .pm-item` (`.pm-lead`/`.is-round`, `.pm-grow > b + small`, `.pm-trail`; `.pm-item.is-card` — отдельной карточкой),
  `.pm-progress > i`, `.pm-actions` (`.is-row`), `.pm-btn-block` (кнопка на всю ширину вместе с `.ps-btn`).
- Навигация: `.pm-tabbar > .pm-tab` (`.is-active`, иконка в `.pm-tab-pill`); `.pm-tabbar.has-fab` — пять колонок, `.pm-fab`
  по центру; отдельный `.pm-fab` (`.is-extended` — с подписью) — над панелью справа.
- Поверх экрана: `.pm-scrim`, нижний лист `.pm-sheet > .pm-grabber` (ручка — отдельный элемент, `::before` листа свободен
  для меток), диалог `.pm-dialog` (`.pm-dialog-ico`), снекбар `.pm-snackbar` (`.pm-snack-action`; `.is-low` — без панели
  вкладок, `.is-static` — в потоке).
- Система: уведомление `.pm-notif` (`.pm-notif-head > .pm-notif-ico + b`, `.pm-notif-title`, `.pm-notif-text`,
  `.pm-notif-actions`; `.is-heads-up` — всплывающее сверху; стопка `.pm-notifs`), экран блокировки `.pm-phone.is-lock`
  (`.pm-lock-clock`, `.pm-lock-date`, `.pm-lock-bottom > .pm-lock-btn`, `.pm-lock-hint`), рабочий стол `.pm-phone.is-home`
  (`.pm-home-grid > .pm-app > i.pm-app-ico`, `.pm-dock`), виджет `.pm-widget` (4×2; `.is-2x2`; `.pm-widget-head`,
  `.pm-widget-value`, `.pm-widget-bars > i`). Обои — тёмные из акцента, текст белый: контраст держится при любом акценте.
- Раскадровка: `.pm-board` `> .pm-board-head` (заголовок + `.ps-concept-badge.is-inline`) `+ .pm-frame[data-screen="N"] >
  .pm-phone + .pm-cap` (`.pm-step` — номер, `small` — P-id и пояснение). Viewport по числу экранов: 4 — `1720x1000`,
  3 — `1320x1000`, 2 — `900x1000`; высота ≥ 960 — иначе подписи под телефонами обрезаются (`shoot_mockups` считает
  раскадровку выше viewport замечанием). `data-screen` переносится в `hotspots[].screen` (`measure_hotspots.mjs`).

Иконки: `<i class="ps-i ps-i-mic"></i>` (размер `1.25em`; `.is-16/.is-20/.is-24/.is-28/.is-32`). Список имён — в
шапке `_icons.css` и в галерее `_kit-demo-mobile`. Рисунки собственные, по мотивам Material/Feather; своя иконка —
строка по образцу (контур 24×24 в `data:` URI).

## Исправлено по сравнению с набором реального прогона

- 1.3 (по отзывам прогонов режима идеи, FB-032/033, SM 6.4/9): `.ps-badge` и `.ps-btn` не сжимаются в flex-строке
  (`flex-shrink: 0`); `.ps-segmented` переносит варианты вместо скрытой прокрутки (последний вариант в `.ps-topbar .ps-row`
  больше не прячется; прокрутка по замыслу — `.is-scroll`); ряды верхней панели переносятся на ≤ 640 px; `.ps-brand` без
  отступов меню в шапке; `.ps-steps` на ≤ 640 px остаётся в одну строку (не 2+1); цели нажатия ≥ 32/44 px (`--k-target`,
  было 28–30 px у `.ps-btn.is-small`, `.ps-chip`, `.ps-switch`, `.ps-segmented > *`); `.pm-snackbar` учитывает свою
  нижнюю панель и экран без вкладок; `.pm-chips` переносятся (край телефона их больше не обрезает; карусель — `.is-scroll`);
  `.ps-concept-badge.is-inline` переносится по словам; одно правило и один текст бейджа; режимы `data-mode`; иконки
  undo/box/coin/wifi-off; компоненты выше; `shoot_mockups --kit` проверяет kit-demo на 1440 и 390 px с `--layout`
  (дети, вылезающие из однострочных flex-рядов, скрытая прокрутка) и `--targets`.
- бейдж концепта: `position: fixed`, одна строка (`white-space: nowrap` + многоточие), на мобильном с нижней панелью
  поднимается над ней автоматически (`body:has(.ps-bottom-nav)`), варианты `.is-top` и `.is-above-nav`;
- `.ps-badge` не выходит из капсулы (`nowrap`, `max-width: 100%`, многоточие);
- `.ps-btn.is-danger` — `--c-danger` с контрастом ≥ 4,5:1 в обеих темах (светлая: белый на `#b42318` ≈ 6,6:1;
  тёмная: тёмный текст на `#f97066`);
- `.ps-lock`: штриховка только поверх `.ps-lock-body`, заголовок `.ps-lock-head` всегда читается;
- `.ps-tip` по умолчанию в потоке (`position: relative`), плавающая — только `.is-floating`; `.ps-rail`, `.ps-card`,
  `.ps-main`, `.ps-page`, `.ps-topbar` — `position: relative`, выноски не уезжают;
- добавлены сегментный переключатель, чипы, тумблер, чекбокс, радио, список, алерты, тёмная тема;
- 1.2 (по отзывам прогонов мобильного приложения): мобильный слой и иконки; мост `--c-*` из `--primary/--bg/--text…` и
  громкая проверка запасных цветов; `.ps-concept-badge.is-inline`; `--font-mono` с Menlo/SF Mono/Consolas; метки
  `.ps-new`/`.ps-changed` без обрезки (у `.ps-list` больше нет `overflow: hidden`); `--k-muted-strong` на градиентах;
  проверка контраста учитывает цвета градиентов (худший случай).
