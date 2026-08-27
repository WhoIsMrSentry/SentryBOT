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

print("=== TESTING OLLAMA ENDPOINT FROM PI ===")

url = "http://whoismrsentry.local:11434/api/tags"
print(f"Checking {url}...")
try:
    r = requests.get(url, timeout=5)
    print("Status:", r.status_code)
    models = [m['name'] for m in r.json().get('models', [])]
    print("Available models:", models)
except Exception as e:
    print("Failed to reach Ollama on whoismrsentry.local:", e)

print("\\nTesting generate on qwen3.5:9b or first available model...")
try:
    payload = {
        "model": "qwen3.5:9b",
        "prompt": "Say hello in one word",
        "stream": False
    }
    started = time.time()
    r = requests.post("http://whoismrsentry.local:11434/api/generate", json=payload, timeout=30)
    print(f"Generated in {time.time()-started:.2f}s:")
    print(r.json().get('response'))
except Exception as e:
    print("Generate failed:", e)

"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > ~/SentryBOT/test_ollama_pi.py\n" + test_code + "\nEOF\n")
stdout.read()

print("Running test_ollama_pi.py...")
stdin, stdout, stderr = ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python test_ollama_pi.py", timeout=45)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print("STDOUT:\n", out)
if err: print("STDERR:\n", err)

ssh.close()
