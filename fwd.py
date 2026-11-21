import socket, threading, base64, urllib.parse, sys

UP = sys.argv[1]  # http://user:pass@host:port
u = urllib.parse.urlsplit(UP)
auth = base64.b64encode(f"{u.username}:{u.password}".encode()).decode()
UPHOST = u.hostname
UPPORT = u.port or 80

def pump(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except Exception:
                pass

def handle(c):
    try:
        data = c.recv(65536)
        line = data.split(b"\r\n")[0].decode(errors="replace")
        parts = line.split()
        if parts[0] != "CONNECT":
            c.close()
            return
        host, port = parts[1].rsplit(":", 1)
        port = int(port)
        s = socket.create_connection((UPHOST, UPPORT), timeout=30)
        req = (f"CONNECT {host}:{port} HTTP/1.1\r\n"
               f"Host: {host}:{port}\r\n"
               f"Proxy-Authorization: Basic {auth}\r\n\r\n").encode()
        s.sendall(req)
        buf = b""
        while b"\r\n\r\n" not in buf:
            d = s.recv(4096)
            if not d:
                break
            buf += d
        if b"200" not in buf.split(b"\r\n")[0]:
            c.close(); s.close(); return
        c.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        t1 = threading.Thread(target=pump, args=(c, s), daemon=True)
        t2 = threading.Thread(target=pump, args=(s, c), daemon=True)
        t1.start(); t2.start()
        t1.join(120); t2.join(120)
    except Exception:
        try:
            c.close()
        except Exception:
            pass

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 3128))
srv.listen(128)
print("fwd listening 3128", flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
