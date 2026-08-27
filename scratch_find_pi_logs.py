import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

out, _ = run("find /home/sentrybot -name '*.log' -mmin -60 2>/dev/null")
print("Recent log files in /home/sentrybot:")
print(out)

out2, _ = run("find /tmp -name '*.log' -mmin -60 2>/dev/null")
print("Recent log files in /tmp:")
print(out2)

out3, _ = run("ls -la /home/sentrybot/SentryBOT/data/ 2>/dev/null")
print("SentryBOT/data contents:")
print(out3)

out4, _ = run("find /home/sentrybot/SentryBOT -name 'run_*' 2>/dev/null")
print("run_* dirs:")
print(out4)

ssh.close()
