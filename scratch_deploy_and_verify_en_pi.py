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

print("1. Pulling git updates on Pi...")
run("cd ~/SentryBOT && git pull origin main")

print("2. Killing any lingering processes on Pi...")
run("pkill -9 -f 'python' || true")

print("3. Starting SentryBOT in background...")
ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python -m modules.gateway.xGatewayService > ~/gateway_test2.log 2>&1 &")

time.sleep(5.0)

print("\n4. Testing English input 'please introduce yourself'...")
run("curl -s -X POST http://127.0.0.1:8080/autonomy/speech -H 'Content-Type: application/json' -d '{\"text\": \"please introduce yourself\", \"language\": \"en\", \"final\": true}'")

print("Waiting 12s for LLM generation and GLaDOS TTS playback...")
time.sleep(12.0)

print("\n5. Checking gateway log for responses and errors:")
run("cat ~/gateway_test2.log | tail -n 80")

print("\n6. Cleaning up test process...")
run("pkill -9 -f 'modules.gateway.xGatewayService' || true")

ssh.close()
