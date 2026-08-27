import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

test_script = """
import sys
from modules.voice.speak.services.lang_detect import detect_text_language, resolve_speak_language
from modules.voice.speak.services.tts import TextToSpeech
from modules.voice.speak.config_loader import load_config

print("Test 1: 'Hello! I am SentryBOT, nice to meet you.' ->", detect_text_language("Hello! I am SentryBOT, nice to meet you."))
print("Test 2: 'Merhaba! Ben SentryBOT, nasılsın bugün?' ->", detect_text_language("Merhaba! Ben SentryBOT, nasılsın bugün?"))
print("Test 3: 'Please introduce yourself' ->", detect_text_language("Please introduce yourself"))
print("Test 4: 'Bana kendini tanıt' ->", detect_text_language("Bana kendini tanıt"))

cfg = load_config()
tts = TextToSpeech(cfg)
print("TTS Health:", tts.health())

pcm_en = tts.synthesize("Hello! I am SentryBOT, your companion robot.", overrides={"language": "en"})
print("Synthesized English PCM sample count:", len(pcm_en.data), "samplerate:", pcm_en.samplerate)

pcm_tr = tts.synthesize("Merhaba! Ben SentryBOT, nasılsın?", overrides={"language": "tr"})
print("Synthesized Turkish PCM sample count:", len(pcm_tr.data), "samplerate:", pcm_tr.samplerate)
"""

sftp = ssh.open_sftp()
with sftp.file("/home/sentrybot/SentryBOT/test_tts_lang_live.py", "w") as f:
    f.write(test_script)
sftp.close()

out, err = run("source /home/sentrybot/SentryBOT/.venv/bin/activate && cd /home/sentrybot/SentryBOT && python3 test_tts_lang_live.py")
print("OUTPUT:\n", out)
print("ERROR:\n", err)

ssh.close()
