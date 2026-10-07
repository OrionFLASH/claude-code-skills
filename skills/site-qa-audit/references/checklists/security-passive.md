# security-passive — Пассивная безопасность

Направление: `security-passive` · Инструменты: `node/headers.js` (HTTPS, HSTS, CSP и другие заголовки, cookies, mixed content, sourcemaps, утечки версий и секретов в JS), Playwright MCP (консоль, сеть, `browser_evaluate` — только чтение) · Усилители: собственные скрипты; qa-skills `security-auditor` — только как справочник пунктов (report-only), без активных проверок

## Цель
Найти то, что видно любому посетителю без атак: отсутствие защитных заголовков, небезопасная передача, утечки служебной информации и секретов в клиентском коде, консоли и ответах.

## Безопасность в этом направлении — ЖЁСТКИЕ ОГРАНИЧЕНИЯ
- **Только GET/HEAD** к страницам и ресурсам, которые и так загружает браузер, плюс стандартные публичные пути: `/robots.txt`, `/sitemap.xml`, `/.well-known/security.txt`, `<script>.map`, на который ссылается сам скрипт.
- **Запрещено**: сканеры уязвимостей, перебор путей и директорий (`/admin`, `/.git`, `/backup`…), подбор паролей, инъекции (XSS, SQL, шаблонов, команд), подделка запросов, обход авторизации, подмена cookies и токенов на боевом аккаунте, фаззинг, DoS.
- Найденные секреты, токены, ключи, e-mail и персональные данные **маскируются** в находках, отчётах и issues: первые 4 символа + `…` + длина (`ghp_…(40)`). Полные значения не сохраняются даже в `raw/` и `logs/` (формат — `references/safety-rules.md` §5).
- Если найдена серьёзная утечка (действующий ключ, персональные данные других пользователей) — остановить публикацию в открытые репозитории и спросить пользователя: такая находка не должна попасть в публичный issue.

## Smoke
- [ ] `sec.https` — сайт на HTTPS, HTTP перенаправляет на HTTPS (`headers.js`: `no-https`, `http-no-redirect`).
- [ ] `sec.hsts` — заголовок `Strict-Transport-Security` (`no-hsts`); в deep — `max-age` ≥ 15552000 и `includeSubDomains`.
- [ ] `sec.mixed-content` — HTTP-ресурсы на HTTPS-страницах (`headers.js` `mixed-content`, консоль браузера с предупреждениями mixed content).
- [ ] `sec.console-leaks` — в консоли нет токенов, stack trace с путями сервера, отладочного вывода с данными (`browser_console_messages` level debug).

## Standard (в дополнение к smoke)
- [ ] `sec.csp` — `Content-Security-Policy` есть (`no-csp`) и не ослаблен `unsafe-inline`/`unsafe-eval` (`weak-csp`) → оценить разумно: отсутствие CSP — Low для контентных сайтов, Medium для сайтов с вводом данных и аккаунтами.
- [ ] `sec.xcto` — `X-Content-Type-Options: nosniff` (`no-xcto`).
- [ ] `sec.clickjacking` — `X-Frame-Options` или `frame-ancestors` (`no-clickjacking`).
- [ ] `sec.referrer-policy` — `Referrer-Policy` (`no-referrer-policy`).
- [ ] `sec.permissions-policy` — `Permissions-Policy` (наличие).
- [ ] `sec.cookie-flags` — cookies без `Secure`/`HttpOnly`/`SameSite` (`cookie-flags`; в браузере — `document.cookie` показывает только не-HttpOnly: сессионная cookie, видимая из JS, — дефект).
- [ ] `sec.version-disclosure` — версии ПО в заголовках (`version-leak`: `Server`, `X-Powered-By`), в HTML-комментариях и мета `generator`.
- [ ] `sec.public-sourcemaps` — доступные `.map` (`public-sourcemaps`) → Low (раскрытие исходников), отметить, если в них видны секреты.
- [ ] `sec.secrets-in-js` — похожие на секреты строки в клиентском JS (`secret-in-js`) → **проверить вручную** (публичные ключи карт и аналитики — норма), маскировать.
- [ ] `sec.error-pages` — страница ошибки не раскрывает стек, пути, версии фреймворка (наблюдать на 404 из functional, без специальных попыток вызвать 500).

## Deep (в дополнение к standard)
- [ ] `sec.storage-sensitive` — localStorage/sessionStorage: токены и персональные данные в открытом виде (только чтение ключей; значения маскировать).
- [ ] `sec.third-party-scripts` — список сторонних скриптов и доменов (с разведки), наличие `integrity` (SRI) у скриптов с CDN.
- [ ] `sec.security-txt` — `/.well-known/security.txt` (`headers.js` `securityTxt`) → info.
- [ ] `sec.coop-corp` — `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` → info/Low.
- [ ] `sec.forms-transport` — формы отправляются на HTTPS-адреса (`action`), поля пароля с `autocomplete` по назначению — только просмотр разметки.
- [ ] `sec.api-responses` — ответы API, которые браузер и так получает (`browser_network_requests`): нет лишних персональных данных других пользователей, служебных полей (хэши паролей, внутренние ID сотрудников) → только наблюдение, без изменения запросов.
- [ ] `sec.target-blank` — внешние ссылки с `target=_blank` без `rel="noopener"` (для старых браузеров) → Low.

## Типовые находки и severity
| Пример | Severity |
|---|---|
| Действующий секретный ключ или персональные данные других пользователей в клиентском коде или ответах | Critical (не публиковать в открытые репозитории, спросить пользователя) |
| Сайт с аккаунтами без HTTPS или с mixed content на страницах ввода | High |
| Сессионная cookie без HttpOnly/Secure | Medium |
| Нет HSTS | Medium |
| Нет CSP, X-Content-Type-Options, X-Frame-Options | Low |
| Раскрытие версий ПО, публичные sourcemaps | Low |
| Нет security.txt | Info |

## Что записывать в находку
- Заголовки ответа (только относящиеся к делу), URL, метод (GET/HEAD).
- Для утечек — место (URL скрипта и позиция, ключ хранилища, сообщение консоли) и **маскированное** значение.
- Рекомендацию с примером заголовка (`Strict-Transport-Security: max-age=31536000; includeSubDomains`).
- Пометку «пассивная проверка, без активного тестирования».
