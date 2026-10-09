#!/usr/bin/env python3
"""Minimal gRPC client for the Android emulator controller on the standard library only (references/audio-input.md).

Not a general gRPC library: HTTP/2 over cleartext TCP with prior knowledge (h2c) to 127.0.0.1:<grpc.port>, HPACK
(static + dynamic table, Huffman decoding), flow control, and protobuf encoding of the few messages the skill needs:
  EmulatorController/getStatus    (Empty) -> EmulatorStatus       — «is gRPC reachable and is the token accepted»
  EmulatorController/injectAudio  (stream AudioPacket) -> Empty   — audio into the emulated microphone
  EmulatorController/setClipboard (ClipData) -> Empty             — text into the guest clipboard (non-ASCII input)

Authorization (emulator started with `-grpc <port> -grpc-use-token`): the emulator writes a discovery file
(`adb emu avd discoverypath` prints its path; keys grpc.port, grpc.token, port.serial, avd.name) and checks the
metadata `authorization: Bearer <grpc.token>`. The console token ~/.emulator_console_auth_token is a different
secret and is rejected by gRPC. The token is never printed: every message goes through masking.mask(secrets=…).

  grpc_emu.py discovery <ini file>                   keys of a discovery file (token masked)
  grpc_emu.py status --port P --token-file F         getStatus (debugging; adb_helpers.py mic-status does this)
Python 3.9+, standard library only.
"""
import argparse
import json
import os
import re
import socket
import struct
import sys
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from masking import mask  # noqa: E402

SERVICE = "/android.emulation.control.EmulatorController/"

# ---------------------------------------------------------------- protobuf (wire format)

def varint(n):
    n = int(n)
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def pb_varint(field, value):
    return varint(field << 3 | 0) + varint(value) if value else b""


def pb_bytes(field, data):
    data = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return varint(field << 3 | 2) + varint(len(data)) + data


def pb_parse(data):
    """bytes -> {field: [values]} (varint -> int, length-delimited -> bytes, fixed -> int)."""
    out, i = {}, 0
    while i < len(data):
        key, i = _read_varint(data, i)
        field, wt = key >> 3, key & 7
        if wt == 0:
            val, i = _read_varint(data, i)
        elif wt == 2:
            ln, i = _read_varint(data, i)
            val, i = data[i:i + ln], i + ln
        elif wt == 1:
            val, i = struct.unpack_from("<Q", data, i)[0], i + 8
        elif wt == 5:
            val, i = struct.unpack_from("<I", data, i)[0], i + 4
        else:
            raise ValueError(f"protobuf: неизвестный тип поля {wt}")
        out.setdefault(field, []).append(val)
    return out


