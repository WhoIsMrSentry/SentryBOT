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

print("1. Starting Gateway in background...")
run("pkill -9 -f 'python' || true")
ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python -m modules.gateway.xGatewayService > ~/gateway_live.log 2>&1 &")

time.sleep(6.0)

print("2. Direct chat endpoint test from Pi...")
run("curl -s -X POST http://127.0.0.1:8080/ollama/chat -H 'Content-Type: application/json' -d '{\"query\": \"Introduce yourself in English briefly\"}'")

print("\n3. Speech endpoint test from Pi...")
run("curl -s -X POST http://127.0.0.1:8080/autonomy/speech -H 'Content-Type: application/json' -d '{\"text\": \"please introduce yourself\", \"language\": \"en\", \"final\": true}'")

print("Waiting 15s for full pipeline generation & audio...")
time.sleep(15.0)

print("\n4. Checking gateway_live.log for full output and any errors:")
run("cat ~/gateway_live.log | tail -n 80")

print("\n5. Killing test server...")
run("pkill -9 -f 'modules.gateway.xGatewayService' || true")

ssh.close()
