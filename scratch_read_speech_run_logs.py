import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

print("=== ALL SPEECH / STT / TTS / LLM LINES FROM RUN_01-28-47 ===")
out, _ = run("grep -i -E 'speech|stt|tts|heard|winner|recogni|piper|glados|lang|say|reply|ollama' /home/sentrybot/SentryBOT/logs/runs/run_2026-08-28_01-28-47/sentry.log")
print(out)

print("\n=== ERRORS / WARNINGS FROM RUN_01-28-47 ===")
out2, _ = run("cat /home/sentrybot/SentryBOT/logs/runs/run_2026-08-28_01-28-47/errors.log 2>/dev/null")
print("ERRORS:\n", out2)

out3, _ = run("cat /home/sentrybot/SentryBOT/logs/runs/run_2026-08-28_01-28-47/warnings.log 2>/dev/null")
print("WARNINGS:\n", out3)

ssh.close()
