import os
import subprocess
import webbrowser
import psutil
import datetime
import shutil
from flask import Flask, render_template, request, jsonify
import google.generativeai as genai

try:
    import pywhatkit
    WHATSAPP_AVAILABLE = True
except ImportError:
    WHATSAPP_AVAILABLE = False
    print("⚠️  pywhatkit install nahi hai. WhatsApp message feature kaam nahi karega.")
    print("    Install karne ke liye: pip install pywhatkit pyautogui")

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
def ask_gemini_with_fallback(prompt):
    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite"
    ]

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[Model Error] {model_name}: {e}")
            continue

    return "सोहेल बॉस, फिलहाल किसी भी एआई मॉडल से कनेक्ट नहीं हो पा रहा है। कृपया बाद में कोशिश करें।"


# ====================== SELF-CODE-WRITING FEATURE ======================
SELF_CODE_TRIGGERS = [
    "apna code", "अपना कोड", "अपने कोड", "code mein add", "कोड में ऐड",
    "फीचर ऐड करो", "feature add karo", "khud se code", "खुद से कोड",
    "अपने अंदर", "code likho", "कोड लिखो"
]


def is_self_code_request(msg_lower, msg_original):
    return any(trigger in msg_lower or trigger in msg_original for trigger in SELF_CODE_TRIGGERS)


def generate_updated_code(current_code, feature_description):
    """Gemini se poori updated Python file maangta hai jisme naya feature ho"""
    models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

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

    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                code = response.text.strip()
                # Agar Gemini ne markdown fences lagayi hon to hata do
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

    # Safety check: naya code valid Python hai ya nahi, pehle check karo
    try:
        compile(new_code, THIS_FILE, "exec")
    except SyntaxError as e:
        print(f"[Self-Code Syntax Error] {e}")
        return "सोहेल बॉस, AI ने जो कोड बनाया वो सही से काम नहीं करेगा (syntax error)। कृपया feature को अलग तरीके से समझाकर दोबारा कोशिश करें।"

    # Backup current file pehle
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"joya2_backup_{timestamp}.py")
        shutil.copy2(THIS_FILE, backup_path)
    except Exception as e:
        print(f"[Backup Error] {e}")
        return f"सोहेल बॉस, backup बनाने में दिक्कत आई, safety के लिए feature add नहीं किया: {e}"

    # Ab naya code save karo
    try:
        with open(THIS_FILE, "w", encoding="utf-8") as f:
            f.write(new_code)
    except Exception as e:
        return f"सोहेल बॉस, नया कोड save करने में दिक्कत आई: {e}"

    return "जी सोहेल बॉस, आपका फीचर कोड में जोड़ दिया है। सर्वर खुद रीस्टार्ट हो रहा है, कुछ सेकंड रुकिए फिर दोबारा कोशिश कीजिए।"


# ====================== WHATSAPP ======================
def send_whatsapp_message(contact_name, message_text):
    if not WHATSAPP_AVAILABLE:
        return "सोहेल बॉस, WhatsApp feature abhi install nahi hai। Terminal mein 'pip install pywhatkit pyautogui' chalayein।"

    number = CONTACTS.get(contact_name, "")
    if not number or "XXXXXXXXXX" in number:
        return f"सोहेल बॉस, पहले joya2.py mein '{contact_name}' का सही नंबर CONTACTS लिस्ट में डालें।"

    try:
        pywhatkit.sendwhatmsg_instantly(
            phone_no=number,
            message=message_text,
            wait_time=22,
            tab_close=True
        )
        # Extra safety: agar auto-send miss ho jaye to khud Enter dabao
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
    # Contact ka naam jahan mila, uske baad wala hissa hi asli message hai
    idx = msg.find(matched_text)
    if idx != -1:
        remainder = msg[idx + len(matched_text):].strip()
    else:
        remainder = msg

    # Shuru mein "को" jaisa connector word hata do
    for connector in ["को", "ko"]:
        if remainder.startswith(connector):
            remainder = remainder[len(connector):].strip()

    # Pattern 1: "...कि <message>"
    if "कि" in remainder:
        content = remainder.split("कि", 1)[1].strip()
    # Pattern 2: "<message> का मैसेज भेजो/करो"
    elif "का मैसेज" in remainder:
        content = remainder.split("का मैसेज")[0].strip()
    elif "ka message" in remainder.lower():
        idx2 = remainder.lower().find("ka message")
        content = remainder[:idx2].strip()
    else:
        content = remainder

    # Trailing filler hata do
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


# ====================== COMMAND PROCESSOR ======================
def process_command(msg: str) -> str:
    msg_lower = msg.lower().strip()

    # ---------- 0. SELF-CODE-WRITING (sabse pehle check hota hai) ----------
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
    elif "youtube" in msg_lower:
        query = msg_lower
        for remove in ["youtube", "par", "search", "खोलो", "खोल दो", "पर", "सर्च"]:
            query = query.replace(remove, "")
        query = query.strip()
        if not query:
            query = "trending"
        webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
        return f"जी सोहेल बॉस, यूट्यूब पर '{query}' सर्च कर रहा हूँ।"

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
        username = os.getenv("USERNAME", "")
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            rf"C:\Users\{username}\AppData\Local\Google\Chrome\Application\chrome.exe"
        ]
        chrome_path = find_executable(chrome_paths)
        if chrome_path:
            try:
                subprocess.Popen([chrome_path])
            except Exception:
                pass
        else:
            webbrowser.open("https://www.google.com")
        return "जी सोहेल बॉस, गूगल क्रोम खोल दिया है।"

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


@app.route('/api/chat', methods=['POST'])
def chat_api():
    try:
        data = request.get_json(silent=True) or {}
        user_msg = data.get('message', '').strip()

        if not user_msg:
            return jsonify({"response": "सोहेल बॉस, कृपया कुछ बोलें या लिखें।"})

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
    app.run(debug=False, use_reloader=True, host='127.0.0.1', port=5000)