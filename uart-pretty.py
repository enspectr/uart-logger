import sys
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

LINE_RE = re.compile(r'^([A-Za-z])\s+(\d\d:\d\d:\d\d\.\d+)\s+([0-9A-Fa-f]{2})$')


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
    return "".join(s) or "."


def pretty_115200(frame):
    if frame[:2] == [0xEB, 0x90] and len(frame) == frame[2]:
        frame = frame[2:]
    return " ".join(f"{b:02X}" for b in frame)


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
    lines = [f"{ch} {ts} {fmt(bts)}" for ch, ts, _, bts in frames]

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
