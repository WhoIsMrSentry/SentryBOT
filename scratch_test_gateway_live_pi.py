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

print("2. Starting SentryBOT gateway in background...")
ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python -m modules.gateway.xGatewayService > ~/gateway_test.log 2>&1 &")

time.sleep(6.0)

print("3. Checking Gateway health...")
run("curl -s http://127.0.0.1:8080/health || true")
run("curl -s http://127.0.0.1:8080/speak/status || true")

print("\n4. Sending Turkish speech to Gateway /autonomy/speech...")
run("curl -s -X POST http://127.0.0.1:8080/autonomy/speech -H 'Content-Type: application/json' -d '{\"text\": \"Lütfen kendini tanıt\", \"language\": \"tr\", \"final\": true}'")

print("Waiting 10s for LLM reply and Piper TTS...")
time.sleep(10.0)

print("\n5. Sending English speech to Gateway /autonomy/speech...")
run("curl -s -X POST http://127.0.0.1:8080/autonomy/speech -H 'Content-Type: application/json' -d '{\"text\": \"Hello, introduce yourself briefly\", \"language\": \"en\", \"final\": true}'")

print("Waiting 10s for GLaDOS reply and Piper TTS...")
time.sleep(10.0)

print("\n6. Checking gateway_test.log:")
run("cat ~/gateway_test.log | tail -n 80")

print("\n7. Killing background test server...")
run("pkill -9 -f 'modules.gateway.xGatewayService' || true")

ssh.close()
