#!/usr/bin/env python3
"""Демо-данные режима «Отслеживание выполнения» (1.2) для готового прогона <OUT>: правдоподобный срез прогресса.

По data/proposals.json, data/scores.json (если есть), data/gantt.json, data/kanban.json и build/run-config.json пишет
строго по references/data-contract.md («Отслеживание выполнения»):

  data/progress.json          последний срез: summary, items (статус, уверенность, источник, issues, PR, коммиты, следы
                              в коде), outside_strategy, facts_changed, next_actions, overdue, warnings
  data/gantt-progress.json    {"current_month", "tasks": [{id, task, proposal_ids, start_month, end_month, status,
                              progress, done_ids, open_ids}]}
  data/kanban-progress.json   {"moves": [{id, from, to, reason}], "columns": {колонка: [id…]}}
  data/revision.json          предлагаемые корректировки стратегии
  data/progress-overrides.json, data/issue-links.json  решения владельца и сохранённые связи (для source override|link)
  tracking/history.json       три точки во времени [{date, summary, git_head}]

Нужен тестам и демо страницы/XLSX, пока движок strategy_track.py не готов; движок пишет те же файлы. Все issues, PR и
коммиты вымышлены (репозиторий — run-config.repo.remote, иначе заглушка owner/repo). Встречаются все статусы: done,
partial, in_progress, planned, not_started, blocked, dropped, obsolete, unknown (при ≥ 9 предложениях).

  make_progress_demo.py <OUT> [--seed 11] [--months 2.3] [--apply-block]

--months       сколько месяцев прошло с даты стратегии (по умолчанию 2,3 → идёт 3-й месяц плана)
--apply-block  вписать автоблок <!-- progress:start --> … <!-- progress:end --> (таблица статусов) в раздел 14
               research/strategy.md — как strategy_track.py apply-to-strategy (идемпотентно)

Только стандартная библиотека.
"""
import argparse
import hashlib
import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

STATUSES = ["done", "partial", "in_progress", "planned", "not_started", "blocked", "dropped", "obsolete", "unknown"]
STATUS_RU = {"done": "выполнено", "partial": "частично", "in_progress": "в работе", "planned": "запланировано",
             "not_started": "не начато", "blocked": "заблокировано", "dropped": "исключено", "obsolete": "устарело",
             "unknown": "неясно"}
CLOSED = {"done", "dropped", "obsolete"}
HORIZONS = ["now", "next", "later", "vision"]
PID_RE = re.compile(r"^P\d{3}$")
REMOTE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
FILES = ["src/app/main.py", "src/app/routes.py", "src/app/onboarding.py", "web/pages/pricing.tsx", "web/components/Export.tsx",
         "src/api/v1.py", "src/digest/weekly.py", "docs/integrations.md", "src/analytics/events.py", "README.md"]


# ---------------------------------------------------------------- ввод
def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as e:
        print("предупреждение: %s не читается (%s) — пропущен" % (path, e), file=sys.stderr)
        return default


def write_json(out, rel, obj):
    p = Path(out) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def as_int(v, default=None):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def remote_of(cfg):
    """owner/repo из run-config.repo.remote (в том числе https://github.com/owner/repo(.git)); иначе заглушка owner/repo."""
    r = str(((cfg.get("repo") or {}) if isinstance(cfg.get("repo"), dict) else {}).get("remote") or "").strip()
    m = re.match(r"^(?:https://github\.com/|git@github\.com:)?([^/\s]+/[^/\s]+?)(?:\.git)?/?$", r)
    r = m.group(1) if m else ""
    return r if REMOTE_RE.match(r) else "owner/repo"


def sha(rnd):
    return "%07x" % rnd.getrandbits(28)


def full_sha(rnd):
    return "%040x" % rnd.getrandbits(160)


def iso(d):
    return d.isoformat()


