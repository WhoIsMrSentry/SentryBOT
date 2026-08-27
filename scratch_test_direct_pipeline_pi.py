import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=40):
    print(f"=== {cmd} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out: print("STDOUT:\n", out)
    if err: print("STDERR:\n", err)

print("1. Pulling git updates on Pi...")
run("cd ~/SentryBOT && git pull origin main")

print("2. Killing any lingering processes on Pi...")
run("pkill -9 -f 'sentrybot.py' || true")
run("pkill -9 -f 'run_robot.py' || true")
run("pkill -9 -f 'Picamera2' || true")
run("pkill -9 -f 'python' || true")

print("3. Testing direct fast Autonomy + Ollama + TTS pipeline on Pi...")
run("cd ~/SentryBOT && source venv/bin/activate && python test_autonomy_speech_pi.py", timeout=60)

ssh.close()
