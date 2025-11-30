import sys, serial

if len(sys.argv) < 6:
    print("usage: python uart-logger.py PORT BAUD PARITY(N|E|O) INVERT(0|1) LOG [MAX_BYTES] [GAP_MS]", file=sys.stderr)
    sys.exit(1)
    
#Example: python uart-logger.py COM16 9600 N 1 log.txt 10 1000

port_name, baudrate, parity_mode, invert_flag, log_path, *extra_args = sys.argv[1:]
max_packet_bytes = int(extra_args[0]) if extra_args else 16
gap_timeout_us = int(float(extra_args[1]) * 1000) if len(extra_args) > 1 else 0

serial_port = serial.Serial(port_name, 115200, timeout=0.1)
serial_port.write(f"s{baudrate},{parity_mode.upper()},{invert_flag}\n".encode("ascii"))
serial_port.flush()

log_file = open(log_path, "w", encoding="utf-8", newline="")
raw_buffer = bytearray()
channel_packets = [[], []]
channel_start_time = [0, 0]
last_byte_time = [0, 0]

def flush_channel(channel_index):
    packet = channel_packets[channel_index]
    if not packet:
        return
    timestamp_us = channel_start_time[channel_index]
    seconds, millis = divmod(timestamp_us // 1000, 1000)
    hex_dump = " ".join(f"{byte:02X}" for byte in packet)
    ascii_text = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in packet)
    log_line = f"{'<>'[channel_index]} {seconds:6d}.{millis:03d}  {hex_dump:<48}  {ascii_text}"
    print(log_line, flush=True)
    log_file.write(log_line + "\n")
    log_file.flush()
    packet.clear()
    channel_start_time[channel_index] = 0

try:
    while True:
        read_chunk = serial_port.read(serial_port.in_waiting or 1)
        if not read_chunk:
            for channel_index in (0, 1):
                flush_channel(channel_index)
            continue

        raw_buffer.extend(read_chunk)
        while len(raw_buffer) >= 6:
            channel_id, ts0, ts1, ts2, ts3, data_byte = raw_buffer[:6]
            del raw_buffer[:6]
            if channel_id > 1:
                continue

            timestamp_us = ts0 | (ts1 << 8) | (ts2 << 16) | (ts3 << 24)

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
