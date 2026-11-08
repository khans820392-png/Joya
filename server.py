"""कॉपी शॉप सर्वर - स्टेप 1: अपलोड, फाइल लिस्ट, कीमत, नकली पेमेंट, प्रिंट जॉब।
चलाने के लिए:  pip install flask  और फिर  python server.py
"""
import json, os, time, uuid
from flask import Flask, jsonify, request, send_from_directory, abort

BASE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(BASE, "uploads")
JOBS_FILE = os.path.join(BASE, "jobs.json")
os.makedirs(UPLOADS, exist_ok=True)

# दुकानदार यहाँ रेट बदल सकता है (रुपये प्रति पेज)
PRICE_BW, PRICE_COLOR = 2, 10
ALLOWED = {"pdf", "jpg", "jpeg", "png"}

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB

def load_jobs():
    if not os.path.exists(JOBS_FILE):
        return {}
    with open(JOBS_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_jobs(jobs):
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)

def page_count(path):
    """PDF के पेज गिनता है (pypdf हो तो), वरना 1। फोटो = 1 पेज।"""
    if path.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return len(PdfReader(path).pages)
        except Exception:
            return 1
    return 1

@app.get("/")
def home():
    return send_from_directory("static", "index.html")

@app.get("/api/prices")
def prices():
    return jsonify(bw=PRICE_BW, color=PRICE_COLOR)

@app.post("/api/upload")
def upload():
    session = request.form.get("session", "")
    if not session.isalnum():
        abort(400)
    folder = os.path.join(UPLOADS, session)
    os.makedirs(folder, exist_ok=True)
    saved = []
    for f in request.files.getlist("files"):
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED:
            continue
        fid = uuid.uuid4().hex[:10]
        name = f"{fid}.{ext}"
        path = os.path.join(folder, name)
        f.save(path)
        saved.append({"id": name, "name": f.filename, "pages": page_count(path)})
    return jsonify(saved)

@app.get("/api/files/<session>/<fid>")
def get_file(session, fid):
    return send_from_directory(os.path.join(UPLOADS, session), fid)

@app.post("/api/order")
def order():
    d = request.get_json()
    session, fid = d["session"], d["file"]
    path = os.path.join(UPLOADS, session, fid)
    if not session.isalnum() or not os.path.exists(path):
        abort(400)
    copies = max(1, min(int(d.get("copies", 1)), 100))
    color = bool(d.get("color"))
    pages = page_count(path)
    # कीमत हमेशा सर्वर पर निकलती है, फोन पर नहीं
    amount = pages * copies * (PRICE_COLOR if color else PRICE_BW)
    jobs = load_jobs()
    oid = uuid.uuid4().hex[:8]
    jobs[oid] = dict(id=oid, session=session, file=fid, name=d.get("name", fid),
                     copies=copies, color=color, pages=pages, amount=amount,
                     status="unpaid", created=time.time())
    save_jobs(jobs)
    return jsonify(jobs[oid])

@app.post("/api/pay/mock/<oid>")
def pay_mock(oid):
    """टेस्ट के लिए नकली पेमेंट। असली में यहाँ Razorpay webhook आएगा।"""
    jobs = load_jobs()
    if oid not in jobs:
        abort(404)
    jobs[oid]["status"] = "paid"
    save_jobs(jobs)
    return jsonify(jobs[oid])

@app.get("/api/job/<oid>")
def job(oid):
    jobs = load_jobs()
    if oid not in jobs:
        abort(404)
    return jsonify(jobs[oid])

# ---- प्रिंट एजेंट के लिए ----
@app.get("/api/agent/next")
def agent_next():
    for j in load_jobs().values():
        if j["status"] == "paid":
            return jsonify(j)
    return jsonify(None)

@app.post("/api/agent/done/<oid>")
def agent_done(oid):
    jobs = load_jobs()
    if oid not in jobs:
        abort(404)
    jobs[oid]["status"] = "printed"
    save_jobs(jobs)
    return jsonify(jobs[oid])

if __name__ == "__main__":
    # 0.0.0.0 ताकि फोन उसी वाईफाई से खोल सके: http://<लैपटॉप-IP>:5000
    app.run(host="0.0.0.0", port=5000, debug=True)