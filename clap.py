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
import urllib.request
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
previous_block_volume = 0.0
QUIET_THRESHOLD = 0.08  # isse kam volume ko "shaant" maana jaata hai


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


def wait_for_server(url, timeout_seconds=30):
    """Server ready hone tak har 0.5 second check karta hai, max timeout_seconds tak"""
    start = time.time()
    while time.time() - start < timeout_seconds:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True  # server ne jawab de diya, ready hai
        except Exception:
            time.sleep(0.5)
    return False  # itne time mein bhi ready nahi hua


def launch_zoya():
    """Naya terminal kholta hai, joya2.py chalata hai, phir Chrome kholta hai"""
    global zoya_already_running

    print("👏 Double clap detected! Zoya launch ho rahi hai...")

    if is_zoya_already_running():
        # Zoya pehle se chal rahi hai - naya tab NAHI kholte, warna 2 tabs
        # ban jaate hain jo ek saath microphone use karne ki koshish karte
        # hain aur command sunna band kar dete hain. Bas yahi batana kaafi hai.
        print("ℹ️  Zoya pehle se chal rahi hai aur tab pehle se khula hai - kuch nahi karna.")
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

    # Fixed wait ki jagah - server ready hone tak poll karo, phir hi browser kholo
    print("⏳ Server ready hone ka wait kar rahe hain...")
    if wait_for_server(ZOYA_URL, timeout_seconds=30):
        webbrowser.open(ZOYA_URL)
        print("✅ Chrome mein Zoya khol di gayi hai.")
    else:
        print("⚠️  30 second mein bhi server ready nahi hua. Terminal check karo kya error hai.")
        webbrowser.open(ZOYA_URL)  # phir bhi try karte hain, shayad user dekh le error


def audio_callback(indata, frames, time_info, status):
    global last_clap_time, last_launch_time, previous_block_volume

    volume = float(np.max(np.abs(indata)))
    was_quiet_before = previous_block_volume < QUIET_THRESHOLD

    now = time.time()

    # Launch ke baad kuch der tak naye claps ignore karo (echo/background noise se bachne ke liye)
    if now - last_launch_time < COOLDOWN_AFTER_LAUNCH:
        previous_block_volume = volume
        return

    # Sirf tab clap maano jab achanak tez awaaz aaye AUR usse theek pehle
    # shaant ho (taali aisi hi hoti hai - ek chhota sharp spike). Lagatar
    # bolna (jaise "Hey Zoya") is check mein fail ho jaata hai kyunki
    # usse pehle bhi awaaz chal rahi hoti hai, shaant nahi hoti.
    if volume > CLAP_LOUDNESS_THRESHOLD and was_quiet_before:
        if now - last_clap_time <= MAX_GAP_BETWEEN_CLAPS and last_clap_time != 0:
            last_launch_time = now
            last_clap_time = 0
            launch_zoya()
        else:
            last_clap_time = now

    previous_block_volume = volume


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