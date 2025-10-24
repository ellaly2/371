import socket
import threading
import time
from urllib.parse import urlparse

HOST = "127.0.0.1"
PORT = 8888
BUFFER_SIZE = 4096
SUPPORTED_VERSIONS = {"HTTP/1.1", "HTTP/1.0"}

cache = {}          # key: full_url -> {"headers": bytes, "body": bytes, "last_modified": str or None, "stored_at": time}
cache_lock = threading.Lock()

def debug(*a):
    print("[proxy]", *a)

def recv_until_double_crlf(sock, timeout=2.0):
    sock.settimeout(timeout)
    data = b""
    try:
        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data:
                break
    except socket.timeout:
        pass
    return data

def parse_request_header(raw_bytes):
    try:
        text = raw_bytes.decode("iso-8859-1")
    except:
        return None
    parts = text.split("\r\n\r\n", 1)
    header_block = parts[0]
    lines = header_block.split("\r\n")
    if len(lines) == 0:
        return None
    request_line = lines[0].split()
    if len(request_line) < 3:
        return None
    method, target, version = request_line[0], request_line[1], request_line[2]
    headers = {}
    for h in lines[1:]:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return method, target, version, headers

def forward_to_origin(host, port, req_bytes):
    try:
        with socket.create_connection((host, port), timeout=6) as s:
            s.settimeout(6)
            s.sendall(req_bytes)
            parts = []
            while True:
                chunk = s.recv(BUFFER_SIZE)
                if not chunk:
                    break
                parts.append(chunk)
            return b"".join(parts)
    except Exception as e:
        debug("forward error:", e)
        return None

def split_status_headers_body(resp_bytes):
    sep = b"\r\n\r\n"
    i = resp_bytes.find(sep)
    if i == -1:
        return resp_bytes.split(b"\r\n",1)[0] + b"\r\n", resp_bytes, b""
    headers = resp_bytes[:i+4]
    body = resp_bytes[i+4:]
    status_line = headers.split(b"\r\n",1)[0] + b"\r\n"
    return status_line, headers, body

def get_header_value_from_bytes(headers_bytes, name):
    try:
        text = headers_bytes.decode("iso-8859-1")
    except:
        return None
    for line in text.split("\r\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip().lower() == name.lower():
                return v.strip()
    return None

def handle_client(conn, addr):
    debug("connection", addr)
    try:
        raw_req = recv_until_double_crlf(conn)
        if not raw_req:
            return
        parsed = parse_request_header(raw_req)
        if not parsed:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
            return
        method, target, version, headers = parsed
        debug("req:", method, target, version)

        # Version check
        if version not in SUPPORTED_VERSIONS:
            conn.sendall(b"HTTP/1.1 505 HTTP Version Not Supported\r\nConnection: close\r\n\r\n")
            return

        if method.upper() != "GET":
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return

        # Determine full URL (absolute-form) or origin-form
        full_url = None
        if target.lower().startswith("http://") or target.lower().startswith("https://"):
            full_url = target
        else:
            host_hdr = headers.get("host")
            if not host_hdr:
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n")
                return
            # assume http
            full_url = f"http://{host_hdr}{target}"

        parsed_url = urlparse(full_url)
        hostname = parsed_url.hostname
        port = parsed_url.port or (80 if parsed_url.scheme == "http" else 443)
        path = parsed_url.path or "/"
        if parsed_url.query:
            path += "?" + parsed_url.query

        cache_key = f"{parsed_url.scheme}://{hostname}:{port}{path}"

        with cache_lock:
            cached = cache.get(cache_key)

        if cached:
            debug("cache hit", cache_key)
            # if we have last_modified, do conditional GET
            lm = cached.get("last_modified")
            origin_req_lines = [
                f"GET {path} HTTP/1.1",
                f"Host: {hostname}",
                "Connection: close",
                "User-Agent: SimpleProxy/0.1",
            ]
            if lm:
                origin_req_lines.append(f"If-Modified-Since: {lm}")
            origin_req_lines.append("") ; origin_req_lines.append("")
            origin_req = ("\r\n".join(origin_req_lines)).encode("iso-8859-1")
            origin_resp = forward_to_origin(hostname, port, origin_req)
            if origin_resp is None:
                debug("origin unreachable, serving cached (stale)")
                conn.sendall(cached["raw"])
                return
            status_line, headers_bytes, body = split_status_headers_body(origin_resp)
            try:
                status_code = int(status_line.split()[1])
            except:
                status_code = 0
            if status_code == 304:
                debug("origin 304 -> serve cached")
                conn.sendall(cached["raw"])
                return
            elif status_code == 200:
                debug("origin 200 -> update cache and serve")
                new_lm = get_header_value_from_bytes(headers_bytes, "Last-Modified")
                raw = origin_resp
                with cache_lock:
                    cache[cache_key] = {"raw": raw, "last_modified": new_lm, "stored_at": time.time()}
                conn.sendall(origin_resp)
                return
            else:
                debug("origin returned", status_code, "-> forward")
                conn.sendall(origin_resp)
                return

        else:
            debug("cache miss", cache_key)
            origin_req_lines = [
                f"GET {path} HTTP/1.1",
                f"Host: {hostname}",
                "Connection: close",
                "User-Agent: SimpleProxy/0.1",
                "", ""
            ]
            origin_req = ("\r\n".join(origin_req_lines)).encode("iso-8859-1")
            origin_resp = forward_to_origin(hostname, port, origin_req)
            if origin_resp is None:
                conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
                return
            status_line, headers_bytes, body = split_status_headers_body(origin_resp)
            try:
                status_code = int(status_line.split()[1])
            except:
                status_code = 0
            if status_code == 200:
                lm = get_header_value_from_bytes(headers_bytes, "Last-Modified")
                raw = origin_resp
                with cache_lock:
                    cache[cache_key] = {"raw": raw, "last_modified": lm, "stored_at": time.time()}
                debug("stored in cache", cache_key)
            conn.sendall(origin_resp)
            return

    except Exception as e:
        debug("handler exception:", e)
    finally:
        try:
            conn.close()
        except:
            pass

def main():
    debug("starting proxy on", f"{HOST}:{PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(50)
    try:
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        debug("shutting down")
    finally:
        s.close()

if __name__ == "__main__":
    main()
