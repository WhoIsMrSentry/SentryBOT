import sys
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sentrybot-pi.local", username="sentrybot", password="sentrybot", timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    return stdout.read().decode('utf-8', errors='replace'), stderr.read().decode('utf-8', errors='replace')

print("=== PULLING LATEST MAIN ON PI ===")
out, err = run("cd /home/sentrybot/SentryBOT && git fetch origin main && git reset --hard origin/main")
print(out)
print(err)

print("=== TESTING TTS AND LANGUAGE DETECTION ON PI ===")
test_code = """
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
print("Synthesized English with voice:", getattr(tts.backend, 'default_voice', 'piper'), "PCM shape/len:", len(pcm_en.data))

pcm_tr = tts.synthesize("Merhaba! Ben SentryBOT, nasılsın?", overrides={"language": "tr"})
print("Synthesized Turkish with voice:", getattr(tts.backend, 'default_voice', 'piper'), "PCM shape/len:", len(pcm_tr.data))
"""

cmd = f"""source /home/sentrybot/SentryBOT/.venv/bin/activate && python3 -c {repr(test_code)}"""
out_test, err_test = run(cmd, timeout=30)
print(out_test)
print(err_test)

ssh.close()
