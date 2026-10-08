# responsive-cross-browser — Адаптивность и кроссбраузерность

Направление: `responsive-cross-browser` · Инструменты: Playwright MCP (`browser_resize`, `browser_emulate_media`), playwright-cli (`open --browser firefox|webkit`, `--device`, `--mobile`, `resize`) — параллельные сессии на разные браузеры · Усилители: qa-skills агент `mobile-ux-auditor` (только с теми же запретами; его viewport 393×852 — дополнительный)

## Цель
Убедиться, что сайт корректно выглядит и работает на разных ширинах, ориентациях и движках.

## Безопасность в этом направлении
- Действия те же, что в functional и visual-ui, с теми же проверками `url_guard`. Каждый браузерный поток (сессия playwright-cli) получает полный текст правил.
- Не логиниться боевым аккаунтом параллельно в нескольких браузерах, если пользователь не разрешил (риск блокировки за подозрительную активность).

## Ширины и браузеры по глубине
| Глубина | Ширины (px) | Браузеры |
|---|---|---|
| smoke | 1440 (desktop), 375 (mobile) | Chromium |
| standard | 375, 768, 1440 | Chromium, WebKit |
| deep | 360, 375, 768, 1024, 1440, 1920 (+ 393×852 у `mobile-ux-auditor`) | Chromium, Firefox, WebKit |

Если браузер не запускается (см. `check_env`, `environment-notes.md` — Firefox на части систем), в отчёт пишется «<браузер>: не проверено — не запускается в окружении».

## Снимок горизонтального скролла (`browser_evaluate`)
```js
() => { const w = document.documentElement.clientWidth;
  const over = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.right > w + 1 && getComputedStyle(e).position !== 'fixed'; })
    .slice(0, 10).map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : ''));
  return { scrollWidth: document.documentElement.scrollWidth, clientWidth: w, overflow: document.documentElement.scrollWidth > w, culprits: over }; }
```

## Smoke
- [ ] `rsp.horizontal-scroll` — на 375 px нет горизонтального скролла → снимок выше → дефект: `overflow: true` (указать виновников).
- [ ] `rsp.mobile-nav` — мобильное меню (бургер) открывается, закрывается, пункты доступны → дефект: не открывается, перекрывает контент без закрытия.
- [ ] `rsp.viewport-meta` — `<meta name="viewport">` есть и не запрещает масштабирование (`user-scalable=no`, `maximum-scale=1` — дефект доступности).
- [ ] `rsp.key-pages-mobile` — ключевые страницы на 375 px: контент читается, CTA видны → full page скриншоты.

## Standard (в дополнение к smoke)
- [ ] `rsp.breakpoints` — 375, 768, 1440: скриншоты ключевых страниц → дефект: поломка на промежуточной ширине (особенно 768), «дыры», наложения.
- [ ] `rsp.webkit` — ключевые сценарии functional (smoke-набор) в WebKit → дефект: отличие поведения от Chromium (не работает клик, ломается вёрстка, ошибки в консоли только в WebKit).
- [ ] `rsp.images-responsive` — изображения не растягиваются и не вылезают, `srcset` подставляет подходящий размер.
- [ ] `rsp.tables` — таблицы на мобильном: прокрутка внутри контейнера или адаптивная раскладка → дефект: таблица расширяет страницу.
- [ ] `rsp.forms-mobile` — поля форм на мобильном: правильный тип клавиатуры (`type=email/tel/number`, `inputmode`), подписи не обрезаны.
- [ ] `rsp.fixed-elements` — фиксированные шапки, баннеры и чаты на мобильном не закрывают больше ~25% экрана и не перекрывают CTA.
- [ ] `rsp.touch-emulation` — **до любых измерений на «телефоне»** проверить, что эмуляция включает касания: `matchMedia('(pointer: coarse)').matches === true` и `(hover: none)` (`node <SKILL_DIR>/scripts/node/device_context.js media --devices pixel7,…`; в результатах `run`, `occlusion.js` и `targets.js` — поле `media.touchValid`). Телефон — только имя из каталога (`pixel7`, `iphone15`, `360x640`) или `WxH@mobile`; просто `WxH` — это **десктопное** окно такой ширины. Если `pointer: coarse` ложно — сайт показывает десктопные мелкие цели, и **результаты измерений целей нажатия и «мобильной» вёрстки недействительны**: находку не заводить, переснять на правильной эмуляции. В браузере пользователя по CDP (manual-cdp) эмуляция вкладки размером окна не даёт касаний — использовать `--cdp … --device pixel7` (отдельный контекст с тем же входом).
- [ ] `rsp.touch-targets` — цели нажатия на телефоне (`node <SKILL_DIR>/scripts/node/targets.js <URL> --device pixel7`): одной строкой «N из M меньше 24×24, K меньше 44×44, по типам» — только при `touchValid: true`.

## Deep (в дополнение к standard)
- [ ] `rsp.all-widths` — все 6 ширин на всех страницах до лимита.
- [ ] `rsp.firefox` — сценарии в Firefox (если запускается).
- [ ] `rsp.orientation` — ландшафт на мобильном (812×375) и планшете (1024×768 ↔ 768×1024) → дефект: контент недоступен, модальные окна не помещаются.
- [ ] `rsp.touch-gestures` — тач-эмуляция (`playwright-cli open --mobile` / `--device "iPhone 15"`): свайпы каруселей, pinch на картах (если поддерживается), отсутствие hover-зависимых функций → дефект: функция доступна только по hover.
- [ ] `rsp.zoom-text` — увеличение текста 200% (через `document.documentElement.style.fontSize='200%'` в своей сессии) → дефект: текст обрезается или перекрывается.
- [ ] `rsp.large-screens` — 1920+: контент не растянут на всю ширину, есть max-width, нет пустых областей.
- [ ] `rsp.safari-quirks` — WebKit: `100vh` при панели браузера, `position: sticky`, формы дат, плавный скролл.
- [ ] `rsp.mobile-ux-auditor` — прогнать агент `mobile-ux-auditor` (передав правила дословно), выводы привести к findings и перепроверить.

## Типовые находки и severity
| Пример | Severity |
|---|---|
| Основная функция не работает в WebKit (Safari) | High |
| Мобильное меню не открывается | High |
| Горизонтальный скролл на мобильном | Medium |
| Поломка вёрстки на 768 px | Medium |
| Запрет масштабирования в viewport | Medium (и accessibility) |
| Неверный тип клавиатуры в поле | Low |

## Что записывать в находку
- Ширину × высоту, браузер и версию, устройство или эмуляцию (`--device`), ориентацию.
- Пары скриншотов: проблемная ширина и ближайшая корректная.
- Вывод снимка горизонтального скролла (`culprits`).
- Для кроссбраузерных отличий — консоль в проблемном браузере и описание поведения в эталонном.
