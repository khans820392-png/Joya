import json
import os
import subprocess
import webbrowser
import psutil
import datetime
import shutil
import concurrent.futures
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai

# Used to put a hard time limit on Gemini calls, so a slow/stuck network
# request can never freeze the whole app (Flask runs single-threaded
# unless told otherwise - a hung call here used to block every command).
GEMINI_CALL_TIMEOUT_SECONDS = 20
_gemini_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def call_with_timeout(func, timeout=GEMINI_CALL_TIMEOUT_SECONDS):
    """Runs func() but gives up after `timeout` seconds instead of hanging forever."""
    future = _gemini_executor.submit(func)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"[Gemini Timeout] Call took longer than {timeout}s, giving up.")
        return None

try:
    import importlib.util
    WHATSAPP_AVAILABLE = importlib.util.find_spec("pywhatkit") is not None
    if not WHATSAPP_AVAILABLE:
        print("⚠️  pywhatkit install nahi hai. WhatsApp message feature kaam nahi karega.")
        print("    Install karne ke liye: pip install pywhatkit pyautogui")
except Exception:
    WHATSAPP_AVAILABLE = False
# Note: pywhatkit yahan import NAHI karte - isse internet check karta hai
# jo app start hote hi atka sakta hai agar connection slow/blocked ho.
# Isko sirf tab import karenge jab WhatsApp message actually bhejna ho
# (dekho send_whatsapp_message function neeche).

try:
    import screen_brightness_control as sbc
    BRIGHTNESS_AVAILABLE = True
except ImportError:
    BRIGHTNESS_AVAILABLE = False
    print("⚠️  screen_brightness_control install nahi hai. Brightness feature kaam nahi karega.")
    print("    Install karne ke liye: pip install screen-brightness-control")

# ====================== CONFIG ======================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("⚠️  WARNING: Google API Key set नहीं है!")
else:
    genai.configure(api_key=GOOGLE_API_KEY)

MODELS_TO_TRY = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash"
]

# ====================== CONTACTS ======================
CONTACTS = {
    "papa": "+919140056548",
    "krish kumar": "+918423174633",
    "arvind sir": "+918887684411",
}
# Hindi mein jo naam bologe, unhe upar wale English naam se jodta hai
CONTACT_ALIASES = {
    "पापा": "papa",
    "क्रिश कुमार": "krish kumar",
    "कृष कुमार": "krish kumar",
    "अरविंद सर": "arvind sir",
}


THIS_FILE = os.path.abspath(__file__)
THIS_DIR = os.path.dirname(THIS_FILE)
LOG_FILE = os.path.join(THIS_DIR, "chat_log.txt")
BACKUP_DIR = os.path.join(THIS_DIR, "backups")

app = Flask(__name__)


# ====================== LOGGING ======================
def log_conversation(user_msg, bot_reply):
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}]\n")
            f.write(f"Sohil Boss: {user_msg}\n")
            f.write(f"Zoya: {bot_reply}\n")
            f.write("-" * 50 + "\n")
    except Exception as e:
        print(f"[Log Error] {e}")


# ====================== AI FALLBACK (conversational replies) ======================
def analyze_image_with_gemini(image_base64, user_question=None):
    """Image ko Gemini ko bhejta hai aur uska Hindi mein description/jawab leta hai"""
    import base64
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception as e:
        return f"सोहेल बॉस, image sahi se nahi mili: {e}"

    question_part = user_question.strip() if user_question else ""
    prompt_text = (
        "तुम ज़ोया हो, सोहेल बॉस की पर्सनल एआई असिस्टेंट। "
        "इस image को dekho aur Hindi mein chhota, saaf jawab do। "
        + (f"User ne ये poocha hai: {question_part}" if question_part
           else "Batao is image mein kya hai.")
    )

    for model_name in MODELS_TO_TRY:
        try:
            def do_call():
                model = genai.GenerativeModel(model_name)
                return model.generate_content([
                    prompt_text,
                    {"mime_type": "image/jpeg", "data": image_bytes}
                ])

            response = call_with_timeout(do_call)
            if response is None:
                continue
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[Vision Error - {model_name}] {e}")
            continue

    return "सोहेल बॉस, image samajhne में दिक्कत आई। दोबारा try कीजिए।"


