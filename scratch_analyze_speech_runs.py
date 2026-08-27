import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

print("=== SPEECH EVENTS IN run_2026-08-28_01-20-09 ===")
out, _ = run("grep -i -E 'speech|stt|tts|heard|winner|recogni|glados|dfki|piper|sentrybot speak|sentrybot reply' /home/sentrybot/SentryBOT/logs/runs/run_2026-08-28_01-20-09/sentry.log")
print(out)

print("\n=== SPEECH EVENTS IN run_2026-08-28_01-25-40 ===")
out2, _ = run("grep -i -E 'speech|stt|tts|heard|winner|recogni|glados|dfki|piper|sentrybot speak|sentrybot reply' /home/sentrybot/SentryBOT/logs/runs/run_2026-08-28_01-25-40/sentry.log")
print(out2)

ssh.close()
