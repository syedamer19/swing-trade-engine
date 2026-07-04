import os
import sys
import subprocess
import urllib.request
import time
import re
import socket

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def download_cloudflared():
    dest = "cloudflared.exe" if sys.platform == "win32" else "./cloudflared"
    if os.path.exists(dest):
        return dest
        
    print("Cloudflared binary not found. Downloading...")
    if sys.platform == "win32":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    elif sys.platform == "darwin":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64"
    else:
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    try:
        with urllib.request.urlopen(req) as response, open(dest, 'wb') as out_file:
            out_file.write(response.read())
        if sys.platform != "win32":
            os.chmod(dest, 0o755)
        print("Cloudflared downloaded successfully!")
        return dest
    except Exception as e:
        print(f"Error downloading cloudflared: {e}")
        sys.exit(1)

def main():
    port = 8503
    
    # 1. Download tunnel binary
    cf_bin = download_cloudflared()
    
    # 2. Check/Start Streamlit app
    streamlit_proc = None
    if not is_port_in_use(port):
        print(f"Starting Streamlit app on port {port}...")
        # Start Streamlit in background
        streamlit_cmd = [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(port)]
        streamlit_proc = subprocess.Popen(streamlit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Wait for port to become active
        for _ in range(15):
            if is_port_in_use(port):
                break
            time.sleep(1)
        else:
            print("Timeout waiting for Streamlit to start.")
            streamlit_proc.terminate()
            sys.exit(1)
    else:
        print(f"Streamlit app is already running on port {port}.")

    # 3. Start Cloudflare Tunnel
    print("Starting secure Cloudflare tunnel...")
    cf_cmd = [cf_bin, "tunnel", "--url", f"http://localhost:{port}"]
    
    # Run cloudflared and capture stderr (where it prints the quick tunnel URL)
    tunnel_proc = subprocess.Popen(cf_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Read stderr line by line until we find the URL
    url_found = None
    start_time = time.time()
    while True:
        line = tunnel_proc.stderr.readline()
        if not line:
            break
            
        # Log line to console for debugging if needed
        # print(line.strip())
        
        # Match trycloudflare url
        match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if match:
            url_found = match.group(0)
            break
            
        # Timeout after 20 seconds
        if time.time() - start_time > 20:
            break
            
    if url_found:
        print("\n" + "="*80)
        print("⚡ SWING TRADE ENGINE IS NOW PUBLICLY ACCESSIBLE!")
        print(f"🔗 Secure Public URL: {url_found}")
        print("="*80 + "\n")
        print("Press Ctrl+C to stop the tunnel and server.")
    else:
        print("Failed to retrieve Cloudflare tunnel URL. Please check the logs.")

    # 4. Keep running until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping tunnel and Streamlit server...")
    finally:
        tunnel_proc.terminate()
        if streamlit_proc:
            streamlit_proc.terminate()
        print("Gracefully stopped all processes.")

if __name__ == "__main__":
    main()
