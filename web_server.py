import socket
import os
import time

HOST = "127.0.0.1"
PORT = 8080

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen(5)
    print("listening on http://{HOST}:{PORT}")
    while True:
        c, addr = s.accept()
        with c:
            print("Connected by", addr)
            handle_request(c)

def handle_request(c):


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