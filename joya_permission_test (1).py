"""
Joya Permission Test (FREE / LOCAL ONLY)
----------------------------------------
This is a safe test companion. It does NOT make or receive real phone calls.
It simulates a request, asks Sohil Boss for approval, and opens Joya only
after the Allow button is clicked.

Keep your existing Joya Python file unchanged.
Requirements: pip install flask
Run: python joya_permission_test.py
Open: http://127.0.0.1:5001
"""

from flask import Flask, request, jsonify, render_template_string
import threading
import webbrowser
import time

app = Flask(__name__)

# Your existing Joya server is expected to run on port 5000.
JOYA_URL = "http://127.0.0.1:5000/"

_lock = threading.Lock()
_request_state = {
    "status": "locked",  # locked, pending, approved, denied
    "caller": "",
    "created_at": 0.0,
    "message": "Joya is locked. No request is waiting."
}

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Joya Permission Test</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 20px; color: #edf4ff; font-family: Arial, sans-serif;
    background: radial-gradient(circle at top, #18264a, #070b16 65%);
  }
  .panel {
    width: min(620px, 100%); padding: 26px; border: 1px solid #34466f;
    border-radius: 20px; background: rgba(12, 20, 40, .96);
    box-shadow: 0 18px 60px #0008;
  }
  h1 { margin: 0 0 8px; color: #72d8ff; }
  .sub { color: #afbdd8; line-height: 1.5; }
  .status {
    margin: 20px 0; padding: 16px; border-radius: 12px;
    background: #17233c; border: 1px solid #334766;
  }
  .state { font-weight: bold; letter-spacing: .08em; }
  label { display: block; margin: 18px 0 7px; color: #d5e3ff; }
  input {
    width: 100%; padding: 12px; border-radius: 9px;
    border: 1px solid #405579; background: #080f20; color: white;
  }
  .buttons { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
  button {
    flex: 1; min-width: 135px; border: 0; border-radius: 10px;
    padding: 12px 14px; font-weight: bold; cursor: pointer;
  }
  button:disabled { opacity: .4; cursor: not-allowed; }
  .simulate { background: #5bc9f5; color: #07101c; }
  .allow { background: #3ed39a; color: #071b13; }
  .deny { background: #ff7e89; color: #26070a; }
  .reset { background: #293854; color: #eaf1ff; }
  .note { font-size: 13px; color: #9eacc7; line-height: 1.5; margin-top: 20px; }
</style>
</head>
<body>
<main class="panel">
  <h1>JOYA · Permission Test</h1>
  <div class="sub">Free local test — no real phone calls are made.</div>

  <section class="status" aria-live="polite">
    <div class="state" id="state">LOCKED</div>
    <p id="message">Joya is locked. No request is waiting.</p>
    <div id="caller"></div>
  </section>

  <label for="number">Simulated caller's number</label>
  <input id="number" type="tel" placeholder="e.g. 98XXXXXXXX" maxlength="20">

  <div class="buttons">
    <button class="simulate" id="simulate" onclick="simulateRequest()">Simulate request</button>
    <button class="allow" id="allow" onclick="decide('allow')" disabled>Yes, open Joya</button>
    <button class="deny" id="deny" onclick="decide('deny')" disabled>No, keep locked</button>
    <button class="reset" onclick="resetState()">Reset</button>
  </div>

  <div class="note">
    This is only a local demonstration. The typed number is not verified against
    a SIM or caller ID. The real-call feature is not connected. Joya opens only
    after you press “Yes, open Joya”. If you do nothing, it stays locked.
  </div>
</main>
<script>
let previousStatus = "";
async function refresh() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    document.getElementById('state').textContent = d.status.toUpperCase();
    document.getElementById('message').textContent = d.message;
    document.getElementById('caller').textContent =
      d.caller ? ('Caller: ' + d.caller) : '';
    const pending = d.status === 'pending';
    document.getElementById('allow').disabled = !pending;
    document.getElementById('deny').disabled = !pending;
    document.getElementById('simulate').disabled = pending;
    if (d.status === 'pending' && previousStatus !== 'pending' &&
        'speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(
        'Sohil Boss, someone wants to open your Joya project. Do you allow it?'
      );
      utterance.lang = 'en-IN';
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    }
    previousStatus = d.status;
  } catch (e) {}
}
async function simulateRequest() {
  const caller = document.getElementById('number').value.trim();
  if (!caller) {
    alert('Test ke liye caller number type karo.');
    return;
  }
  const r = await fetch('/api/request', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({caller})
  });
  const d = await r.json();
  if (!r.ok) alert(d.message);
  await refresh();
}
async function decide(decision) {
  const r = await fetch('/api/decision', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({decision})
  });
  const d = await r.json();
  alert(d.message);
  await refresh();
}
async function resetState() {
  await fetch('/api/reset', {method: 'POST'});
  document.getElementById('number').value = '';
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  await refresh();
}
refresh();
setInterval(refresh, 1500);
</script>
</body>
</html>
"""

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.get("/api/status")
def status():
    with _lock:
        return jsonify(_request_state.copy())

@app.post("/api/request")
def simulate_request():
    data = request.get_json(silent=True) or {}
    caller = str(data.get("caller", "")).strip()
    if not caller:
        return jsonify({"message": "Caller number is required."}), 400

    with _lock:
        if _request_state["status"] == "pending":
            return jsonify({"message": "One request is already waiting for approval."}), 409
        _request_state.update({
            "status": "pending",
            "caller": caller,
            "created_at": time.time(),
            "message": "Someone wants to open Joya. Allow or deny the request."
        })
    return jsonify({"message": "Test request received. Joya stays locked until approval."})

@app.post("/api/decision")
def decision():
    data = request.get_json(silent=True) or {}
    choice = data.get("decision")
    if choice not in ("allow", "deny"):
        return jsonify({"message": "Invalid decision."}), 400

    with _lock:
        if _request_state["status"] != "pending":
            return jsonify({"message": "There is no pending request. Joya remains locked."}), 409
        if choice == "allow":
            _request_state.update({
                "status": "approved",
                "message": "Approval granted. Opening Joya on this computer."
            })
        else:
            _request_state.update({
                "status": "denied",
                "message": "Request denied. Joya remains locked."
            })

    if choice == "allow":
        # Opens the already-running Joya app on this same computer.
        threading.Thread(target=lambda: (time.sleep(0.5), webbrowser.open(JOYA_URL)),
                         daemon=True).start()
        return jsonify({"message": "Allowed. Joya is opening in your browser."})
    return jsonify({"message": "Denied. Joya was not opened."})

@app.post("/api/reset")
def reset():
    with _lock:
        _request_state.update({
            "status": "locked",
            "caller": "",
            "created_at": 0.0,
            "message": "Joya is locked. No request is waiting."
        })
    return jsonify({"message": "Reset complete. Joya is locked."})

if __name__ == "__main__":
    print("Joya Permission Test: http://127.0.0.1:5001")
    print("Make sure your existing Joya server is running on port 5000.")
    app.run(host="127.0.0.1", port=5001, debug=False)