def ask_gemini_with_fallback(prompt):
    for model_name in MODELS_TO_TRY:
        try:
            def do_call():
                model = genai.GenerativeModel(model_name)
                return model.generate_content(
                    prompt,
                    generation_config={"max_output_tokens": 200}
                )

            response = call_with_timeout(do_call)
            if response is None:
                continue  # timed out, try next model

            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[Model Error] {model_name}: {e}")
            continue

    return "सोहेल बॉस, फिलहाल किसी भी एआई मॉडल से कनेक्ट नहीं हो पा रहा है। कृपया बाद में कोशिश करें।"


# ====================== STUDY MODE ======================
STUDY_TRIGGER_WORDS = ["padhao", "पढ़ाओ", "samjhao", "समझाओ", "sikhao", "सिखाओ", "padha do", "पढ़ा दो"]

# The already-open "waiting" browser tab polls /api/study_pending every
# second and navigates itself when this gets set - this avoids ever
# needing window.open() from a voice-triggered (non-click) context,
# which browsers block.
PENDING_STUDY_TOPIC = {"topic": None}

# Same idea as PENDING_STUDY_TOPIC, but for opening the 3D map/dashboard -
# the already-open "map waiting" tab polls this and navigates itself.
PENDING_MAP_OPEN = {"open": False}
MAP_TRIGGER_WORDS = ["3d map", "थ्री डी मैप", "india map", "इंडिया मैप",
                      "map kholo", "मैप खोलो", "map dikhao", "मैप दिखाओ", "flood map"]


def is_map_request(message):
    msg_lower = message.lower()
    return any(word in msg_lower for word in MAP_TRIGGER_WORDS)


def is_study_request(message):
    msg_lower = message.lower()
    return any(word in msg_lower for word in STUDY_TRIGGER_WORDS)


def extract_study_topic(message):
    msg_lower = message.lower()
    for word in STUDY_TRIGGER_WORDS:
        if word in msg_lower:
            idx = msg_lower.find(word)
            topic = message[:idx].strip()
            if topic:
                return topic
    return message


def generate_study_content(topic):
    prompt = f"""Tum ek teacher ho. Topic hai: "{topic}"
Is topic ko student ko samjhao, 6 se 10 chhote paragraphs mein, har paragraph 1-2 lines ka.
Jo paragraphs exam ke liye zyada important hain unhe "important": true maaro, baaki "important": false.
STRICTLY sirf ek valid JSON array return karo, koi aur text nahi, koi markdown fences nahi:
[{{"text": "paragraph", "important": false}}]"""

    for model_name in MODELS_TO_TRY:
        try:
            def do_call():
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt)

            response = call_with_timeout(do_call)
            if response is None:
                continue  # timed out, try next model

            raw = response.text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[Study Content Error - {model_name}]", e)
            continue
    return None


# ====================== SELF-CODE-WRITING FEATURE ======================
# ====================== EMOTION MODE ======================
EMOTION_MODE = {"on": False}

EMOTION_ON_TRIGGERS = ["emotion mode on", "इमोशन मोड ऑन", "emotion on karo",
                       "इमोशन ऑन करो", "इमोशन एक्टिवेट", "emotion activate"]
EMOTION_OFF_TRIGGERS = ["emotion mode off", "इमोशन मोड ऑफ", "emotion off karo",
                        "इमोशन ऑफ करो", "इमोशन बंद"]


def is_emotion_toggle_request(msg_lower):
    if any(t in msg_lower for t in EMOTION_ON_TRIGGERS):
        return "on"
    if any(t in msg_lower for t in EMOTION_OFF_TRIGGERS):
        return "off"
    return None


SELF_CODE_TRIGGERS = [
    "apna code", "अपना कोड", "अपने कोड", "code mein add", "कोड में ऐड",
    "फीचर ऐड करो", "feature add karo", "khud se code", "खुद से कोड",
    "अपने अंदर", "code likho", "कोड लिखो"
]


def is_self_code_request(msg_lower, msg_original):
    return any(trigger in msg_lower or trigger in msg_original for trigger in SELF_CODE_TRIGGERS)


