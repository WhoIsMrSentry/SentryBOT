import sys
import paramiko
import time

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    print(f"=== {cmd} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out: print("STDOUT:\n", out)
    if err: print("STDERR:\n", err)
    return out

print("1. Killing any previous processes...")
run("pkill -9 -f 'python' || true")

print("2. Starting SentryBOT Gateway in background...")
ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python -m modules.gateway.xGatewayService > ~/gateway_test3.log 2>&1 &")

print("Waiting for Gateway to become healthy...")
for i in range(25):
    time.sleep(1.0)
    out = run("curl -s http://127.0.0.1:8080/health || true", timeout=5)
    if '"ok":true' in out or '"ok": true' in out:
        print(f"Gateway is ready after {i+1}s!")
        break

print("\n3. Testing English Chat /ollama/chat directly...")
run("curl -s -X POST http://127.0.0.1:8080/ollama/chat -H 'Content-Type: application/json' -d '{\"query\": \"Introduce yourself in one English sentence.\"}'", timeout=40)

print("\n4. Testing English Speech via /autonomy/speech...")
run("curl -s -X POST http://127.0.0.1:8080/autonomy/speech -H 'Content-Type: application/json' -d '{\"text\": \"please introduce yourself\", \"language\": \"en\", \"final\": true}'", timeout=40)

print("Waiting 12s for LLM reply and GLaDOS Piper playback...")
time.sleep(12.0)

print("\n5. Checking gateway_test3.log for outputs:")
run("cat ~/gateway_test3.log | tail -n 60")

print("\n6. Clean up...")
run("pkill -9 -f 'modules.gateway.xGatewayService' || true")

ssh.close()
