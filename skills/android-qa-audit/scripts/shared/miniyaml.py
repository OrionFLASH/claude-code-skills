#!/usr/bin/env python3
"""Мини-парсер подмножества YAML на стандартной библиотеке (для конфигов скилов).

Поддерживается:
  - словари `key: value`, вложенность отступами (пробелы);
  - списки `- value` и списки словарей `- key: value`;
  - inline-списки `[a, "b c", 3]` и пустые `{}`;
  - скаляры: строки (в кавычках и без), int, float, true/false, null/~;
  - блочные строки `|` и `>`;
  - комментарии `# …` (вне кавычек).
Не поддерживается: якоря, теги, многодокументность, inline-словари с содержимым.

  load(text) -> object        dump(obj) -> text
  python3 miniyaml.py file.yaml   # печатает JSON
"""
import json
import re
import sys

_NUM_INT = re.compile(r"^[-+]?\d+$")
_NUM_FLOAT = re.compile(r"^[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?$")


class YamlError(ValueError):
    pass


def _strip_comment(line):
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote and (quote == "'" or line[i - 1] != "\\"):
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _split_inline(s):
    items, buf, quote = [], [], None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        items.append("".join(buf).strip())
    return items


def _scalar(s):
    s = s.strip()
    if s == "" or s in ("null", "~", "Null", "NULL"):
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if s == "{}":
        return {}
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(x) for x in _split_inline(s[1:-1])]
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return json.loads(s)
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].replace("''", "'")
    if _NUM_INT.match(s):
        return int(s)
    if _NUM_FLOAT.match(s):
        return float(s)
    return s


def _key_value(content):
    """Разбирает 'key: value' с учётом кавычек в ключе. None, если это не пара."""
    m = re.match(r'^("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^\'"\s][^:]*?)\s*:(\s+(.*))?$', content)
    if not m:
        return None
    key = m.group(1)
    if key[0] in "'\"":
        key = _scalar(key)
    return key, (m.group(3) or "")


class _Parser:
    def __init__(self, text):
        self.lines = []
        for raw in text.replace("\t", "    ").splitlines():
            self.lines.append(raw)
        self.i = 0

    def _next_meaningful(self):
        while self.i < len(self.lines):
            stripped = _strip_comment(self.lines[self.i])
            if stripped.strip() and stripped.strip() != "---":
                return len(stripped) - len(stripped.lstrip()), stripped.strip()
            self.i += 1
        return None

    def parse_block(self, indent):
        nxt = self._next_meaningful()
        if nxt is None:
            return None
        ind, content = nxt
        if ind < indent:
            return None
        if content.startswith("- ") or content == "-":
            return self._parse_list(ind)
        return self._parse_map(ind)

    def _block_scalar(self, style, parent_indent):
        self.i += 1
        collected, block_indent = [], None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == "":
                collected.append("")
                self.i += 1
                continue
            ind = len(raw) - len(raw.lstrip())
            if ind <= parent_indent:
                break
            if block_indent is None:
                block_indent = ind
            collected.append(raw[block_indent:])
            self.i += 1
        while collected and collected[-1] == "":
            collected.pop()
        if style.startswith("|"):
            return "\n".join(collected) + ("" if style.endswith("-") else "\n")
        return " ".join(x for x in collected if x) + ("" if style.endswith("-") else "\n")

    def _value_after_key(self, value, indent):
        if value in ("|", ">", "|-", ">-"):
            return self._block_scalar(value, indent)
        if value == "":
            self.i += 1
            nxt = self._next_meaningful()
            if nxt is None or nxt[0] < indent or (nxt[0] == indent and not nxt[1].startswith("-")):
                return None
            if nxt[0] == indent and nxt[1].startswith("-"):
                return self._parse_list(indent)
            return self.parse_block(nxt[0])
        self.i += 1
        return _scalar(value)

    def _parse_map(self, indent):
        result = {}
        while True:
            nxt = self._next_meaningful()
            if nxt is None or nxt[0] < indent:
                break
            ind, content = nxt
            if ind > indent:
                raise YamlError(f"строка {self.i + 1}: неожиданный отступ")
            if content.startswith("- "):
                break
            kv = _key_value(content)
            if kv is None:
                raise YamlError(f"строка {self.i + 1}: ожидалось 'ключ: значение': {content}")
            key, value = kv
            result[key] = self._value_after_key(value, indent)
        return result

    def _parse_list(self, indent):
        result = []
        while True:
            nxt = self._next_meaningful()
            if nxt is None or nxt[0] != indent or not (nxt[1].startswith("- ") or nxt[1] == "-"):
                break
            content = nxt[1][1:].strip()
            if content == "":
                self.i += 1
                result.append(self.parse_block(indent + 1))
                continue
            kv = _key_value(content) if not content.startswith(("'", '"', "[")) else None
            if kv is None:
                self.i += 1
                result.append(_scalar(content))
                continue
            # Элемент-словарь: первая пара на строке с '-', остальные — с отступом indent+2.
            item_indent = indent + 2
            key, value = kv
            item = {key: self._value_after_key(value, item_indent)}
            nxt2 = self._next_meaningful()
            if nxt2 is not None and nxt2[0] > indent and not nxt2[1].startswith("- "):
                item.update(self._parse_map(nxt2[0]))
            result.append(item)
        return result


def load(text):
    return _Parser(text).parse_block(0)


def load_file(path):
    with open(path, encoding="utf-8") as f:
        return load(f.read())


def _dump_scalar(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "" or re.search(r"[:#\[\]{},&*!|>'\"%@`]|^\s|\s$|^-", s) or s.lower() in (
        "true", "false", "null", "yes", "no", "~") or _NUM_INT.match(s) or _NUM_FLOAT.match(s):
        return json.dumps(s, ensure_ascii=False)
    return s


def dump(obj, indent=0):
    pad = " " * indent
    lines = []
    if isinstance(obj, dict):
        if not obj:
            return pad + "{}"
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{_dump_scalar(k)}:")
                lines.append(dump(v, indent + 2))
            elif isinstance(v, str) and "\n" in v:
                lines.append(f"{pad}{_dump_scalar(k)}: |")
                lines.extend(pad + "  " + ln for ln in v.rstrip("\n").split("\n"))
            else:
                lines.append(f"{pad}{_dump_scalar(k)}: {_dump_scalar(v) if not isinstance(v, (dict, list)) else ('{}' if isinstance(v, dict) else '[]')}")
    elif isinstance(obj, list):
        if not obj:
            return pad + "[]"
        for v in obj:
            if isinstance(v, dict) and v:
                sub = dump(v, indent + 2).split("\n")
                lines.append(pad + "- " + sub[0].lstrip())
                lines.extend(sub[1:])
            elif isinstance(v, list) and v:
                lines.append(pad + "-")
                lines.append(dump(v, indent + 2))
            else:
                lines.append(pad + "- " + _dump_scalar(v))
    else:
        lines.append(pad + _dump_scalar(obj))
    return "\n".join(lines)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        sys.exit("Использование: miniyaml.py <file.yaml>  — печатает JSON")
    print(json.dumps(load_file(sys.argv[1]), ensure_ascii=False, indent=2))
