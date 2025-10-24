import socket
import os
import time
import threading

HOST = "127.0.0.1"
PORT = 8080
SUPPORTED_VERSIONS = ["HTTP/1.1", "HTTP/1.0"]


def handle_request(c):
    try:
        request = c.recv(1024).decode("utf-8")

        lines = request.split("\r\n")
        request_line = lines[0].split()
        if len(request_line) < 3:
            return
        method,path,version = request_line

        if not version in SUPPORTED_VERSIONS:
            c.sendall(build_header(505))
            return
        
        if method != "GET":
            c.sendall(build_header(403))
            return
        
        filepath = "." + path
        if filepath == "./":
            filepath = "./test.html"
        
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
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        body += f"\n<!-- Served at {timestamp} -->".encode()
        headers = build_header(200, filepath)
        
        c.sendall(headers)

       
        frame_size = 50  
        print(f"Serving file in frames: {filepath}")

        for i in range(0, len(body), frame_size):
            frame = body[i:i+frame_size]
          
            frame_header = f"--FRAME {i//frame_size}\r\n".encode()
            c.sendall(frame_header + frame)
            print(f"Sent frame {i//frame_size} for {path} ({len(frame)} bytes)")
            time.sleep(0.1)  


    except Exception as e:
        print("Handler exception:", e)
    finally:
        c.close()

            

def build_header(status_code, filepath=None):
    if status_code == 200 and filepath:
        mtime = time.gmtime(os.path.getmtime(filepath))
        mtime_str = time.strftime("%a, %d %b %Y %H:%M:%S GMT", mtime)
        header = "HTTP/1.1 200 OK\r\n"
        header += f"Last-Modified: {mtime_str}\r\n"
    elif status_code == 304:
        header = "HTTP/1.1 304 Not Modified\r\n"
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
        print(f"Serving on {HOST}:{PORT}")
        while True:
            c, addr = s.accept()
            t = threading.Thread(target=handle_request, args=(c,))
            t.start()

if __name__ == "__main__":
    main()