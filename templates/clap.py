"""
clap_launcher.py
-----------------
Ye script hamesha background mein chalta rehta hai aur microphone se
awaaz sunta rehta hai. Jab 2 taaliyan (double clap) thodi der ke
andar sune, to Zoya ka Flask server (joya2.py) naye terminal mein
chalu kar deta hai aur Chrome mein uska page khol deta hai.

Pehli baar use karne se pehle ye install karo:
    pip install sounddevice numpy

Phir isko chalu karo:
    python clap_launcher.py

Hamesha chalte rehne ke liye, isko Windows Startup folder mein daal do
(neeche instructions hain is file ke end mein).
"""

import subprocess
import time
import webbrowser
import os
import numpy as np
import sounddevice as sd

# ====================== CONFIG - apni zaroorat ke hisaab se badal sakte ho ======================
PROJECT_DIR = r"C:\Users\Dell\Desktop\python"   # joya2.py jahan hai
PYTHON_FILE = "joya2.py"
ZOYA_URL = "http://127.0.0.1:5000"

CLAP_LOUDNESS_THRESHOLD = 0.35   # kitni tez awaaz ko "clap" maanein (0.0 se 1.0)
MAX_GAP_BETWEEN_CLAPS = 1.0      # 2 taaliyon ke beech max kitna time gap (seconds)
COOLDOWN_AFTER_LAUNCH = 15.0     # launch ke baad kitni der tak dobara trigger na ho

SAMPLE_RATE = 44100
BLOCK_SIZE = 1024

# ====================== STATE ======================
last_clap_time = 0.0
last_launch_time = 0.0
zoya_already_running = False


def is_zoya_already_running():
    """Check karta hai ki joya2.py pehle se chal to nahi raha"""
    try:
        import psutil
        for proc in psutil.process_iter(['cmdline']):
            cmdline = proc.info.get('cmdline') or []
            if any(PYTHON_FILE in str(arg) for arg in cmdline):
                return True
    except Exception:
        pass
    return False


def launch_zoya():
    """Naya terminal kholta hai, joya2.py chalata hai, phir Chrome kholta hai"""
    global zoya_already_running

    print("👏 Double clap detected! Zoya launch ho rahi hai...")

    if is_zoya_already_running():
        print("ℹ️  Zoya pehle se chal rahi hai, sirf browser khol raha hoon.")
        webbrowser.open(ZOYA_URL)
        return

    try:
        # Naya CMD window khol kar usme joya2.py chalao
        subprocess.Popen(
            f'start cmd /k "cd /d {PROJECT_DIR} && python {PYTHON_FILE}"',
            shell=True
        )
        print("✅ Terminal khula, joya2.py chalu ho raha hai...")
    except Exception as e:
        print(f"[Launch Error] {e}")
        return

    # Server ko start hone ke liye thoda time do, phir browser kholo
    time.sleep(4)
    webbrowser.open(ZOYA_URL)
    print("✅ Chrome mein Zoya khol di gayi hai.")


def audio_callback(indata, frames, time_info, status):
    global last_clap_time, last_launch_time

    volume = float(np.max(np.abs(indata)))

    now = time.time()

    # Launch ke baad kuch der tak naye claps ignore karo (echo/background noise se bachne ke liye)
    if now - last_launch_time < COOLDOWN_AFTER_LAUNCH:
        return

    if volume > CLAP_LOUDNESS_THRESHOLD:
        if now - last_clap_time <= MAX_GAP_BETWEEN_CLAPS and last_clap_time != 0:
            # Doosri clap mil gayi, pehli ke time ke andar -> double clap confirm
            last_launch_time = now
            last_clap_time = 0
            launch_zoya()
        else:
            # Pehli clap record karo, doosri ka wait karo
            last_clap_time = now


def main():
    print("=" * 50)
    print("  Zoya Clap Launcher - Active")
    print("  Do taaliyan bajao (1 second ke andar) Zoya launch karne ke liye")
    print("  Band karne ke liye Ctrl+C dabao")
    print("=" * 50)

    with sd.InputStream(channels=1, samplerate=SAMPLE_RATE,
                         blocksize=BLOCK_SIZE, callback=audio_callback):
        while True:
            time.sleep(0.1)


if __name__ == "__main__":
    main()


# ====================== WINDOWS STARTUP PE CHALANE KE LIYE ======================
# 1. Ye file save karo: C:\Users\Dell\Desktop\python\clap_launcher.py
# 2. Win + R dabao, likho: shell:startup, Enter dabao (ek folder khulega)
# 3. Us folder mein ek naya text file banao naam: start_clap_listener.bat
# 4. Usme ye line likho (apna path check kar lena):
#        pythonw C:\Users\Dell\Desktop\python\clap_launcher.py
# 5. Save karo. Ab laptop restart/login hone par ye script khud chalu ho jayega,
#    bina kisi terminal window dikhaye background mein (pythonw ka matlab silent run).