def generate_updated_code(current_code, feature_description):
    """Gemini se poori updated Python file maangta hai jisme naya feature ho"""
    prompt = f"""Tum ek Python Flask backend file ko edit kar rahe ho. Neeche poori current file di gayi hai.

User ye naya feature chahta hai: {feature_description}

Rules:
1. Poori updated Python file wapas do - sirf raw Python code, koi markdown fences (```), koi explanation nahi.
2. Current functionality bilkul preserve karo, sirf naya feature add karo.
3. process_command() function ke andar ek naya elif branch add karo jo iss feature ko handle kare, General AI response (sabse last elif) se PEHLE.
4. Agar kisi naye library ki zaroorat ho, usse try/except import ke saath top mein add karo (jaisa pywhatkit/screen_brightness_control ke liye kiya gaya hai), taaki library na hone par bhi app crash na ho.
5. Response hamesha Hindi mein ho jaise baaki responses hain.
6. Code 100% syntactically valid Python hona chahiye.

Current file:
{current_code}
"""

    for model_name in MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                code = response.text.strip()
                if code.startswith("```"):
                    lines = code.split("\n")
                    lines = lines[1:] if lines[0].startswith("```") else lines
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    code = "\n".join(lines)
                return code, None
        except Exception as e:
            print(f"[Self-Code Model Error] {model_name}: {e}")
            continue

    return None, "किसी भी AI मॉडल से कनेक्ट नहीं हो पाया।"


def handle_self_code_request(feature_description):
    """Naya feature khud code karke apni hi file mein save karta hai, backup ke saath"""
    try:
        with open(THIS_FILE, "r", encoding="utf-8") as f:
            current_code = f.read()
    except Exception as e:
        return f"सोहेल बॉस, अपना कोड पढ़ने में दिक्कत आई: {e}"

    new_code, error = generate_updated_code(current_code, feature_description)
    if error or not new_code:
        return f"सोहेल बॉस, फीचर कोड नहीं बना पाया: {error}"

    try:
        compile(new_code, THIS_FILE, "exec")
    except SyntaxError as e:
        print(f"[Self-Code Syntax Error] {e}")
        return "सोहेल बॉस, AI ने जो कोड बनाया वो सही से काम नहीं करेगा (syntax error)। कृपया feature को अलग तरीके से समझाकर दोबारा कोशिश करें।"

    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"joya2_backup_{timestamp}.py")
        shutil.copy2(THIS_FILE, backup_path)
    except Exception as e:
        print(f"[Backup Error] {e}")
        return f"सोहेल बॉस, backup बनाने में दिक्कत आई, safety के लिए feature add नहीं किया: {e}"

    try:
        with open(THIS_FILE, "w", encoding="utf-8") as f:
            f.write(new_code)
    except Exception as e:
        return f"सोहेल बॉस, नया कोड save करने में दिक्कत आई: {e}"

    return "जी सोहेल बॉस, आपका फीचर कोड में जोड़ दिया है। सर्वर खुद रीस्टार्ट हो रहा है, कुछ सेकंड रुकिए फिर दोबारा कोशिश कीजिए।"


# ====================== WHATSAPP ======================
def find_contact_in_message(msg_lower, msg_original):
    """Message mein CONTACTS ya CONTACT_ALIASES mein se koi naam dhoondta hai"""
    for name in CONTACTS.keys():
        if name in msg_lower:
            return name, name
    for hindi_name, english_name in CONTACT_ALIASES.items():
        if hindi_name in msg_original:
            return english_name, hindi_name
    return None, None


def send_whatsapp_message(contact_name, message_text):
    if not WHATSAPP_AVAILABLE:
        return "सोहेल बॉस, WhatsApp feature abhi install nahi hai। Terminal mein 'pip install pywhatkit pyautogui' chalayein।"

    number = CONTACTS.get(contact_name, "")
    if not number or "XXXXXXXXXX" in number:
        return f"सोहेल बॉस, पहले joya2.py mein '{contact_name}' का सही नंबर CONTACTS लिस्ट में डालें।"

    try:
        import pywhatkit  # lazy import - sirf yahan, jab actually bhejna ho
        pywhatkit.sendwhatmsg_instantly(
            phone_no=number,
            message=message_text,
            wait_time=22,
            tab_close=True
        )
        try:
            import pyautogui
            import time
            time.sleep(1)
            pyautogui.press("enter")
        except Exception:
            pass
        return f"जी सोहेल बॉस, {contact_name} को मैसेज भेज दिया है: '{message_text}'"
    except Exception as e:
        print(f"[WhatsApp Error] {e}")
        return "सोहेल बॉस, WhatsApp मैसेज भेजने में दिक्कत आई। WhatsApp Web पहले से login होना चाहिए।"


