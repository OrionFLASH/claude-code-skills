#!/usr/bin/env python3
"""Fake Android emulator gRPC endpoint for offline tests (HTTP/2 cleartext, prior knowledge). Standard library only.

  fake_grpc.py --port-file F --token T --log L [--window 4096]
Listens on 127.0.0.1:<free port> (written to F), serves connections until killed. Every call is appended to L as JSON:
{"method", "auth_ok", "packets", "audio_bytes", "format": {...}, "clipboard"}. A wrong or missing
`authorization: Bearer <T>` gets a Trailers-Only UNAUTHENTICATED whose grpc-message ECHOES the received header
(to test that the client masks the token). Responses use HPACK indexing and Huffman coding (the client decodes them);
a small stream window (--window) makes the client wait for WINDOW_UPDATE.
Methods: getStatus (EmulatorStatus{version, uptime, booted}), injectAudio (stream AudioPacket -> Empty),
setClipboard (ClipData -> Empty); anything else — UNIMPLEMENTED.
"""
import argparse
import json
import socket
import struct
import sys
import threading
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import grpc_emu as g  # noqa: E402

ENC = {sym: (code, ln) for (ln, code), sym in g.HUFFMAN.items()}


def huff(s):
    bits, n = 0, 0
    for b in s.encode("utf-8"):
        code, ln = ENC[b]
        bits = (bits << ln) | code
        n += ln
    pad = (8 - n % 8) % 8
    bits = (bits << pad) | ((1 << pad) - 1)
    n += pad
    return bits.to_bytes(n // 8, "big") if n else b""


def lit_indexed(name, value, use_huffman=True):
    """Literal with incremental indexing, new name; value Huffman-coded."""
    nb = name.encode("ascii")
    vb = huff(value) if use_huffman else value.encode("utf-8")
    hflag = 0x80 if use_huffman else 0
    v = g.hpack_int(len(vb), 7, hflag) + vb
    return b"\x40" + g.hpack_int(len(nb), 7) + nb + v


def response_headers():
    return b"\x88" + lit_indexed("content-type", "application/grpc")  # :status 200 (static index 8)


def trailers(code, message=""):
    out = lit_indexed("grpc-status", str(code))
    if message:
        out += lit_indexed("grpc-message", message)
    return out


class Conn(threading.Thread):
    def __init__(self, sock, args):
        super().__init__(daemon=True)
        self.s, self.a = sock, args
        self.dec = g.HpackDecoder()
        self.buf = bytearray()
        self.hdrs = {}
        self.stats = {"packets": 0, "audio_bytes": 0, "format": None, "clipboard": None}
        self.ended = False

    def send(self, ftype, flags, stream, payload=b""):
        self.s.sendall(g.frame(ftype, flags, stream, payload))

    def recv(self, n):
        b = bytearray()
        while len(b) < n:
            chunk = self.s.recv(n - len(b))
            if not chunk:
                raise ConnectionError
            b += chunk
        return bytes(b)

    def log(self, rec):
        with open(self.a.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def finish(self, method, auth_ok):
        if method == "getStatus":
            body = g.pb_bytes(1, "35.1.20.0") + g.pb_varint(2, 123456) + g.pb_varint(3, 1)
        else:
            body = b""
        self.send(g.HEADERS, g.END_HEADERS, 1, response_headers())
        self.send(g.DATA, 0, 1, b"\x00" + struct.pack(">I", len(body)) + body)
        self.send(g.HEADERS, g.END_HEADERS | g.END_STREAM, 1, trailers(0))
        self.log({"method": method, "auth_ok": auth_ok, **self.stats})

    def messages(self):
        while len(self.buf) >= 5:
            ln = int.from_bytes(self.buf[1:5], "big")
            if len(self.buf) < 5 + ln:
                return
            msg = bytes(self.buf[5:5 + ln])
            del self.buf[:5 + ln]
            yield msg

    def run(self):
        try:
            if self.recv(24) != g.PREFACE:
                return
            self.send(g.SETTINGS, 0, 0, struct.pack(">HI", 4, self.a.window) + struct.pack(">HI", 5, 16384))
            method = None
            auth_ok = False
            while True:
                head = self.recv(9)
                ln = int.from_bytes(head[:3], "big")
                ftype, flags = head[3], head[4]
                stream = int.from_bytes(head[5:9], "big") & 0x7FFFFFFF
                payload = self.recv(ln) if ln else b""
                if ftype == g.SETTINGS and not flags & g.ACK:
                    self.send(g.SETTINGS, g.ACK, 0)
                elif ftype == g.HEADERS:
                    self.hdrs = dict(self.dec.decode(payload))
                    method = self.hdrs.get(":path", "").rsplit("/", 1)[-1]
                    auth = self.hdrs.get("authorization", "")
                    auth_ok = auth == "Bearer " + self.a.token
                    if not auth_ok:
                        self.send(g.HEADERS, g.END_HEADERS | g.END_STREAM, 1,
                                  response_headers() + trailers(16, f"token is invalid: header was {auth or 'empty'}"))
                        self.log({"method": method, "auth_ok": False})
                        return
                    if method not in ("getStatus", "injectAudio", "setClipboard"):
                        self.send(g.HEADERS, g.END_HEADERS | g.END_STREAM, 1, response_headers() + trailers(12, "unknown"))
                        return
                elif ftype == g.DATA and stream == 1:
                    self.buf += payload
                    for msg in self.messages():
                        f = g.pb_parse(msg)
                        if method == "injectAudio":
                            self.stats["packets"] += 1
                            self.stats["audio_bytes"] += len(f.get(3, [b""])[0])
                            if 1 in f and self.stats["format"] is None:
                                fm = g.pb_parse(f[1][0])
                                self.stats["format"] = {"rate": fm.get(1, [0])[0], "channels": fm.get(2, [0])[0],
                                                        "format": fm.get(3, [0])[0], "mode": fm.get(4, [0])[0]}
                        elif method == "setClipboard":
                            self.stats["clipboard"] = f.get(1, [b""])[0].decode("utf-8")
                    if payload:
                        self.send(g.WINDOW_UPDATE, 0, 0, struct.pack(">I", len(payload)))
                        self.send(g.WINDOW_UPDATE, 0, 1, struct.pack(">I", len(payload)))
                    if flags & g.END_STREAM:
                        self.finish(method, auth_ok)
                        return
                elif ftype == g.PING and not flags & g.ACK:
                    self.send(g.PING, g.ACK, 0, payload)
        except (ConnectionError, OSError):
            return
        finally:
            try:
                self.s.close()
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port-file", required=True)
    ap.add_argument("--token", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--window", type=int, default=4096)
    a = ap.parse_args()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    Path(a.port_file).write_text(str(srv.getsockname()[1]), encoding="utf-8")
    while True:
        sock, _ = srv.accept()
        Conn(sock, a).start()


if __name__ == "__main__":
    main()
