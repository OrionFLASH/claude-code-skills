# performance — Производительность

Направление: `performance` · Инструменты: `node/lighthouse.js` (mobile и desktop), `node/headers.js` (кэш, сжатие), Playwright MCP (`browser_network_requests`, Performance API через `browser_evaluate`) · Усилители: browser-devtools `performance-analyzer` (если включён), qa-skills агент `performance-profiler` (ориентирован на Next.js; только report-only); opentest `perf-test` **не используется** (k6 — нагрузка)

## Цель
Оценить скорость загрузки и отзывчивость с точки зрения пользователя: Core Web Vitals, вес и число ресурсов, кэширование, сжатие, ленивая загрузка, форматы изображений.

## Безопасность в этом направлении
- **Никаких нагрузочных тестов**: не запускать параллельные повторные запросы, k6, ab, wrk. Lighthouse — последовательно, с паузой между URL (так делает `lighthouse.js`).
- Число страниц для Lighthouse ограничено глубиной (smoke 1–3, standard до 10, deep — шаблоны страниц, а не все URL).

## Пороги Core Web Vitals (хорошо / нужно улучшить / плохо)
| Метрика | Хорошо | Плохо |
|---|---|---|
| LCP | ≤ 2.5 с | > 4.0 с |
| INP | ≤ 200 мс | > 500 мс |
| CLS | ≤ 0.1 | > 0.25 |
| FCP (вспомогательная) | ≤ 1.8 с | > 3.0 с |
| TBT (лабораторная замена INP) | ≤ 200 мс | > 600 мс |

## Smoke
- [ ] `perf.lighthouse-mobile` — `node/lighthouse.js <главная + 1–2 ключевых> --form mobile --out raw/lighthouse.json` → дефект: performance score < 0.5 (High), < 0.9 (Medium/Low по метрикам).
- [ ] `perf.lcp` — LCP из Lighthouse → дефект: > 2.5 с (mobile).
- [ ] `perf.cls` — CLS → дефект: > 0.1; найти сдвигающийся элемент (раздел `layout-shift-elements`).
- [ ] `perf.tbt` — TBT → дефект: > 200 мс.
- [ ] `perf.compression` — `headers.js`: `no-compression` → дефект: текстовые ресурсы без gzip/br.

## Standard (в дополнение к smoke)
- [ ] `perf.lighthouse-desktop` — `--form both` для ключевых шаблонов страниц.
- [ ] `perf.page-weight` — общий вес (`totalBytes`) и число запросов → дефект: > 3 МБ или > 100 запросов на мобильной загрузке (ориентир, оценивать по типу сайта).
- [ ] `perf.images-format` — изображения не в WebP/AVIF, без размеров, крупнее отображаемых (opportunities: `modern-image-formats`, `uses-responsive-images`, `unsized-images`).
- [ ] `perf.lazy-loading` — изображения и iframe ниже первого экрана грузятся лениво (`offscreen-images`, атрибут `loading="lazy"`); LCP-изображение **не** ленивое.
- [ ] `perf.caching` — статические ресурсы с долгим `Cache-Control` (`uses-long-cache-ttl`; `headers.js` `cacheControl`).
- [ ] `perf.render-blocking` — блокирующие CSS и JS (`render-blocking-resources`).
- [ ] `perf.unused-code` — неиспользуемый JS и CSS (`unused-javascript`, `unused-css-rules`) — крупные суммы.
- [ ] `perf.third-party` — вклад сторонних скриптов (`third-party-summary`) → дефект: сторонние скрипты блокируют основной поток дольше 250 мс.
- [ ] `perf.fonts` — шрифты: `font-display`, preload ключевых, число начертаний.

## Deep (в дополнение к standard)
- [ ] `perf.inp-interactions` — реальная отзывчивость: замер задержки на ключевых взаимодействиях (клик по фильтру, открытие меню) через `browser_evaluate` с `PerformanceObserver` типа `event` → дефект: > 200 мс.
- [ ] `perf.long-tasks` — долгие задачи главного потока после загрузки (`longtask` observer) при работе с картой, фильтрами, прокруткой.
- [ ] `perf.slow-network` — Lighthouse mobile уже троттлит; дополнительно: поведение на «медленном 3G» в своей сессии — индикаторы, приоритет контента.
- [ ] `perf.memory-growth` — SPA: `performance.memory` (Chromium) до и после 20 переходов → дефект: устойчивый рост (утечка).
- [ ] `perf.cdn-http2` — протокол (h2/h3) и CDN для статики (`browser_network_requests`, заголовки).
- [ ] `perf.map-tiles` — карты: число и вес тайлов, кэш тайлов.
- [ ] `perf.performance-analyzer` — если включён browser-devtools: агент `performance-analyzer` с правилами дословно; выводы привести к findings.

## Типовые находки и severity
| Пример | Severity |
|---|---|
| LCP > 4 с на главной (mobile) | High |
| CLS > 0.25 на ключевой странице | High |
| LCP 2.5–4 с, TBT > 600 мс | Medium |
| Нет сжатия текстовых ресурсов | Medium |
| Изображения не в современных форматах (экономия > 500 КБ) | Medium |
| Короткий кэш статики | Low |
| Отдельные opportunities с экономией < 100 мс | Low / info |

## Что записывать в находку
- Значения метрик (mobile и desktop отдельно), score, версия Lighthouse, дата; ссылка на полный отчёт (`--reports-dir raw/lighthouse/`).
- Для opportunities — ожидаемая экономия (мс и байты) и 3–5 самых тяжёлых ресурсов (URL без токенов).
- Условия: эмуляция Lighthouse (по умолчанию mobile: Moto G Power, slow 4G), локальная машина — отметить, что это лабораторные, а не полевые данные.
- Элемент LCP и элементы сдвига CLS (селекторы).
