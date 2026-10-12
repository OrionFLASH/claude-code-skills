import re
def parse_fm(text):
    """Minimal YAML frontmatter parser: top-level scalars, block scalars, nested maps (flattened), lists."""
    m = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n?', text, re.S)
    if not m:
        return {}, text
    body = text[m.end():]
    lines = m.group(1).split('\n')
    out = {}
    i = 0
    def unq(v):
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'':
            inner = v[1:-1]
            if v[0] == '"':
                inner = inner.replace('\\"', '"').replace('\\n', ' ')
            else:
                inner = inner.replace("''", "'")
            return inner
        return v
    while i < len(lines):
        ln = lines[i]
        mm = re.match(r'^([A-Za-z0-9_-]+):\s*(.*)$', ln)
        if not mm:
            i += 1; continue
        k, v = mm.group(1), mm.group(2)
        if v.strip() in ('>', '>-', '|', '|-', '>+', '|+'):
            buf = []
            i += 1
            while i < len(lines) and (lines[i].startswith(' ') or lines[i].strip() == ''):
                buf.append(lines[i].strip()); i += 1
            out[k] = (' ' if v.strip().startswith('>') else '\n').join(b for b in buf).strip()
            continue
        if v.strip() == '':
            # nested map or list
            sub = {}; lst = []
            i += 1
            while i < len(lines) and (lines[i].startswith(' ') or lines[i].startswith('\t') or lines[i].strip() == ''):
                s = lines[i].strip()
                if s.startswith('- '):
                    lst.append(unq(s[2:]))
                else:
                    m2 = re.match(r'^([A-Za-z0-9_-]+):\s*(.*)$', s)
                    if m2: sub[m2.group(1)] = unq(m2.group(2))
                i += 1
            out[k] = lst if lst else sub
            continue
        vs = v.strip()
        if vs.startswith('[') and vs.endswith(']'):
            out[k] = [unq(x) for x in vs[1:-1].split(',') if x.strip()]
        else:
            # multi-line plain/quoted continuation
            val = vs
            if (val.startswith('"') and not (len(val) > 1 and val.endswith('"'))) or (val.startswith("'") and not (len(val) > 1 and val.endswith("'"))):
                i += 1
                while i < len(lines) and not re.match(r'^[A-Za-z0-9_-]+:', lines[i]):
                    val += ' ' + lines[i].strip(); i += 1
                out[k] = unq(val); continue
            out[k] = unq(val)
        i += 1
    return out, body