def extract_whatsapp_message(msg, matched_text):
    idx = msg.find(matched_text)
    if idx != -1:
        remainder = msg[idx + len(matched_text):].strip()
    else:
        remainder = msg

    for connector in ["को", "ko"]:
        if remainder.startswith(connector):
            remainder = remainder[len(connector):].strip()

    if "कि" in remainder:
        content = remainder.split("कि", 1)[1].strip()
    elif "का मैसेज" in remainder:
        content = remainder.split("का मैसेज")[0].strip()
    elif "ka message" in remainder.lower():
        idx2 = remainder.lower().find("ka message")
        content = remainder[:idx2].strip()
    else:
        content = remainder

    fillers = ["और सेंड कर देना", "सेंड कर देना", "सेंड कर दो", "send kar dena", "send kar do",
               "भेज देना", "भेज दो", "मैसेज भेजो", "मैसेज करो", "message bhejo", "message karo",
               "व्हाट्सएप पर", "whatsapp par", "व्हाट्सएप पे"]
    for f in fillers:
        content = content.replace(f, "").strip()

    return content if content else "नमस्ते"


def open_whatsapp_app():
    username = os.getenv("USERNAME", "")
    possible_paths = [
        rf"C:\Users\{username}\AppData\Local\WhatsApp\WhatsApp.exe",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen([path])
                return "जी सोहेल बॉस, WhatsApp खोल दिया है।"
            except Exception:
                pass
    webbrowser.open("https://web.whatsapp.com")
    return "जी सोहेल बॉस, WhatsApp Web खोल दिया है।"


# ====================== BRIGHTNESS ======================
def change_brightness(action, amount=20):
    if not BRIGHTNESS_AVAILABLE:
        return "सोहेल बॉस, brightness feature abhi install nahi hai। Terminal mein 'pip install screen-brightness-control' chalayein।"
    try:
        current = sbc.get_brightness()[0]
        if action == "up":
            new_level = min(100, current + amount)
        elif action == "down":
            new_level = max(0, current - amount)
        else:
            new_level = amount
        sbc.set_brightness(new_level)
        return f"जी सोहेल बॉस, ब्राइटनेस {new_level}% कर दी है।"
    except Exception as e:
        print(f"[Brightness Error] {e}")
        return "सोहेल बॉस, ब्राइटनेस बदलने में दिक्कत आई। यह feature सभी लैपटॉप/मॉनिटर पर काम नहीं करता।"


# ====================== APP PATHS ======================
def find_executable(possible_paths):
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


def get_vscode_path():
    username = os.getenv("USERNAME", "")
    possible_paths = [
        rf"C:\Users\{username}\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    ]
    return find_executable(possible_paths)


def get_chrome_path():
    username = os.getenv("USERNAME", "")
    possible_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        rf"C:\Users\{username}\AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    return find_executable(possible_paths)


def open_url_in_chrome(url):
    """Chrome mein ek specific URL kholta hai - seedha chrome.exe se (reliable),
    agar chrome.exe na mile tabhi default browser (webbrowser) try karta hai."""
    chrome_path = get_chrome_path()
    if chrome_path:
        try:
            subprocess.Popen([chrome_path, url])
            return True
        except Exception as e:
            print(f"[Chrome Launch Error] {e}")
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        print(f"[Browser Open Error] {e}")
        return False


# ====================== COMMAND PROCESSOR ======================
def process_command(msg: str) -> str:
    msg_lower = msg.lower().strip()

    # ---------- 0. SELF-CODE-WRITING (sabse pehle check hota hai) ----------
    # ---------- EMOTION MODE TOGGLE (sabse pehle check hota hai) ----------
    emotion_toggle = is_emotion_toggle_request(msg_lower)
    if emotion_toggle == "on":
        EMOTION_MODE["on"] = True
        return "जी सोहेल बॉस, अब मैं इमोशन मोड में बात करूँगी।"
    elif emotion_toggle == "off":
        EMOTION_MODE["on"] = False
        return "ठीक है सोहेल बॉस, इमोशन मोड बंद कर दिया।"

    if is_self_code_request(msg_lower, msg):
        return handle_self_code_request(msg)

    # ---------- 1. SHUTDOWN ----------
    shutdown_phrases = ["shutdown", "shut down", "sit down", "कंप्यूटर बंद", "pc band",
                         "pc बंद", "शटडाउन", "सिट डाउन", "सिस्टम बंद", "सिस्टम सिट डाउन"]
    pc_word_present = "पीसी" in msg or "pc" in msg_lower or "कंप्यूटर" in msg or "computer" in msg_lower or "सिस्टम" in msg
    band_word_present = "बंद" in msg or "band" in msg_lower or "shut" in msg_lower or "sit down" in msg_lower or "शटडाउन" in msg or "सिट डाउन" in msg

    if any(phrase in msg_lower for phrase in shutdown_phrases) or (pc_word_present and band_word_present):
        try:
            os.system("shutdown /s /t 5")
            return "जी सोहेल बॉस, 5 सेकंड में कंप्यूटर शट डाउन हो रहा है।"
        except Exception as e:
            return f"शटडाउन कमांड में समस्या: {e}"

    # ---------- 2. BATTERY ----------
    elif any(word in msg_lower for word in ["battery", "बैटरी", "kitni battery", "battery status"]):
        try:
            battery = psutil.sensors_battery()
            if battery:
                percent = battery.percent
                plugged = "चार्जिंग पर लगी है" if battery.power_plugged else "चार्जिंग पर नहीं है"
                return f"सोहेल बॉस, बैटरी अभी {percent}% है और यह {plugged}।"
            return "सोहेल बॉस, बैटरी की जानकारी नहीं मिल पा रही है।"
        except Exception:
            return "बैटरी चेक करने में एरर आ गया है।"

    # ---------- 3. BRIGHTNESS ----------
    elif "brightness" in msg_lower or "ब्राइटनेस" in msg:
        if any(w in msg_lower for w in ["tez", "badhao", "up", "बढ़ा", "तेज़", "तेज"]):
            return change_brightness("up")
        elif any(w in msg_lower for w in ["kam", "dheemi", "down", "कम", "धीमी", "धीमा"]):
            return change_brightness("down")
        else:
            return change_brightness("up")

    # ---------- 4. WHATSAPP - SEND MESSAGE TO A CONTACT ----------
    elif ("whatsapp" in msg_lower or "व्हाट्सएप" in msg) and \
         ("message" in msg_lower or "मैसेज" in msg or "भेज" in msg or "send" in msg_lower):
        contact_name, matched_text = find_contact_in_message(msg_lower, msg)
        if not contact_name:
            saved_names = ", ".join(CONTACTS.keys()) if CONTACTS else "कोई नहीं"
            return f"सोहेल बॉस, मुझे पता नहीं किसे मैसेज करना है। मेरे पास ये नाम सेव हैं: {saved_names}"
        content = extract_whatsapp_message(msg, matched_text)
        return send_whatsapp_message(contact_name, content)

    # ---------- 5. WHATSAPP - JUST OPEN THE APP ----------
    elif "whatsapp" in msg_lower or "व्हाट्सएप" in msg:
        return open_whatsapp_app()

    # ---------- 6. YOUTUBE SEARCH ----------
    elif "youtube" in msg_lower or "यूट्यूब" in msg:
        query = msg_lower
        for remove in ["youtube", "यूट्यूब", "par", "search", "खोलो", "खोल दो", "पर", "सर्च", "kholo"]:
            query = query.replace(remove, "")
        query = query.strip()

        if not query:
            # Koi specific search term nahi diya - seedha YouTube homepage kholo
            opened = open_url_in_chrome("https://www.youtube.com")
            if opened:
                return "जी सोहेल बॉस, YouTube Chrome में खोल दिया है।"
            return "सोहेल बॉस, YouTube खोलने में दिक्कत आई।"

        opened = open_url_in_chrome(f"https://www.youtube.com/results?search_query={query}")
        if opened:
            return f"जी सोहेल बॉस, यूट्यूब पर '{query}' सर्च कर रहा हूँ।"
        return "सोहेल बॉस, YouTube search खोलने में दिक्कत आई।"

    # ---------- 7. VS CODE ----------
    elif any(word in msg_lower for word in ["visual studio code", "vs code", "vscode", "विजुअल स्टूडियो", "वीएस कोड"]):
        vscode_path = get_vscode_path()
        if vscode_path:
            try:
                subprocess.Popen([vscode_path])
                return "जी सोहेल बॉस, VS Code खोल दिया है।"
            except Exception as e:
                return f"VS Code खोलने में समस्या: {e}"
        else:
            return "सोहेल बॉस, मुझे VS Code इस कंप्यूटर पर नहीं मिला।"

    # ---------- 8. CHROME / BROWSER ----------
    elif any(word in msg_lower for word in ["chrome", "browser", "क्रोम", "ब्राउज़र"]):
        # Pehle check karo - kya ye "Chrome pe X search karo" jaisi request hai?
        has_search_intent = any(w in msg_lower for w in ["search", "सर्च", "dhoondo", "ढूंढो", "khojo", "खोजो"])

        if has_search_intent:
            query = msg_lower
            for remove in ["chrome", "क्रोम", "browser", "ब्राउज़र", "par", "पर", "pe",
                            "search karo", "सर्च करो", "search kar do", "सर्च कर दो",
                            "dhoondo", "ढूंढो", "khojo", "खोजो", "search", "सर्च"]:
                query = query.replace(remove, "")
            query = query.strip()

            if query:
                opened = open_url_in_chrome(f"https://www.google.com/search?q={query}")
                if opened:
                    return f"जी सोहेल बॉस, Chrome पर '{query}' सर्च कर रहा हूँ।"
                return "सोहेल बॉस, Chrome search खोलने में दिक्कत आई।"
            # Agar "search karo" bola par kya search karna hai pata nahi chala
            opened = open_url_in_chrome("https://www.google.com")
            return "सोहेल बॉस, क्या search करना है ये समझ नहीं आया, Google खोल दिया है - type/bol kar bata dijiye।" if opened else "Chrome खोलने में दिक्कत आई।"

        # Sirf "Chrome kholo" - bina search ke
        opened = open_url_in_chrome("https://www.google.com")
        if opened:
            return "जी सोहेल बॉस, गूगल क्रोम खोल दिया है।"
        return "सोहेल बॉस, Chrome खोलने में दिक्कत आई।"

    # ---------- 9. NOTEPAD ----------
    elif any(word in msg_lower for word in ["notepad", "नोटपैड", "नोट पैड"]):
        try:
            subprocess.Popen("notepad.exe")
            return "जी सोहेल बॉस, नोटपैड खोल दिया है।"
        except Exception as e:
            print(f"[Notepad Error] {e}")
            return f"नोटपैड खोलने में समस्या आई: {e}"

    # ---------- 10. VOLUME UP ----------
    elif any(word in msg_lower for word in ["volume up", "आवाज़ तेज़", "tez", "badhao", "volume badhao", "आवाज तेज"]):
        try:
            import pyautogui
            for _ in range(5):
                pyautogui.press("volumeup")
            return "जी सोहेल बॉस, आवाज़ तेज़ कर दी है।"
        except Exception:
            return "वॉल्यूम बढ़ाने की कमांड पूरी नहीं हो पाई। pyautogui install करें।"

    # ---------- 11. VOLUME DOWN ----------
    elif any(word in msg_lower for word in ["volume down", "आवाज़ कम", "kam karo", "volume kam", "आवाज कम"]):
        try:
            import pyautogui
            for _ in range(5):
                pyautogui.press("volumedown")
            return "जी सोहेल बॉस, आवाज़ कम कर दी है।"
        except Exception:
            return "वॉल्यूम कम करने में दिक्कत आई है।"

    # ---------- 12. GENERAL AI RESPONSE ----------
    else:
        if EMOTION_MODE["on"]:
            # Emotion detection aur reply, DONO EK HI Gemini call mein -
            # isse extra API round-trip nahi lagta, speed same rehti hai.
            prompt = (
                f"तुम ज़ोया हो, सोहेल बॉस की पर्सनल एआई असिस्टेंट, और अभी तुम्हारा "
                f"'इमोशन मोड' ऑन है। पहले user का tone samjho (gussa/rude, khush/polite, ya normal), "
                f"फिर उसी भावना के हिसाब से reply do - agar woh rude bola hai to thodi naraazgi dikhao, "
                f"agar achha/dhanyawad bola hai to khushi dikhao, warna normal raho। "
                f"जवाब हमेशा छोटे, साफ़ और हिंदी में दो, aur tone ka explanation mat do bas usi tarah reply karo। "
                f"सवाल: {msg}"
            )
        else:
            prompt = (
                f"तुम ज़ोया हो, सोहेल बॉस की पर्सनल एआई असिस्टेंट। "
                f"जवाब हमेशा छोटे, साफ़ और हिंदी में दो। "
                f"सवाल: {msg}"
            )
        return ask_gemini_with_fallback(prompt)


# ====================== ROUTES ======================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/india-map2')
def india_map_page():
    return render_template('india_map2.html')


@app.route('/up-districts2')
def up_districts_page():
    return render_template('up_districts2.html')


@app.route('/hamirppur_demo2')
def flood_demo_page():
    return render_template('hamirppur_demo2.html')


@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')


@app.route('/study')
def study_page():
    return render_template('study_mode.html')


@app.route('/study_waiting')
def study_waiting_page():
    return render_template('study_waiting.html')


@app.route('/map_waiting')
def map_waiting_page():
    return render_template('map_waiting.html')


@app.route('/api/map_pending')
def api_map_pending():
    is_open = PENDING_MAP_OPEN["open"]
    PENDING_MAP_OPEN["open"] = False  # clear once read, so it fires only once
    return jsonify({"open": is_open})


@app.route('/api/study_pending')
def api_study_pending():
    topic = PENDING_STUDY_TOPIC["topic"]
    PENDING_STUDY_TOPIC["topic"] = None  # clear once read, so it fires only once
    return jsonify({"topic": topic})


@app.route('/api/study_content', methods=['POST'])
def api_study_content():
    data = request.get_json(silent=True) or {}
    topic = data.get('topic', '').strip()
    content = generate_study_content(topic) if topic else None
    return jsonify({"content": content or []})


@app.route('/api/vision', methods=['POST'])
def vision_api():
    try:
        data = request.get_json(silent=True) or {}
        image_base64 = data.get('image', '')
        question = data.get('question', '')

        if not image_base64:
            return jsonify({"response": "सोहेल बॉस, कोई image नहीं मिली।"})

        reply_text = analyze_image_with_gemini(image_base64, question)
        log_conversation(f"[Image] {question or 'Describe image'}", reply_text)
        return jsonify({"response": reply_text})
    except Exception as e:
        print(f"[Vision API Error] {e}")
        return jsonify({"response": "सोहेल बॉस, image process करने में दिक्कत आई।"}), 500


@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.get_json(silent=True) or {}
        user_msg = data.get('message', '').strip()

        if not user_msg:
            return jsonify({"response": "सोहेल बॉस, कृपया कुछ बोलें या लिखें।"})

        if is_study_request(user_msg):
            topic = extract_study_topic(user_msg)
            confirm_msg = f"जी सोहेल बॉस, '{topic}' पढ़ाते हैं — टैब मिलते ही खुल जाएगा।"
            PENDING_STUDY_TOPIC["topic"] = topic
            log_conversation(user_msg, confirm_msg)
            return jsonify({"response": confirm_msg, "action": "open_study", "topic": topic})

        if is_map_request(user_msg):
            confirm_msg = "जी सोहेल बॉस, 3D मैप खोल रहा हूँ — टैब मिलते ही खुल जाएगा।"
            PENDING_MAP_OPEN["open"] = True
            log_conversation(user_msg, confirm_msg)
            return jsonify({"response": confirm_msg, "action": "open_map"})

        reply_text = process_command(user_msg)
        log_conversation(user_msg, reply_text)
        return jsonify({"response": reply_text})

    except Exception as e:
        print(f"[Chat API Error] {e}")
        return jsonify({"response": "कुछ गड़बड़ हो गई है सोहेल बॉस। कृपया दोबारा कोशिश करें।"}), 500


# ====================== RUN ======================
if __name__ == '__main__':
    print("=" * 50)
    print("  Zoya AI Assistant - Improved Version")
    print("  Multi-Model Fallback Engine Active")
    print(f"  Conversation Log: {LOG_FILE}")
    print(f"  Backups folder: {BACKUP_DIR}")
    print("  Code badalne par server khud restart ho jayega (auto-reload ON)")
    print("  Running on http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=False, use_reloader=True, threaded=True, host='127.0.0.1', port=5000)