# ---------------------------------------------------------------- модель среза
class Demo:
    def __init__(self, out, seed=11, months=2.3):
        self.out = Path(out).resolve()
        self.rnd = random.Random(seed)
        self.cfg = read_json(self.out / "build" / "run-config.json", {}) or {}
        props = read_json(self.out / "data" / "proposals.json", None)
        if not isinstance(props, list) or not props:
            raise SystemExit("ошибка: нет data/proposals.json (список предложений) в %s" % self.out)
        self.P = [p for p in props if isinstance(p, dict) and PID_RE.match(str(p.get("id") or ""))]
        self.ids = [p["id"] for p in self.P]
        self.byid = {p["id"]: p for p in self.P}
        scores = read_json(self.out / "data" / "scores.json", []) or []
        self.S = {s.get("id"): s for s in scores if isinstance(s, dict)}
        self.gantt = [g for g in (read_json(self.out / "data" / "gantt.json", []) or []) if isinstance(g, dict)]
        kb = read_json(self.out / "data" / "kanban.json", {}) or {}
        self.kanban = kb if isinstance(kb, dict) else {}
        created = str(self.cfg.get("created") or "")
        self.created = date.fromisoformat(created) if re.match(r"^\d{4}-\d{2}-\d{2}$", created) else date.today() - timedelta(days=70)
        st = self.cfg.get("strategy") if isinstance(self.cfg.get("strategy"), dict) else {}
        self.horizon = max(1, as_int(st.get("horizon_months"), 12) or 12)
        self.months = max(0.05, float(months))
        self.checked = self.created + timedelta(days=int(round(self.months * 30.44)))
        self.month_index = int(self.months) + 1
        self.remote = remote_of(self.cfg)
        self.issue_no = 10 + self.rnd.randint(0, 20)

    # --- порядок важности: ранг из scores.json, иначе порядок реестра
    def rank(self, pid):
        r = as_int((self.S.get(pid) or {}).get("rank"))
        return r if r is not None else 10 ** 4 + self.ids.index(pid)

    def priority(self, pid):
        p = str((self.S.get(pid) or {}).get("priority") or "")
        return p if re.match(r"^P[0-3]$", p) else ""

    def plan_window(self):
        """Предложение → (самый ранний старт, самый поздний конец) по задачам Ганта."""
        win = {}
        for g in self.gantt:
            s, e = as_int(g.get("start_month")), as_int(g.get("end_month"))
            if s is None and e is None:
                continue
            s, e = (s if s is not None else e), (e if e is not None else s)
            for pid in g.get("proposal_ids") or []:
                if pid in self.byid:
                    a, b = win.get(pid, (s, e))
                    win[pid] = (min(a, s), max(b, e))
        return win

    # --- статусы
    def statuses(self):
        rnd, cur = self.rnd, self.month_index
        win = self.plan_window()
        st = {}
        for pid in self.ids:
            p = self.byid[pid]
            hz = str(p.get("horizon") or "next")
            if pid in win:
                s, e = win[pid]
                if e < cur:                      # срок прошёл
                    w = {"done": 50, "partial": 18, "in_progress": 14, "not_started": 12, "planned": 6}
                elif s <= cur:                   # идёт сейчас
                    w = {"in_progress": 34, "partial": 20, "planned": 18, "done": 12, "not_started": 16}
                else:                            # впереди
                    w = {"not_started": 66, "planned": 22, "done": 4, "in_progress": 8}
            else:
                w = {"now": {"done": 22, "in_progress": 18, "partial": 10, "planned": 14, "not_started": 36},
                     "next": {"not_started": 70, "planned": 14, "in_progress": 8, "done": 5, "partial": 3},
                     "later": {"not_started": 90, "planned": 6, "done": 2, "in_progress": 2},
                     "vision": {"not_started": 96, "planned": 4}}.get(hz, {"not_started": 1})
            keys = list(w)
            st[pid] = rnd.choices(keys, weights=[w[k] for k in keys])[0]
        # редкие статусы: исключено, устарело, неясно
        tail = sorted(self.ids, key=self.rank)[len(self.ids) // 3:] or list(self.ids)
        for k, name in ((2, "dropped"), (1, "obsolete"), (1, "unknown")):
            pool = [x for x in tail if st[x] in ("not_started", "planned")] or [x for x in tail if st[x] not in CLOSED]
            for pid in rnd.sample(pool, min(k, len(pool))):
                st[pid] = name
        # блокировки: предпосылка не выполнена → не начатое становится заблокированным
        for pid in self.ids:
            deps = [d for d in (self.byid[pid].get("dependencies") or []) if d in st]
            if deps and st[pid] in ("not_started", "planned") and any(st[d] not in CLOSED for d in deps):
                st[pid] = "blocked"
        # каждый статус хотя бы раз (при достаточном реестре)
        if len(self.ids) >= len(STATUSES):
            for name in STATUSES:
                if name in st.values():
                    continue
                counts = {s: list(st.values()).count(s) for s in STATUSES}
                donor = max((x for x in self.ids if counts[st[x]] > 1 and st[x] not in ("blocked",)),
                            key=lambda x: (counts[st[x]], self.rank(x)), default=None)
                if donor is None:
                    continue
                if name == "blocked":
                    deps = [d for d in self.ids if d != donor and st[d] not in CLOSED]
                    if deps:
                        self.byid[donor].setdefault("_demo_dep", deps[0])
                st[donor] = name
        return st

    # --- issues, PR, коммиты, следы в коде
    def gh(self, kind, n):
        return "https://github.com/%s/%s/%d" % (self.remote, "issues" if kind == "issue" else "pull", n)

    def next_no(self):
        self.issue_no += self.rnd.randint(1, 3)
        return self.issue_no

    def day(self, lo=0.05, hi=1.0):
        span = max(1, (self.checked - self.created).days)
        return self.created + timedelta(days=int(span * self.rnd.uniform(lo, hi)))

    def item(self, pid, status, links, overrides):
        rnd, p = self.rnd, self.byid[pid]
        title = str(p.get("title") or pid)
        it = {"status": status, "suggested": status, "confidence": 0.0, "source": "auto", "issues": [], "prs": [], "commits": [],
              "code": [], "scan_diff": [], "blocked_by_open": [], "note": "", "since": None}

        def issue(state, reason=None, match=None, closed=None):
            n = self.next_no()
            m = match or rnd.choices(["explicit", "saved", "similar"], weights=[55, 25, 20])[0]
            iss = {"number": n, "state": state, "state_reason": reason, "title": "%s (%s)" % (title, pid) if m == "explicit" else title,
                   "url": self.gh("issue", n), "labels": rnd.choice([["enhancement"], ["feature"], ["enhancement", "strategy"], []]),
                   "closed_at": iso(closed) if closed else None, "match": m,
                   "score": round(rnd.uniform(0.62, 0.95) if m != "similar" else rnd.uniform(0.38, 0.74), 2)}
            if m == "saved":
                links.setdefault(pid, []).append(n)
            it["issues"].append(iss)
            return iss

        def pr(state, match="explicit"):
            n = self.next_no()
            merged = self.day(0.3, 1.0) if state == "merged" else None
            it["prs"].append({"number": n, "state": state, "title": "%s: %s" % (rnd.choice(["feat", "fix", "docs"]), title.lower()[:70]),
                              "url": self.gh("pr", n), "merged_at": iso(merged) if merged else None, "match": match})

        def commits(k):
            for _ in range(k):
                d = self.day(0.1, 1.0)
                it["commits"].append({"sha": sha(rnd), "date": iso(d), "subject": "%s: %s (%s)" % (
                    rnd.choice(["feat", "fix", "refactor", "docs"]), title.lower()[:60], pid), "match": rnd.choice(["explicit", "files", "terms"])})
            it["commits"].sort(key=lambda c: c["date"], reverse=True)

        def code(k):
            for f in rnd.sample(FILES, k):
                kind = "route" if "routes" in f or "pages" in f else rnd.choice(["path", "feature"])
                it["code"].append({"file": f, "kind": kind, "evidence": rnd.choice([
                    "новая функция по ключевым словам предложения", "маршрут /%s" % pid.lower(), "модуль появился после даты стратегии",
                    "тесты на новую функцию", "упоминание %s в комментарии" % pid])})

        if status == "done":
            issue("closed", "completed", closed=self.day(0.2, 1.0))
            if rnd.random() < 0.7:
                pr("merged")
            commits(rnd.randint(1, 3))
            code(rnd.randint(1, 2))
            if rnd.random() < 0.4:
                it["scan_diff"].append(rnd.choice(["+route /%s" % pid.lower(), "+feature %s" % title[:40], "+tests 6 файлов"]))
            it["confidence"] = round(rnd.uniform(0.78, 0.97), 2)
        elif status == "partial":
            issue("closed", "completed", closed=self.day(0.2, 0.9))
            issue("open")
            commits(rnd.randint(1, 2))
            code(1)
            it["confidence"] = round(rnd.uniform(0.6, 0.85), 2)
            it["note"] = "закрыта часть шагов: %d из %d" % (1, max(2, len(p.get("steps") or []) or 2))
        elif status == "in_progress":
            issue("open")
            if rnd.random() < 0.6:
                pr("open")
            commits(rnd.randint(0, 2))
            it["confidence"] = round(rnd.uniform(0.55, 0.85), 2)
        elif status == "planned":
            issue("open", match=rnd.choice(["explicit", "saved"]))
            it["confidence"] = round(rnd.uniform(0.6, 0.9), 2)
        elif status == "blocked":
            deps = [d for d in (p.get("dependencies") or []) if d in self.byid] or ([p["_demo_dep"]] if p.get("_demo_dep") else [])
            it["blocked_by_open"] = deps
            it["confidence"] = round(rnd.uniform(0.7, 0.9), 2)
            it["note"] = "ждёт предпосылок: " + ", ".join(deps) if deps else "ждёт предпосылок"
        elif status == "dropped":
            issue("closed", "not_planned", match="explicit", closed=self.day(0.3, 1.0))
            it["confidence"] = 0.9
            it["note"] = "issue закрыт как not planned: владелец решил не делать"
        elif status == "obsolete":
            it["confidence"] = 0.8
            it["note"] = "условие предложения изменилось: факт «%s» уже другой" % rnd.choice(["видимость репозитория", "лицензия", "платформа"])
        elif status == "unknown":
            issue("closed", "completed", match="similar")
            it["confidence"] = 0.41
            it["note"] = "противоречивые следы: issue закрыт, а в коде функции нет"
        else:
            it["confidence"] = round(rnd.uniform(0.55, 0.8), 2)
        # источник: решение владельца или связь
        if status in ("dropped",) or (status == "done" and rnd.random() < 0.12):
            it["source"] = "override"
            it["suggested"] = "in_progress" if status == "done" else "planned"
            it["note"] = (it["note"] + "; " if it["note"] else "") + "решение владельца"
            overrides[pid] = {"status": status, "note": "решение владельца (демо)", "date": iso(self.checked), "by": "owner"}
        elif any(i["match"] == "saved" for i in it["issues"]):
            it["source"] = "link"
        if status not in ("not_started",) and rnd.random() < 0.5:
            it["since"] = iso(self.day(0.5, 1.0))
        # поля сверх базовой схемы, которые пишет движок (раздел «Уточнения по итогам реализации отслеживания»)
        it["title"], it["horizon"], it["priority"] = title, p.get("horizon"), self.priority(pid) or None
        it["issues_before"], it["mentions"] = [], []
        return it

    # --- сводки
    def summary(self, st):
        def count(ids):
            c = {s: 0 for s in STATUSES}
            for x in ids:
                c[st[x]] += 1
            return c
        tot = count(self.ids)
        s = {"total": len(self.ids)}
        s.update(tot)
        s["percent_done"] = round(100.0 * tot["done"] / max(1, len(self.ids)), 1)
        for key, fn in (("by_horizon", lambda p: str(p.get("horizon") or "")), ("by_category", lambda p: str(p.get("category") or "")),
                        ("by_priority", lambda p: self.priority(p["id"]))):
            groups = {}
            for p in self.P:
                k = fn(p)
                if k:
                    groups.setdefault(k, []).append(p["id"])
            if groups:
                order = HORIZONS if key == "by_horizon" else ["P0", "P1", "P2", "P3"] if key == "by_priority" else []
                ks = [k for k in order if k in groups] + sorted(k for k in groups if k not in order)
                s[key] = {k: dict({"total": len(groups[k])}, **{x: v for x, v in count(groups[k]).items() if v}) for k in ks}
        return s

    def gantt_progress(self, st):
        cur, tasks = self.month_index, []
        for g in self.gantt:
            s, e = as_int(g.get("start_month")), as_int(g.get("end_month"))
            if s is None and e is None:
                continue
            s, e = (s if s is not None else e), (e if e is not None else s)
            ids = [x for x in (g.get("proposal_ids") or []) if x in st]
            live = [x for x in ids if st[x] not in ("dropped", "obsolete")]
            w = {"done": 1.0, "partial": 0.5, "in_progress": 0.25}
            prog = (sum(w.get(st[x], 0.0) for x in live) / len(live)) if live else (1.0 if ids else 0.0)
            if ids and prog >= 0.999:
                status = "done"
            elif e < cur:
                status = "behind"
            elif s > cur:
                status = "upcoming" if prog == 0 else "partial"
            else:
                expected = (cur - s + 0.5) / float(e - s + 1)
                status = "on_track" if prog >= 0.5 * expected or any(st[x] == "in_progress" for x in live) else (
                    "partial" if prog > 0 else "behind")
            tasks.append({"id": g.get("id"), "task": g.get("task"), "proposal_ids": ids, "start_month": s, "end_month": e,
                          "status": status, "progress": round(prog, 3), "done_ids": [x for x in ids if st[x] in CLOSED],
                          "open_ids": [x for x in ids if st[x] not in CLOSED]})
        return {"current_month": cur, "checked": iso(self.checked), "tasks": tasks}

    def kanban_progress(self, st):
        cols = [str(c.get("name") if isinstance(c, dict) else c) for c in (self.kanban.get("columns") or [])]
        cards = [c for c in (self.kanban.get("cards") or []) if isinstance(c, dict) and c.get("id")]
        if not cols:
            return {"moves": [], "columns": {}}

        def find(words, fallback):
            for w in words:                       # слова — по убыванию точности: «в работе» раньше «работ»
                for c in cols:
                    if w in c.lower():
                        return c
            return cols[max(0, min(len(cols) - 1, fallback))]
        closed, work = find(["закрыт", "done", "готово ✓"], len(cols) - 1), find(["в работе", "работ", "progress"], len(cols) // 2)
        ready = find(["готово к", "ready"], max(0, cols.index(work) - 1))
        measure = find(["измер", "measure"], len(cols) - 2)
        idx = {c: i for i, c in enumerate(cols)}
        res, moves, on_board = {c: [] for c in cols}, [], set()
        for c in cards:
            pid, plan = str(c["id"]), str(c.get("column") or cols[0])
            s = st.get(pid, "unknown")
            to, why = plan, ""
            if s == "done":
                to, why = (measure if self.rnd.random() < 0.4 else closed), "сделано: issue закрыт / PR влит"
            elif s in ("dropped", "obsolete"):
                to, why = closed, "исключено решением владельца" if s == "dropped" else "устарело: условие изменилось"
            elif s in ("in_progress", "partial"):
                to, why = work, "есть открытый issue/PR с активностью" if s == "in_progress" else "закрыта часть шагов"
            elif s == "planned" and idx.get(plan, 0) < idx.get(ready, 0):
                to, why = ready, "issue заведён"
            elif s in ("not_started", "blocked") and idx.get(plan, 0) >= idx.get(work, 0):
                to, why = ready, "следов работы нет" if s == "not_started" else "ждёт предпосылок"
            res.setdefault(to, []).append(pid)
            on_board.add(pid)
            if to != plan:
                moves.append({"id": pid, "from": plan, "to": to, "reason": why})
        target = {"in_progress": work, "partial": work, "done": closed}
        off = [{"id": pid, "status": st[pid], "to": target[st[pid]]} for pid in self.ids if pid not in on_board and st[pid] in target][:8]
        return {"checked": iso(self.checked), "moves": moves, "columns": res, "off_board": off}

    def history(self, st, summary):
        """Три точки: ~⅓ и ~⅔ пути и сам срез; прошлые — та же картина с меньшим числом сделанного."""
        span = max(3, (self.checked - self.created).days)
        pts = []
        for k, frac in ((1, 0.33), (2, 0.66)):
            d = self.created + timedelta(days=int(span * frac))
            s = {key: summary.get(key, 0) for key in ["total"] + STATUSES}
            moved_done = int(round(s["done"] * (1 - frac)))
            moved_work = int(round(s["in_progress"] * (1 - frac) * 0.6))
            s["done"] -= moved_done
            s["in_progress"] = s["in_progress"] - moved_work + int(round(moved_done * 0.6))
            s["not_started"] += moved_work + moved_done - int(round(moved_done * 0.6))
            s["percent_done"] = round(100.0 * s["done"] / max(1, s["total"]), 1)
            pts.append({"date": iso(d), "summary": s, "git_head": full_sha(self.rnd)[:12], "month_index": int(self.months * frac) + 1})
        last = {key: summary.get(key, 0) for key in ["total"] + STATUSES}
        last["percent_done"] = summary.get("percent_done", 0.0)
        pts.append({"date": iso(self.checked), "summary": last, "git_head": full_sha(self.rnd)[:12], "month_index": self.month_index})
        return pts

    # --- всё вместе
    def build(self):
        rnd = self.rnd
        st = self.statuses()
        links, overrides = {}, {}
        items = {pid: self.item(pid, st[pid], links, overrides) for pid in self.ids}
        summary = self.summary(st)
        hist = self.history(st, summary)
        summary["previous_check"] = hist[-2]["date"]
        summary["changed_since_last"] = sum(1 for it in items.values() if it["since"] and it["since"] > hist[-2]["date"])
        gp = self.gantt_progress(st)
        # PR, найденный как issue (kind: pr), подозрительный текст, упоминания в эпиках, «считали отсутствующим»
        with_issues = [pid for pid in sorted(self.ids, key=self.rank) if items[pid]["issues"]]
        if with_issues:
            x = items[with_issues[0]]["issues"][0]
            x["suspicious"] = True
        if len(with_issues) > 1:
            n = self.next_no()
            items[with_issues[1]]["issues"].append({"number": n, "state": "open", "state_reason": None, "title": "PR с черновиком",
                                                    "url": self.gh("pr", n), "labels": [], "closed_at": None, "match": "similar",
                                                    "score": 0.52, "sim": 0.41, "kind": "pr"})
        epic = self.next_no()
        for pid in [x for x in sorted(self.ids, key=self.rank) if st[x] in ("not_started", "planned")][:3]:
            items[pid]["mentions"].append({"kind": "issue", "number": epic, "state": "open", "title": "Эпик: дорожная карта квартала",
                                           "url": self.gh("issue", epic)})
        discrepancies = []
        for pid in [x for x in self.ids if str(self.byid[x].get("current_feature") or "").lower().startswith("нет")][:2]:
            n = self.next_no()
            items[pid]["issues_before"].append({"number": n, "state": "closed", "state_reason": "completed", "title": self.byid[pid].get("title"),
                                                "url": self.gh("issue", n), "labels": [], "closed_at": iso(self.created - timedelta(days=40)),
                                                "match": "explicit", "score": 0.9})
            discrepancies.append({"id": pid, "kind": "closed_before_baseline", "number": n, "title": self.byid[pid].get("title"),
                                  "url": self.gh("issue", n), "score": 0.9, "closed_at": iso(self.created - timedelta(days=40)),
                                  "text": "в стратегии «нет», но #%d закрыт %s" % (n, iso(self.created - timedelta(days=40)))})
        overdue = [{"task": t["id"], "proposals": t["open_ids"] or t["proposal_ids"], "planned_end_month": t["end_month"], "status": "behind"}
                   for t in gp["tasks"] if t["status"] == "behind"]
        # следующие шаги: не начато/запланировано, предпосылки выполнены, по рангу
        def ready(pid):
            deps = [d for d in (self.byid[pid].get("dependencies") or []) if d in st]
            return all(st[d] in CLOSED for d in deps)
        nxt = [pid for pid in sorted(self.ids, key=self.rank) if st[pid] in ("not_started", "planned") and ready(pid)][:7]
        sample_ids = sorted(self.ids, key=self.rank)
        outside = []
        for k in range(min(6, max(3, len(self.ids) // 15))):
            n = self.next_no()
            kind = "pr" if k % 3 == 2 else "issue"
            sug = ["candidate-proposal", "bug", "chore"][k % 3]
            state = {"issue": rnd.choice(["open", "closed"]), "pr": rnd.choice(["merged", "open"])}[kind]
            title = {"candidate-proposal": rnd.choice(["Тёмная тема для отчётов", "Экспорт в Google Sheets", "Импорт из CSV",
                                                       "Шаблон для еженедельного отчёта"]),
                     "bug": rnd.choice(["Падает экспорт при пустом списке", "Неверная дата в дайджесте", "Кнопка «Назад» теряет фильтры"]),
                     "chore": rnd.choice(["Обновить зависимости", "Перейти на Python 3.13 в CI", "Почистить логи"])}[sug]
            outside.append({"kind": kind, "number": n, "title": title, "state": state, "url": self.gh(kind, n), "suggest": sug,
                            "similar_to": [sample_ids[(k * 7) % len(sample_ids)]] if sug == "candidate-proposal" else []})
        aff = [x for x in sample_ids[:12] if st[x] in ("obsolete", "not_started", "planned")][:2] or sample_ids[:1]
        facts = [{"fact": "repo_visibility", "was": "private", "now": "public", "affects": aff[:1]},
                 {"fact": "license", "was": "нет", "now": "MIT", "affects": aff[1:2] or aff[:1]},
                 {"fact": "tests", "was": "12 файлов", "now": "31 файл", "affects": []}]
        revision = []
        for pid in [x for x in sample_ids if st[x] == "done"][:3]:
            ev = ["issue #%d" % items[pid]["issues"][0]["number"]] if items[pid]["issues"] else []
            ev += ["commit %s" % items[pid]["commits"][0]["sha"]] if items[pid]["commits"] else []
            revision.append({"type": "mark_done", "id": pid, "text": "Отметить %s выполненным в разделе 14 и убрать из ближайших шагов" % pid,
                             "reason": "issue закрыт как completed, есть коммиты", "evidence": ev, "sections": [10, 14]})
        for pid in [x for x in sample_ids if st[x] == "obsolete"][:1]:
            revision.append({"type": "obsolete", "id": pid, "text": "Пометить %s устаревшим: условие изменилось" % pid,
                             "reason": items[pid]["note"], "evidence": ["факт: %s" % facts[0]["fact"]], "sections": [2, 10]})
        for t in overdue[:2]:
            revision.append({"type": "reschedule", "id": (t["proposals"] or [None])[0], "text": "Перенести задачу %s на месяц %d–%d"
                             % (t["task"], self.month_index, self.month_index + 2), "reason": "срок (месяц %d) прошёл, работа не завершена"
                             % t["planned_end_month"], "evidence": ["gantt-progress: %s behind" % t["task"]], "sections": [14]})
        for pid in [x for x in sample_ids if st[x] == "blocked"][:1]:
            revision.append({"type": "unblock", "id": pid, "text": "Сначала закрыть предпосылки %s: %s" % (pid, ", ".join(items[pid]["blocked_by_open"]) or "—"),
                             "reason": "предложение ждёт невыполненных предпосылок", "evidence": [], "sections": [10, 14]})
        for pid in [x for x in sample_ids if st[x] == "dropped"][:1]:
            revision.append({"type": "drop", "id": pid, "text": "Исключить %s из плана (решение владельца)" % pid,
                             "reason": "issue закрыт как not planned", "evidence": ["issue #%d" % items[pid]["issues"][0]["number"]] if items[pid]["issues"] else [],
                             "sections": [10, 14, 16]})
        for o in [o for o in outside if o["suggest"] == "candidate-proposal"][:1]:
            revision.append({"type": "add", "id": None, "text": "Добавить предложение: «%s»" % o["title"],
                             "reason": "работа вне стратегии с реальным спросом", "evidence": ["%s #%d" % (o["kind"], o["number"])], "sections": [10]})
        pid = next((x for x in sample_ids if st[x] in ("in_progress", "partial") and self.priority(x) in ("P2", "P3")), None)
        if pid:
            revision.append({"type": "reprioritize", "id": pid, "text": "Поднять приоритет %s: работа уже идёт" % pid,
                             "reason": "открытый PR и коммиты при низком приоритете", "evidence": [], "sections": [10]})
        progress = {
            "version": 1,
            "baseline": {"strategy_dir": ".", "created": iso(self.created), "proposals": len(self.ids), "git_head": None, "scan": "data/repo-scan.json"},
            "checked": iso(self.checked), "months_elapsed": round(self.months, 1), "month_index": self.month_index,
            "sources": {"repo": True, "git_log": True, "scan_diff": True, "issues": True, "prs": True, "gh": "ok", "match_threshold": 0.35,
                        "demo": "make_progress_demo.py — вымышленные данные"},
            "summary": summary, "items": items, "outside_strategy": outside, "facts_changed": facts, "next_actions": nxt,
            "overdue": overdue, "warnings": ["демо: issues, PR и коммиты вымышлены (make_progress_demo.py)"],
            "discrepancies": discrepancies, "notes": ["демо: GitHub не читался — данные сгенерированы"], "remote": self.remote}
        return {"progress": progress, "gantt": gp, "kanban": self.kanban_progress(st), "revision": revision,
                "history": hist, "links": links, "overrides": overrides}


# ---------------------------------------------------------------- автоблок раздела 14
BLOCK_RE = re.compile(r"<!-- progress:start -->.*?<!-- progress:end -->\n?", re.S)


def progress_block(res, demo):
    s = res["progress"]["summary"]
    rows = []
    for hz, lab in (("now", "0–3 мес."), ("next", "3–12 мес."), ("later", "1–2 года"), ("vision", "2+ года")):
        g = (s.get("by_horizon") or {}).get(hz)
        if g:
            rows.append("| %s | %d | %d | %d | %d | %d |" % (lab, g["total"], g.get("done", 0), g.get("partial", 0) + g.get("in_progress", 0),
                                                       g.get("blocked", 0), g.get("not_started", 0) + g.get("planned", 0)))
    top = [p for p in res["progress"]["next_actions"][:3]]
    return ("<!-- progress:start -->\n"
            "**Выполнение на %s** (месяц плана %d): выполнено %s %% (%d из %d), в работе %d, заблокировано %d. Ближайшие шаги: %s.\n\n"
            "| Срок | Всего | Сделано | В работе | Заблокировано | Не начато |\n|---|--:|--:|--:|--:|--:|\n%s\n"
            "<!-- progress:end -->\n") % (res["progress"]["checked"], demo.month_index, str(s["percent_done"]).replace(".", ","), s["done"], s["total"],
                                          s["in_progress"] + s["partial"], s["blocked"], ", ".join(top) or "—", "\n".join(rows))


def apply_block(out, res, demo):
    p = Path(out) / "research" / "strategy.md"
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8")
    block = progress_block(res, demo)
    if BLOCK_RE.search(text):
        text = BLOCK_RE.sub(lambda m: block, text, count=1)
    else:
        m = re.search(r"^##\s+14[.)][^\n]*\n", text, re.M)
        if m:
            text = text[:m.end()] + "\n" + block + "\n" + text[m.end():]
        else:
            text = text.rstrip("\n") + "\n\n## 14. План действий\n\n" + block
    p.write_text(text, encoding="utf-8")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", help="папка прогона <OUT> с data/proposals.json")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--months", type=float, default=2.3, help="месяцев с даты стратегии (по умолчанию 2,3)")
    ap.add_argument("--apply-block", action="store_true", help="вписать автоблок progress:start/end в раздел 14 research/strategy.md")
    a = ap.parse_args(argv)
    demo = Demo(a.out, a.seed, a.months)
    res = demo.build()
    out = demo.out
    write_json(out, "data/progress.json", res["progress"])
    write_json(out, "data/gantt-progress.json", res["gantt"])
    write_json(out, "data/kanban-progress.json", res["kanban"])
    write_json(out, "data/revision.json", res["revision"])
    write_json(out, "data/issue-links.json", res["links"])
    write_json(out, "data/progress-overrides.json", res["overrides"])
    write_json(out, "tracking/history.json", res["history"])
    applied = apply_block(out, res, demo) if a.apply_block else False
    s = res["progress"]["summary"]
    print("Демо-прогресс: %s — срез %s (месяц %d), выполнено %s %% (%d из %d); статусы: %s; задач Ганта: %d (отстают %d); "
          "переносов Kanban: %d; корректировок: %d%s"
          % (out, res["progress"]["checked"], demo.month_index, s["percent_done"], s["done"], s["total"],
             ", ".join("%s %d" % (k, s[k]) for k in STATUSES if s.get(k)), len(res["gantt"]["tasks"]), len(res["progress"]["overdue"]),
             len(res["kanban"]["moves"]), len(res["revision"]), "; автоблок раздела 14 записан" if applied else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