def _read_varint(data, i):
    shift = n = 0
    while True:
        if i >= len(data):
            raise ValueError("protobuf: обрыв varint")
        b = data[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7


SAMPLE_FORMAT = {1: 0, 2: 1}  # sample width in bytes -> AudioFormat.SampleFormat (AUD_FMT_U8 = 0, AUD_FMT_S16 = 1)
CHANNELS = {1: 0, 2: 1}       # Mono = 0, Stereo = 1
MODE_UNSPECIFIED, MODE_REAL_TIME = 0, 1


def audio_format(rate, channels, width, mode=MODE_UNSPECIFIED):
    return (pb_varint(1, rate) + pb_varint(2, CHANNELS[channels]) + pb_varint(3, SAMPLE_FORMAT[width]) +
            pb_varint(4, mode))


def audio_packet(fmt, audio, ts_us=None):
    """AudioPacket{format = 1 (only the first one is honoured), timestamp = 2 (µs), audio = 3}."""
    return (pb_bytes(1, fmt) if fmt is not None else b"") + pb_varint(2, ts_us or int(time.time() * 1e6)) + pb_bytes(3, audio)


def decode_status(data):
    """EmulatorStatus: version = 1 (string), uptime = 2 (ms), booted = 3 (bool) — the rest is not needed."""
    f = pb_parse(data or b"")
    ver = f.get(1, [b""])[0]
    return {"version": ver.decode("utf-8", "replace") if isinstance(ver, bytes) else str(ver),
            "uptime_ms": f.get(2, [None])[0], "booted": bool(f.get(3, [0])[0])}


# ---------------------------------------------------------------- HPACK (RFC 7541)

STATIC = [
    (":authority", ""), (":method", "GET"), (":method", "POST"), (":path", "/"), (":path", "/index.html"),
    (":scheme", "http"), (":scheme", "https"), (":status", "200"), (":status", "204"), (":status", "206"),
    (":status", "304"), (":status", "400"), (":status", "404"), (":status", "500"), ("accept-charset", ""),
    ("accept-encoding", "gzip, deflate"), ("accept-language", ""), ("accept-ranges", ""), ("accept", ""),
    ("access-control-allow-origin", ""), ("age", ""), ("allow", ""), ("authorization", ""), ("cache-control", ""),
    ("content-disposition", ""), ("content-encoding", ""), ("content-language", ""), ("content-length", ""),
    ("content-location", ""), ("content-range", ""), ("content-type", ""), ("cookie", ""), ("date", ""), ("etag", ""),
    ("expect", ""), ("expires", ""), ("from", ""), ("host", ""), ("if-match", ""), ("if-modified-since", ""),
    ("if-none-match", ""), ("if-range", ""), ("if-unmodified-since", ""), ("last-modified", ""), ("link", ""),
    ("location", ""), ("max-forwards", ""), ("proxy-authenticate", ""), ("proxy-authorization", ""), ("range", ""),
    ("referer", ""), ("refresh", ""), ("retry-after", ""), ("server", ""), ("set-cookie", ""),
    ("strict-transport-security", ""), ("transfer-encoding", ""), ("user-agent", ""), ("vary", ""), ("via", ""),
    ("www-authenticate", ""),
]
# Huffman code of RFC 7541 Appendix B: symbol i -> "<code hex>/<bit length>" (256 = EOS)
_HUFF = (
    "1ff8/13,7fffd8/23,fffffe2/28,fffffe3/28,fffffe4/28,fffffe5/28,fffffe6/28,fffffe7/28,fffffe8/28,"
    "ffffea/24,3ffffffc/30,fffffe9/28,fffffea/28,3ffffffd/30,fffffeb/28,fffffec/28,fffffed/28,fffffee/28,"
    "fffffef/28,ffffff0/28,ffffff1/28,ffffff2/28,3ffffffe/30,ffffff3/28,ffffff4/28,ffffff5/28,ffffff6/28,"
    "ffffff7/28,ffffff8/28,ffffff9/28,ffffffa/28,ffffffb/28,14/6,3f8/10,3f9/10,ffa/12,1ff9/13,15/6,f8/8,"
    "7fa/11,3fa/10,3fb/10,f9/8,7fb/11,fa/8,16/6,17/6,18/6,0/5,1/5,2/5,19/6,1a/6,1b/6,1c/6,1d/6,1e/6,1f/6,"
    "5c/7,fb/8,7ffc/15,20/6,ffb/12,3fc/10,1ffa/13,21/6,5d/7,5e/7,5f/7,60/7,61/7,62/7,63/7,64/7,65/7,66/7,"
    "67/7,68/7,69/7,6a/7,6b/7,6c/7,6d/7,6e/7,6f/7,70/7,71/7,72/7,fc/8,73/7,fd/8,1ffb/13,7fff0/19,1ffc/13,"
    "3ffc/14,22/6,7ffd/15,3/5,23/6,4/5,24/6,5/5,25/6,26/6,27/6,6/5,74/7,75/7,28/6,29/6,2a/6,7/5,2b/6,76/7,"
    "2c/6,8/5,9/5,2d/6,77/7,78/7,79/7,7a/7,7b/7,7ffe/15,7fc/11,3ffd/14,1ffd/13,ffffffc/28,fffe6/20,3fffd2/22,"
    "fffe7/20,fffe8/20,3fffd3/22,3fffd4/22,3fffd5/22,7fffd9/23,3fffd6/22,7fffda/23,7fffdb/23,7fffdc/23,"
    "7fffdd/23,7fffde/23,ffffeb/24,7fffdf/23,ffffec/24,ffffed/24,3fffd7/22,7fffe0/23,ffffee/24,7fffe1/23,"
    "7fffe2/23,7fffe3/23,7fffe4/23,1fffdc/21,3fffd8/22,7fffe5/23,3fffd9/22,7fffe6/23,7fffe7/23,ffffef/24,"
    "3fffda/22,1fffdd/21,fffe9/20,3fffdb/22,3fffdc/22,7fffe8/23,7fffe9/23,1fffde/21,7fffea/23,3fffdd/22,"
    "3fffde/22,fffff0/24,1fffdf/21,3fffdf/22,7fffeb/23,7fffec/23,1fffe0/21,1fffe1/21,3fffe0/22,1fffe2/21,"
    "7fffed/23,3fffe1/22,7fffee/23,7fffef/23,fffea/20,3fffe2/22,3fffe3/22,3fffe4/22,7ffff0/23,3fffe5/22,"
    "3fffe6/22,7ffff1/23,3ffffe0/26,3ffffe1/26,fffeb/20,7fff1/19,3fffe7/22,7ffff2/23,3fffe8/22,1ffffec/25,"
    "3ffffe2/26,3ffffe3/26,3ffffe4/26,7ffffde/27,7ffffdf/27,3ffffe5/26,fffff1/24,1ffffed/25,7fff2/19,"
    "1fffe3/21,3ffffe6/26,7ffffe0/27,7ffffe1/27,3ffffe7/26,7ffffe2/27,fffff2/24,1fffe4/21,1fffe5/21,"
    "3ffffe8/26,3ffffe9/26,ffffffd/28,7ffffe3/27,7ffffe4/27,7ffffe5/27,fffec/20,fffff3/24,fffed/20,1fffe6/21,"
    "3fffe9/22,1fffe7/21,1fffe8/21,7ffff3/23,3fffea/22,3fffeb/22,1ffffee/25,1ffffef/25,fffff4/24,fffff5/24,"
    "3ffffea/26,7ffff4/23,3ffffeb/26,7ffffe6/27,3ffffec/26,3ffffed/26,7ffffe7/27,7ffffe8/27,7ffffe9/27,"
    "7ffffea/27,7ffffeb/27,ffffffe/28,7ffffec/27,7ffffed/27,7ffffee/27,7ffffef/27,7fffff0/27,3ffffee/26,"
    "3fffffff/30")
HUFFMAN = {}
for _sym, _item in enumerate(_HUFF.split(",")):
    _code, _len = _item.split("/")
    HUFFMAN[(int(_len), int(_code, 16))] = _sym


def huffman_decode(data):
    out, code, length = bytearray(), 0, 0
    for byte in data:
        for bit in range(7, -1, -1):
            code = (code << 1) | ((byte >> bit) & 1)
            length += 1
            sym = HUFFMAN.get((length, code))
            if sym is not None:
                if sym == 256:
                    raise ValueError("HPACK: EOS в строке")
                out.append(sym)
                code = length = 0
            elif length > 30:
                raise ValueError("HPACK: неверный код Хаффмана")
    if length > 7 or code != (1 << length) - 1:  # padding: at most 7 bits, all ones (prefix of EOS)
        raise ValueError("HPACK: неверное дополнение")
    return bytes(out)


def hpack_int(value, prefix_bits, first=0):
    limit = (1 << prefix_bits) - 1
    if value < limit:
        return bytes([first | value])
    out = bytearray([first | limit])
    value -= limit
    while value >= 128:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _hpack_read_int(data, i, prefix_bits):
    limit = (1 << prefix_bits) - 1
    value = data[i] & limit
    i += 1
    if value < limit:
        return value, i
    shift = 0
    while True:
        b = data[i]
        i += 1
        value += (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return value, i


def hpack_encode(headers):
    """Literal header fields without indexing, new name, no Huffman: always valid, no shared state."""
    out = bytearray()
    for name, value in headers:
        n, v = name.encode("ascii"), value.encode("utf-8")
        out += b"\x00" + hpack_int(len(n), 7) + n + hpack_int(len(v), 7) + v
    return bytes(out)


class HpackDecoder:
    def __init__(self, max_size=4096):
        self.dynamic, self.max_size = [], max_size

    def _size(self):
        return sum(32 + len(n) + len(v) for n, v in self.dynamic)

    def _evict(self):
        while self.dynamic and self._size() > self.max_size:
            self.dynamic.pop()

    def _get(self, idx):
        if idx <= 0:
            raise ValueError("HPACK: индекс 0")
        if idx <= len(STATIC):
            return STATIC[idx - 1]
        j = idx - len(STATIC) - 1
        if j >= len(self.dynamic):
            raise ValueError(f"HPACK: нет записи {idx}")
        return self.dynamic[j]

    def _string(self, data, i):
        huff = bool(data[i] & 0x80)
        ln, i = _hpack_read_int(data, i, 7)
        raw = data[i:i + ln]
        return (huffman_decode(raw) if huff else raw).decode("utf-8", "replace"), i + ln

    def decode(self, data):
        headers, i = [], 0
        while i < len(data):
            b = data[i]
            if b & 0x80:                      # indexed
                idx, i = _hpack_read_int(data, i, 7)
                headers.append(self._get(idx))
            elif b & 0x40:                    # literal with incremental indexing
                idx, i = _hpack_read_int(data, i, 6)
                name = self._get(idx)[0] if idx else None
                if name is None:
                    name, i = self._string(data, i)
                value, i = self._string(data, i)
                headers.append((name, value))
                self.dynamic.insert(0, (name, value))
                self._evict()
            elif b & 0x20:                    # dynamic table size update
                self.max_size, i = _hpack_read_int(data, i, 5)
                self._evict()
            else:                             # literal without indexing / never indexed
                idx, i = _hpack_read_int(data, i, 4)
                name = self._get(idx)[0] if idx else None
                if name is None:
                    name, i = self._string(data, i)
                value, i = self._string(data, i)
                headers.append((name, value))
        return headers


# ---------------------------------------------------------------- HTTP/2 + gRPC

PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"
DATA, HEADERS, PRIORITY, RST_STREAM, SETTINGS, PUSH_PROMISE, PING, GOAWAY, WINDOW_UPDATE, CONTINUATION = range(10)
END_STREAM, ACK, END_HEADERS, PADDED, PRIO = 0x1, 0x1, 0x4, 0x8, 0x20
OUR_WINDOW = 1 << 24
GRPC_CODES = {0: "OK", 1: "CANCELLED", 2: "UNKNOWN", 3: "INVALID_ARGUMENT", 4: "DEADLINE_EXCEEDED", 5: "NOT_FOUND",
              6: "ALREADY_EXISTS", 7: "PERMISSION_DENIED", 8: "RESOURCE_EXHAUSTED", 9: "FAILED_PRECONDITION",
              10: "ABORTED", 11: "OUT_OF_RANGE", 12: "UNIMPLEMENTED", 13: "INTERNAL", 14: "UNAVAILABLE",
              15: "DATA_LOSS", 16: "UNAUTHENTICATED"}


class GrpcError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def frame(ftype, flags, stream, payload=b""):
    return struct.pack(">I", len(payload))[1:] + bytes([ftype, flags]) + struct.pack(">I", stream & 0x7FFFFFFF) + payload


class Call:
    """One gRPC call on its own HTTP/2 connection (stream 1)."""

    def __init__(self, port, token=None, host="127.0.0.1", timeout=10):
        self.token, self.port = token, port
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        self.sock.settimeout(None)
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.conn_window = 65535
        self.stream_window = 65535
        self.peer_initial = 65535
        self.max_frame = 16384
        self.decoder = HpackDecoder()
        self.headers, self.trailers, self.body = None, None, bytearray()
        self.closed = False          # stream ended by the server (END_STREAM / RST_STREAM / GOAWAY / socket)
        self.error = None
        self._block, self._block_end = bytearray(), False
        self.reader = threading.Thread(target=self._read_loop, daemon=True)
        self._send(PREFACE + frame(SETTINGS, 0, 0, struct.pack(">HI", 2, 0) + struct.pack(">HI", 4, OUR_WINDOW))
                   + frame(WINDOW_UPDATE, 0, 0, struct.pack(">I", OUR_WINDOW - 65535)))
        self.reader.start()

    def secret(self, text):
        return mask(str(text), secrets=(self.token,) if self.token else ())

    # -- io
    def _send(self, data):
        with self.lock:
            self.sock.sendall(data)

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("соединение закрыто сервером")
            buf += chunk
        return bytes(buf)

    def _read_loop(self):
        try:
            while True:
                head = self._recv_exact(9)
                ln = int.from_bytes(head[:3], "big")
                ftype, flags = head[3], head[4]
                stream = int.from_bytes(head[5:9], "big") & 0x7FFFFFFF
                payload = self._recv_exact(ln) if ln else b""
                self._on_frame(ftype, flags, stream, payload)
        except (OSError, ConnectionError, ValueError) as ex:
            with self.cond:
                if not self.closed:
                    self.error = self.error or f"соединение прервано: {ex}"
                self.closed = True
                self.cond.notify_all()

    def _strip_padding(self, flags, payload):
        if flags & PADDED:
            pad = payload[0]
            payload = payload[1:len(payload) - pad]
        return payload

    def _on_frame(self, ftype, flags, stream, payload):
        if ftype == SETTINGS and not flags & ACK:
            for k in range(0, len(payload) - 5, 6):
                ident, val = struct.unpack_from(">HI", payload, k)
                if ident == 4:
                    with self.cond:
                        self.stream_window += val - self.peer_initial
                        self.peer_initial = val
                        self.cond.notify_all()
                elif ident == 5:
                    self.max_frame = val
            self._send(frame(SETTINGS, ACK, 0))
        elif ftype == PING and not flags & ACK:
            self._send(frame(PING, ACK, 0, payload))
        elif ftype == WINDOW_UPDATE:
            inc = struct.unpack(">I", payload[:4])[0] & 0x7FFFFFFF
            with self.cond:
                if stream == 0:
                    self.conn_window += inc
                else:
                    self.stream_window += inc
                self.cond.notify_all()
        elif ftype in (HEADERS, CONTINUATION) and stream == 1:
            if ftype == HEADERS:
                payload = self._strip_padding(flags, payload)
                if flags & PRIO:
                    payload = payload[5:]
                self._block, self._block_end = bytearray(payload), bool(flags & END_STREAM)
            else:
                self._block += payload
            if flags & END_HEADERS:
                hdrs = dict(self.decoder.decode(bytes(self._block)))
                with self.cond:
                    if self.headers is None and not self._block_end:
                        self.headers = hdrs
                    elif self.headers is None:   # Trailers-Only: the call failed before any message
                        self.headers, self.trailers = hdrs, hdrs
                    else:
                        self.trailers = hdrs
                    if self._block_end:
                        self.closed = True
                    self.cond.notify_all()
        elif ftype == DATA and stream == 1:
            data = self._strip_padding(flags, payload)
            with self.cond:
                self.body += data
                if flags & END_STREAM:
                    self.closed = True
                self.cond.notify_all()
            if payload:
                self._send(frame(WINDOW_UPDATE, 0, 0, struct.pack(">I", len(payload))) +
                           frame(WINDOW_UPDATE, 0, 1, struct.pack(">I", len(payload))))
        elif ftype == RST_STREAM and stream == 1:
            code = struct.unpack(">I", payload[:4])[0]
            with self.cond:
                self.error, self.closed = f"сервер сбросил поток (RST_STREAM, код {code})", True
                self.cond.notify_all()
        elif ftype == GOAWAY:
            code = struct.unpack(">I", payload[4:8])[0] if len(payload) >= 8 else None
            debug = payload[8:].decode("utf-8", "replace")
            with self.cond:
                if not self.closed:
                    self.error = f"сервер закрыл соединение (GOAWAY {code}){': ' + debug if debug else ''}"
                    self.closed = True
                self.cond.notify_all()

    # -- call
    def start(self, method):
        hdrs = [(":method", "POST"), (":scheme", "http"), (":path", SERVICE + method),
                (":authority", f"127.0.0.1:{self.port}"), ("content-type", "application/grpc"), ("te", "trailers"),
                ("user-agent", "android-qa-audit-grpc-stdlib/1.0")]
        if self.token:
            hdrs.append(("authorization", "Bearer " + self.token))
        self._send(frame(HEADERS, END_HEADERS, 1, hpack_encode(hdrs)))

    def send_message(self, payload, end=False, timeout=30):
        """One gRPC message (5-byte prefix + protobuf), split by frame size and flow-control windows."""
        data = b"\x00" + struct.pack(">I", len(payload)) + payload
        pos = 0
        deadline = time.time() + timeout
        while pos < len(data):
            with self.cond:
                while (self.conn_window <= 0 or self.stream_window <= 0) and not self.closed:
                    left = deadline - time.time()
                    if left <= 0:
                        raise GrpcError("сервер не принимает данные (окно HTTP/2 не открылось)")
                    self.cond.wait(min(left, 1.0))
                if self.closed:
                    raise GrpcError(self.result_text())
                n = min(len(data) - pos, self.conn_window, self.stream_window, self.max_frame)
                self.conn_window -= n
                self.stream_window -= n
            last = pos + n >= len(data)
            self._send(frame(DATA, END_STREAM if (end and last) else 0, 1, data[pos:pos + n]))
            pos += n

    def end(self):
        if not self.closed:
            self._send(frame(DATA, END_STREAM, 1))

    def wait(self, timeout=30):
        with self.cond:
            deadline = time.time() + timeout
            while not self.closed:
                left = deadline - time.time()
                if left <= 0:
                    raise GrpcError(f"нет ответа gRPC за {timeout} с", 4)
                self.cond.wait(min(left, 1.0))
        return self.result()

    def status(self):
        t = self.trailers or {}
        code = t.get("grpc-status")
        return (int(code) if code is not None and str(code).isdigit() else None), \
            urllib.parse.unquote(t.get("grpc-message", ""))

    def result_text(self):
        code, msg = self.status()
        if code is None:
            return self.secret(self.error or "поток закрыт без статуса gRPC")
        return self.secret(f"gRPC {GRPC_CODES.get(code, code)}" + (f": {msg}" if msg else ""))

    def result(self):
        code, msg = self.status()
        if code is None:
            raise GrpcError(self.result_text())
        if code != 0:
            raise GrpcError(self.result_text(), code)
        body = bytes(self.body)
        return body[5:5 + int.from_bytes(body[1:5], "big")] if len(body) >= 5 else b""

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def unary(port, token, method, payload=b"", timeout=15):
    call = Call(port, token, timeout=timeout)
    try:
        call.start(method)
        call.send_message(payload, end=True, timeout=timeout)
        return call.wait(timeout)
    finally:
        call.close()


def get_status(port, token, timeout=10):
    return decode_status(unary(port, token, "getStatus", b"", timeout))


def set_clipboard(port, token, text, timeout=10):
    unary(port, token, "setClipboard", pb_bytes(1, text), timeout)


def inject_audio(port, token, chunks, rate, channels, width, mode=MODE_UNSPECIFIED, lead_s=0.2, on_progress=None,
                 stop=None):
    """Stream PCM chunks (bytes) in real time: the emulator buffers ≤ 300 ms, so the client keeps ≤ lead_s ahead.
    Returns {"seconds_sent", "packets"}; raises GrpcError with a masked message."""
    call = Call(port, token)
    fmt = audio_format(rate, channels, width, mode)
    frame_bytes = channels * width
    sent_s, packets = 0.0, 0
    t0 = time.time()
    try:
        call.start("injectAudio")
        for chunk in chunks:
            if stop is not None and stop.is_set():
                break
            call.send_message(audio_packet(fmt if packets == 0 else None, chunk))
            packets += 1
            sent_s += len(chunk) / float(frame_bytes * rate)
            ahead = sent_s - (time.time() - t0)
            if ahead > lead_s:
                time.sleep(ahead - lead_s)
            if on_progress and packets % 50 == 0:
                on_progress(sent_s)
            if call.closed:
                break
        call.end()
        call.wait(timeout=max(10, lead_s + 5))
        return {"seconds_sent": round(sent_s, 2), "packets": packets}
    finally:
        call.close()


# ---------------------------------------------------------------- discovery file

def parse_ini(text):
    data = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", ";")) and "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def running_dirs():
    """Folders where the emulator advertises running instances (pid_<pid>.ini), most likely first."""
    home = Path(os.path.expanduser("~"))
    dirs = []
    if os.environ.get("ANDROID_QA_EMU_RUNNING_DIR"):
        dirs.append(Path(os.environ["ANDROID_QA_EMU_RUNNING_DIR"]))
    if sys.platform == "darwin":
        dirs.append(home / "Library/Caches/TemporaryItems/avd/running")
    elif os.name == "nt":
        dirs.append(Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local") / "Temp/avd/running")
    else:
        if os.environ.get("XDG_RUNTIME_DIR"):
            dirs.append(Path(os.environ["XDG_RUNTIME_DIR"]) / "avd/running")
        if hasattr(os, "getuid"):
            dirs.append(Path(f"/run/user/{os.getuid()}/avd/running"))
        dirs += [Path("/tmp/avd/running"), Path(f"/tmp/android-{os.environ.get('USER', '')}/avd/running")]
    dirs.append(home / ".android/avd/running")
    return dirs


def find_discovery(console_port, discoverypath=None):
    """(path, data) of the discovery file of the emulator with this console port (5554…) or (None, {})."""
    cands = [Path(discoverypath)] if discoverypath else []
    for d in running_dirs():
        if d.is_dir():
            cands += sorted(d.glob("pid_*.ini"), key=lambda p: -p.stat().st_mtime)
    for p in cands:
        try:
            data = parse_ini(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if discoverypath and p == Path(discoverypath):
            return p, data
        if str(data.get("port.serial")) == str(console_port):
            return p, data
    return None, {}


def public(data):
    """Discovery keys safe to print: tokens and keys are replaced by «есть»."""
    return {k: ("есть (не печатается)" if re.search(r"token|jwk|key|cert|secret", k, re.I) else v) for k, v in data.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discovery")
    d.add_argument("ini")
    s = sub.add_parser("status")
    s.add_argument("--port", type=int, required=True)
    s.add_argument("--token-file", help="файл с токеном (не печатается); без него — без авторизации")
    a = ap.parse_args()
    if a.cmd == "discovery":
        print(json.dumps(public(parse_ini(Path(a.ini).read_text(encoding="utf-8", errors="replace"))), ensure_ascii=False))
        return
    token = Path(a.token_file).read_text(encoding="utf-8").strip() if a.token_file else None
    try:
        print(json.dumps(get_status(a.port, token), ensure_ascii=False))
    except (GrpcError, OSError) as ex:
        print(mask(f"gRPC: {ex}", secrets=(token,) if token else ()), file=sys.stderr)
        sys.exit(5)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
