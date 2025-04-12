from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ------------------------------------------
# Serveur HTTP keep-alive
# ------------------------------------------
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot actif.")
    def log_message(self, format, *args):
        return

def keep_alive(port=10000):
    try:
        server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
        thread = threading.Thread(target=server.serve_forever, name="KeepAliveThread")
        thread.daemon = True
        thread.start()
        print(f"✅ Serveur keep-alive lancé sur le port {port}")
    except Exception as e:
        print(f"❌ Erreur keep-alive: {e}")

if __name__ == "__main__":
    keep_alive()
