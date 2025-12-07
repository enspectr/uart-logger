import argparse
import serial
import time
import sys

MAGIC = 0xA5
L1_BAUD = 9600
L1_PARITY = "N"
L1_INVERT = 1
L2_BAUD = 115200
L2_PARITY = "N"
L2_INVERT = 1

#Example: python uart-logger.py --port1 COM16 --port2 COM18

def parse_args():
    p = argparse.ArgumentParser(prog="uart-logger.py")
    p.add_argument("--port", dest="port1")
    p.add_argument("--port1", dest="port1")
    p.add_argument("--port2")
    a = p.parse_args()
    if not a.port1:
        p.error("missing --port or --port1")
    return a

def safe_name(s):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s)

class Listener:
    def __init__(self, port_name, baudrate, parity_mode, invert_flag, start_tag):
        self.port_name = port_name
        self.parity_mode = parity_mode
        self.invert_flag = invert_flag
        self.serial_port = serial.Serial(port_name, 115200, timeout=0)
        self.serial_port.write(f"s{baudrate},{parity_mode},{invert_flag}\n".encode("ascii"))
        self.serial_port.flush()
        log_name = f"log_{start_tag}_b{baudrate}_p{parity_mode}_i{invert_flag}_{safe_name(port_name)}.txt"
        self.log_file = open(log_name, "w", encoding="utf-8", newline="", buffering=1)
        self.raw_buffer = bytearray()
        self.offset_us = None
        self.tag = safe_name(port_name)

    def poll(self):
        chunk = self.serial_port.read(self.serial_port.in_waiting or 1)
        if not chunk:
            return False

        self.raw_buffer.extend(chunk)

        while len(self.raw_buffer) >= 8:
            magic, channel_id, ts0, ts1, ts2, ts3, data_byte, csum = self.raw_buffer[:8]
            del self.raw_buffer[:8]
            if magic != MAGIC:
                print(f"error: bad magic 0x{magic:02X} on {self.port_name}", file=sys.stderr)
                raise SystemExit(2)
            if channel_id > 1:
                print(f"error: bad channel {channel_id} on {self.port_name}", file=sys.stderr)
                raise SystemExit(2)
            if csum != (channel_id ^ ts0 ^ ts1 ^ ts2 ^ ts3 ^ data_byte):
                print(f"error: checksum mismatch on {self.port_name}", file=sys.stderr)
                raise SystemExit(2)
            ts_us = ts0 | (ts1 << 8) | (ts2 << 16) | (ts3 << 24)
            if self.offset_us is None:
                self.offset_us = time.time_ns() // 1000 - ts_us
            abs_us = ts_us + self.offset_us
            sec = abs_us // 1_000_000
            ms = (abs_us // 1000) % 1000
            t = time.localtime(sec)
            ch = "AB"[channel_id]
            ts_str = f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.{ms:03d}"
            line = f"{ch} {ts_str} {data_byte:02X}"
            print(f"{self.tag}:{line}", flush=True)
            self.log_file.write(line + "\n")
        return True

    def close(self):
        self.log_file.close()
        self.serial_port.close()

def main():
    args = parse_args()
    start_tag = time.strftime("%Y%m%d_%H%M%S")
    listeners = [Listener(args.port1, L1_BAUD, L1_PARITY, L1_INVERT, start_tag)]
    if args.port2:
        listeners.append(Listener(args.port2, L2_BAUD, L2_PARITY, L2_INVERT, start_tag))

    try:
        while True:
            any_data = False
            for l in listeners:
                if l.poll():
                    any_data = True
            if not any_data:
                time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        for l in listeners:
            l.close()

if __name__ == "__main__":
    main()