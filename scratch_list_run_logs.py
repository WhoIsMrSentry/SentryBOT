import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

out, _ = run("ls -lat /home/sentrybot/SentryBOT/logs/runs/")
print("Runs list:")
print(out)

print("\n=== LATEST RUNS AND THEIR SIZES ===")
out2, _ = run("ls -lat /home/sentrybot/SentryBOT/logs/runs/*/*.log")
print(out2)

ssh.close()
