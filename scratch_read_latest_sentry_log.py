import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

print("=== SENTRY.LOG (LATEST 200 LINES) ===")
out, _ = run("tail -n 200 /home/sentrybot/SentryBOT/logs/sentry.log")
print(out)

print("\n=== RUN_01-28-47/sentry.log ===")
out2, _ = run("tail -n 200 /home/sentrybot/SentryBOT/logs/runs/run_2026-08-28_01-28-47/sentry.log")
print(out2)

ssh.close()
