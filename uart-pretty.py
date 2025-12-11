import sys
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

LINE_RE = re.compile(r'^([A-Za-z])\s+(\d\d:\d\d:\d\d\.\d+)\s+([0-9A-Fa-f]{2})$')
MAX_PERIOD = 12


def parse_entries(path: Path):
    out = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            m = LINE_RE.match(line)
            if not m:
                continue
            ch, ts, hx = m.groups()
            t = datetime.strptime(ts, "%H:%M:%S.%f").time()
            ms = (t.hour * 3600 + t.minute * 60 + t.second) * 1000 + t.microsecond // 1000
            out.append((ch, ts, ms, int(hx, 16)))
    return out


def frames_9600(entries):
    by = defaultdict(list)
    for ch, ts, ms, b in entries:
        by[ch].append((ts, ms, b))

    frames = []
    for ch, seq in by.items():
        buf = None
        for ts, ms, b in seq:
            if b == 0x02:
                buf = [(ts, ms, b)]
                continue
            if buf is not None:
                buf.append((ts, ms, b))
                if b == 0x03:
                    frames.append((ch, buf[0][0], buf[0][1], [x[2] for x in buf]))
                    buf = None
        if buf:
            frames.append((ch, buf[0][0], buf[0][1], [x[2] for x in buf]))
    return frames


def frames_115200(entries):
    by = defaultdict(list)
    for ch, ts, ms, b in entries:
        by[ch].append((ts, ms, b))

    frames = []
    for ch, seq in by.items():
        bs = [b for _, _, b in seq]
        ts_list = [ts for ts, _, _ in seq]
        ms_list = [ms for _, ms, _ in seq]

        i = 0
        n = len(bs)
        while i + 2 < n:
            if bs[i] == 0xEB and bs[i + 1] == 0x90:
                ln = bs[i + 2]
                if 3 <= ln <= 64 and i + ln <= n:
                    frames.append((ch, ts_list[i], ms_list[i], bs[i:i + ln]))
                    i += ln
                    continue
            i += 1
    return frames


def pretty_9600(frame):
    payload = frame[1:-1] if frame[:1] == [0x02] and frame[-1:] == [0x03] else frame
    s = []
    for b in payload:
        s.append(chr(b) if 32 <= b < 127 else f"\\x{b:02X}")
    text = "".join(s)
    if "," in text:
        parts = text.split(",")
        if len(parts) > 1:
            text = ",".join(parts[:-1])
    return text or "."


def pretty_115200(frame):
    if frame[:2] == [0xEB, 0x90] and len(frame) == frame[2]:
        if len(frame) > 4:
            frame = frame[3:-1]
        else:
            frame = []
    return " ".join(f"{b:02X}" for b in frame) or "."


def compress(rows):
    sig = [(c, t) for c, _, t in rows]
    out = []
    i = 0
    n = len(rows)

    while i < n:
        lim = min(MAX_PERIOD, n - i)
        done = False

        for p in range(1, lim + 1):
            if i + 2 * p > n or sig[i:i + p] != sig[i + p:i + 2 * p]:
                continue

            r = 2
            while i + (r + 1) * p <= n and sig[i:i + p] == sig[i + r * p:i + (r + 1) * p]:
                r += 1

            out += rows[i:i + p]
            out.append((None, rows[i][1], f"x{r}"))
            i += r * p
            done = True
            break

        if not done:
            out.append(rows[i])
            i += 1

    return out


def process_file(path: Path):
    entries = parse_entries(path)
    name = path.name.lower()

    if "b115200" in name:
        frames = frames_115200(entries)
        fmt = pretty_115200
    else:
        frames = frames_9600(entries)
        fmt = pretty_9600

    frames.sort(key=lambda x: x[2])

    rows = [(ch, ts, fmt(bts)) for ch, ts, _, bts in frames]
    rows = compress(rows)
    lines = [f"R {ts} {txt}" if ch is None else f"{ch} {ts} {txt}" for ch, ts, txt in rows]

    out_path = path.with_name(path.stem + "_pretty.txt")
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out_path, len(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python uart-pretty.py <logfile1> [logfile2 ...]")
        return 2

    rc = 0
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.is_file():
            print(f"Skip: {arg}")
            rc = 1
            continue
        try:
            out_path, n = process_file(p)
            print(f"{p.name} -> {out_path.name} ({n} lines)")
        except Exception as e:
            print(f"Error: {p}: {e}")
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
