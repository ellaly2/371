import socket
import os
import time

HOST = "127.0.0.1"
PORT = 8080


def handle_request(c):
    request = c.recv(1024).decode("utf-8")
    lines = c.split("\r\n")
    if len(lines) == 0:
        c.sendall(build_header(400))
        return
    
    method, path = lines[0].split()[:2]
    filepath = "." + path
    if filepath == "./":
        filepath = "./test.html"

    if method != "GET":
        c.sendall(build_header(403))
        return
    
    if not os.path.exists(filepath):
        c.sendall(build_header(404))
        return
    
    if "secret" in filepath or not os.access(filepath, os.R_OK):
        c.sendall(build_header(403))
        return
    
    for line in lines:
        if line.startswith("If-Modified-Since:"):
            since_time = line.split(":", 1)[1].strip()
            file_mtime = time.gmtime(os.path.getmtime(filepath))
            file_mtime_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", file_mtime)
            if since_time == file_mtime_str:
                c.sendall(build_header(304))
                return
    with open(filepath, "rb") as f:
        body = f.read()
    headers = build_header(200)
    return headers, body
            

def build_header(status_code):
    if status_code == 200:
        header = "HTTP/1.1 200 OK\r\n"
    elif status_code == 404:
        header = "HTTP/1.1 404 Not Found\r\n"
    elif status_code == 403:
        header = "HTTP/1.1 403 Forbidden\r\n"
    elif status_code == 505:
        header = "HTTP/1.1 505 HTTP Version Not Supported\r\n"
    else:
        header = "HTTP/1.1 400 Bad Request\r\n"
    
    header += "Server: SimpleServer/0.1\r\n"
    header += "Connection: close\r\n\r\n"
    return header.encode()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)
        while True:
            c, addr = s.accept()
            with c:
                handle_request(c)