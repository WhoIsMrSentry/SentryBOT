import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

test_code = """
import sys
import os
import requests
import json
import time

print("Testing direct Ollama chat from Pi...")
url = "http://whoismrsentry.local:11434/api/chat"
payload = {
    "model": "qwen3.5:9b",
    "messages": [{"role": "user", "content": "Kendini 1 cumleyle tanit"}],
    "stream": False,
    "options": {"num_predict": 50, "temperature": 0.4}
}
t0 = time.time()
try:
    r = requests.post(url, json=payload, timeout=45)
    print(f"Status: {r.status_code} in {time.time()-t0:.2f}s")
    msg = r.json().get('message', {}).get('content')
    print("OLLAMA RESPONSE:", msg)
except Exception as e:
    print("Failed:", e)
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > ~/SentryBOT/test_chat_quick.py\n" + test_code + "\nEOF\n")
stdout.read()

print("Running test_chat_quick.py on Pi...")
stdin, stdout, stderr = ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python test_chat_quick.py", timeout=50)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print("STDOUT:\n", out)
if err: print("STDERR:\n", err)

ssh.close()
