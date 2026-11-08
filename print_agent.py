"""प्रिंट एजेंट - दुकान के लैपटॉप पर चलता है। हर 2 सेकंड में पूछता है: कोई पेड जॉब है?
MODE = "simulate"  -> सिर्फ स्क्रीन पर दिखाता है (प्रिंटर की ज़रूरत नहीं)
MODE = "print"     -> असली/वर्चुअल प्रिंटर पर भेजता है (Windows)
"""
import json, os, time, urllib.request

SERVER = "http://localhost:5000"
MODE = "simulate"
PRINTER = "Microsoft Print to PDF"   # असली प्रिंटर लगे तो यहाँ उसका नाम
UPLOADS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")

def call(path, method="GET"):
    req = urllib.request.Request(SERVER + path, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def do_print(job):
    path = os.path.join(UPLOADS, job["session"], job["file"])
    kind = "कलर" if job["color"] else "ब्लैक-वाइट"
    if MODE == "simulate":
        print(f"[प्रिंट] {job['name']} | {job['pages']} पेज x {job['copies']} कॉपी | {kind} | ₹{job['amount']}")
        return
    # Windows: हर कॉपी के लिए एक बार प्रिंट कमांड (os.startfile का "printto" क्रिया)
    for _ in range(job["copies"]):
        os.startfile(path, "printto", f'"{PRINTER}"', 0)
        time.sleep(1)

print("प्रिंट एजेंट चालू है... (बंद करने के लिए Ctrl+C)")
while True:
    try:
        job = call("/api/agent/next")
        if job:
            do_print(job)
            call(f"/api/agent/done/{job['id']}", "POST")
    except Exception as e:
        print("सर्वर से जुड़ नहीं पा रहा:", e)
    time.sleep(2)