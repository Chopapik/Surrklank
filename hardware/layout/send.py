# Sends a Python file to live_server.py (127.0.0.1:8765); it will be executed in Blender.
import os, socket, sys
path = os.path.abspath(sys.argv[1])
# __file__ lets the sent script find its sibling modules (fdd_model*.py)
code = f"__file__ = {path!r}\n" + open(path).read() + "\n#END\n"
s = socket.create_connection(("127.0.0.1", 8765), timeout=10)
s.sendall(code.encode()); print(s.recv(65536).decode())
