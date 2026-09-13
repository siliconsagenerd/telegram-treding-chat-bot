import threading
import http.server
import socketserver
import os
from derivatives_scanner.core.bot_listener import main

def run_health_check():
    port = int(os.environ.get("PORT", 8080))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Health check server serving at port {port}")
        httpd.serve_forever()

if __name__ == "__main__":
    # Start a dummy health check server to satisfy Render's free tier requirements
    threading.Thread(target=run_health_check, daemon=True).start()
    
    # Start the Telegram bot
    main()
