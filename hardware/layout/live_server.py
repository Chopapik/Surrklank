# WARNING: executes arbitrary Python sent to 127.0.0.1:8765. Run only in a GUI Blender you control.
import bpy, socket, io, contextlib, traceback
HOST, PORT = "127.0.0.1", 8765
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind((HOST, PORT)); srv.listen(1); srv.setblocking(False)
NS = {"bpy": bpy}
def poll():
    try:
        conn, _ = srv.accept()
    except BlockingIOError:
        return 0.1
    conn.settimeout(2); data = b""
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk: break
            data += chunk
            if data.endswith(b"\n#END\n"): break
    except socket.timeout: pass
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try: exec(data.decode(), NS)
        except Exception: traceback.print_exc(file=buf)
    try: conn.sendall(buf.getvalue().encode() or b"ok\n")
    finally: conn.close()
    return 0.1
bpy.app.timers.register(poll, persistent=True)
print("surrklank live server on", HOST, PORT)
