from flask import Flask, request, render_template_string, g
import sqlite3, datetime

app = Flask(__name__)
DB = "college.db"


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db():
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS students(
        id INTEGER PRIMARY KEY, name TEXT, father_phone TEXT, course TEXT DEFAULT 'BCA');
    CREATE TABLE IF NOT EXISTS attendance(
        student_id INTEGER, date TEXT, status TEXT, UNIQUE(student_id, date));
    """)
    if con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
        for i in range(1, 26):  # 25 demo students - replace with real names/numbers
            con.execute("INSERT INTO students(name, father_phone) VALUES(?,?)",
                        (f"sohil {i}", "7318135376"))
    con.commit()
    con.close()


def send_sms(phone, text):
    # Abhi sirf print hota hai. Asli SMS ke liye Fast2SMS / Twilio API yahan lagayein.
    print(f"SMS to {phone}: {text}")


PAGE = """
<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Attendance</title>
<style>
body{font-family:sans-serif;max-width:480px;margin:auto;padding:12px}
.row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #ddd}
button.sub{width:100%;padding:14px;font-size:18px;margin-top:16px}
</style>
<h2>Attendance - {{today}}</h2>
{% if done %}<p><b>Ho gaya! {{absent}} absent, unke father ko message bhej diya.</b></p>{% endif %}
<form method=post>
{% for s in students %}
<div class=row><span>{{s['name']}}</span>
<select name="s{{s['id']}}"><option value=P>Present</option><option value=A>Absent</option></select></div>
{% endfor %}
<button class=sub>Submit Attendance</button>
</form>
"""


@app.route("/", methods=["GET", "POST"])
def attendance():
    today = datetime.date.today().isoformat()
    students = db().execute("SELECT * FROM students").fetchall()
    done, absent = False, 0
    if request.method == "POST":
        for s in students:
            status = request.form.get(f"s{s['id']}", "P")
            db().execute("INSERT OR REPLACE INTO attendance VALUES(?,?,?)",
                         (s["id"], today, status))
            if status == "A":
                absent += 1
                send_sms(s["father_phone"],
                         f"Aapka bachcha {s['name']} aaj ({today}) college nahi aaya.")
        db().commit()
        done = True
    return render_template_string(PAGE, students=students, today=today, done=done, absent=absent)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)