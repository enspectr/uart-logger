import argparse
import serial
import time
import sys

MAGIC = 0xA5

def parse_args():
    p = argparse.ArgumentParser(prog="uart-logger.py")
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, required=True)
    p.add_argument("--parity", choices=["N", "E", "O", "n", "e", "o"], required=True)
    p.add_argument("--invert", type=int, choices=[0, 1], required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--max-bytes", type=int, default=16)
    p.add_argument("--gap-ms", type=float, default=0)
    return p.parse_args()

#Example: python uart-logger.py --port COM16 --baud 9600 --parity N --invert 1 --log log.txt --max-bytes 10 --gap-ms 1000

args = parse_args()

port_name = args.port
baudrate = args.baud
parity_mode = args.parity.upper()
invert_flag = args.invert
log_path = args.log
max_packet_bytes = args.max_bytes
gap_timeout_us = int(args.gap_ms * 1000)

serial_port = serial.Serial(port_name, 115200, timeout=0.1)
serial_port.write(f"s{baudrate},{parity_mode},{invert_flag}\n".encode("ascii"))
serial_port.flush()

log_file = open(log_path, "w", encoding="utf-8", newline="")
raw_buffer = bytearray()
channel_packets = [[], []]
channel_start_time = [0, 0]
last_byte_time = [0, 0]

offset_us = None

def format_time(ts_us):
    abs_us = ts_us + offset_us if offset_us is not None else ts_us
    sec = abs_us // 1_000_000
    ms = (abs_us // 1000) % 1000
    t = time.localtime(sec)
    return f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.{ms:03d}"

def flush_channel(channel_index):
    packet = channel_packets[channel_index]
    if not packet:
        return
    timestamp_us = channel_start_time[channel_index]
    hex_dump = " ".join(f"{byte:02X}" for byte in packet)
    log_line = f"{'AB'[channel_index]} {format_time(timestamp_us)} {hex_dump}"
    print(log_line, flush=True)
    log_file.write(log_line + "\n")
    log_file.flush()
    packet.clear()
    channel_start_time[channel_index] = 0

def calc_checksum(chan, ts0, ts1, ts2, ts3, data):
    return chan ^ ts0 ^ ts1 ^ ts2 ^ ts3 ^ data

try:
    while True:
        read_chunk = serial_port.read(serial_port.in_waiting or 1)
        if not read_chunk:
            for channel_index in (0, 1):
                flush_channel(channel_index)
            continue

        raw_buffer.extend(read_chunk)
        while len(raw_buffer) >= 8:
            magic, channel_id, ts0, ts1, ts2, ts3, data_byte, csum = raw_buffer[:8]
            del raw_buffer[:8]

            if magic != MAGIC:
                print(f"error: bad magic 0x{magic:02X}", file=sys.stderr)
                sys.exit(2)
            if channel_id > 1:
                print(f"error: bad channel {channel_id}", file=sys.stderr)
                sys.exit(2)
            if csum != calc_checksum(channel_id, ts0, ts1, ts2, ts3, data_byte):
                print("error: checksum mismatch", file=sys.stderr)
                sys.exit(2)

            timestamp_us = ts0 | (ts1 << 8) | (ts2 << 16) | (ts3 << 24)

            if offset_us is None:
                offset_us = time.time_ns() // 1000 - timestamp_us

            if channel_packets[channel_id]:
                if max_packet_bytes and len(channel_packets[channel_id]) >= max_packet_bytes:
                    flush_channel(channel_id)
                elif gap_timeout_us and timestamp_us - last_byte_time[channel_id] > gap_timeout_us:
                    flush_channel(channel_id)

            if not channel_packets[channel_id]:
                channel_start_time[channel_id] = timestamp_us

            channel_packets[channel_id].append(data_byte)
            last_byte_time[channel_id] = timestamp_us
except KeyboardInterrupt:
    pass
finally:
    for channel_index in (0, 1):
        flush_channel(channel_index)
    log_file.close()
    serial_port.close()
