import sys
import paramiko
import os

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

out, _ = run("ls -td /home/sentrybot/SentryBOT/logs/run_* 2>/dev/null | head -n 5")
print("Latest run dirs in SentryBOT/logs:")
print(out)

dirs = [d.strip() for d in out.strip().splitlines() if d.strip()]
if not dirs:
    out2, _ = run("ls -td ~/.sentrybot/logs/run_* 2>/dev/null | head -n 5")
    print("Latest run dirs in ~/.sentrybot/logs:")
    print(out2)
    dirs = [d.strip() for d in out2.strip().splitlines() if d.strip()]

if dirs:
    latest = dirs[0]
    print(f"\nFetching logs from: {latest}")
    for log_name in ["sentry.log", "errors.log", "warnings.log", "tui.log"]:
        content, _ = run(f"cat {latest}/{log_name} 2>/dev/null")
        if content:
            local_path = os.path.join(r"C:\Users\emohi\Desktop\Project SentryBOT V5\scratch_pi_latest", log_name)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Saved {log_name} ({len(content.splitlines())} lines)")

ssh.close()
