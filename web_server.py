import socket
import os
import time

HOST = "127.0.0.1"
PORT = 8080

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind(HOST, PORT)
    s.listen(5)
    while True:
        c, addr = s.accept()
        with c:
            handle_request(c)

def handle_request(c):


def build_header():