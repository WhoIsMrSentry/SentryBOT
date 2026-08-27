import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

test_code = """
import sys
import os
import time
import requests

sys.path.insert(0, "/home/sentrybot/SentryBOT")

from modules.voice.speak.xSpeakService import SpeakService
from modules.autonomy.xAutonomyService import xAutonomyService
from modules.common.config_loader import load_agent_config

print("=== TESTING AUTONOMY + SPEAK IN-PROCESS ON PI ===")

cfg = load_agent_config()
speak_svc = SpeakService()
autonomy_svc = xAutonomyService()

# Test vocal brain path directly
print("\\n1. Triggering speech on Autonomy Brain: 'Lütfen kendini tanıt' (tr)...")
autonomy_svc.brain.on_speech_final("Lütfen kendini tanıt", "tr")

time.sleep(6.0)

print("\\n2. Triggering English speech on Autonomy Brain: 'Hello, what is your mission?' (en)...")
autonomy_svc.brain.on_speech_final("Hello, what is your mission?", "en")

time.sleep(6.0)
print("=== DONE ===")
"""

stdin, stdout, stderr = ssh.exec_command("cat << 'EOF' > ~/SentryBOT/test_autonomy_speech_pi.py\n" + test_code + "\nEOF\n")
stdout.read()

print("Running test_autonomy_speech_pi.py...")
stdin, stdout, stderr = ssh.exec_command("cd ~/SentryBOT && source venv/bin/activate && python test_autonomy_speech_pi.py", timeout=45)
out = stdout.read().decode('utf-8', errors='replace')
err = stderr.read().decode('utf-8', errors='replace')
print("STDOUT:\n", out)
if err: print("STDERR:\n", err)

ssh.close()
