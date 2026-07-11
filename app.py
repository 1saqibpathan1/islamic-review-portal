from flask import Flask, request, redirect, session, render_template_string
import psycopg2
import json
import os
import time

app = Flask(__name__)
app.secret_key = "change_this_secret"

VIDEO_MAP_FILE = "video_id_map.json"
DATABASE_URL = os.environ.get("DATABASE_URL")
CLEAN_TRANSCRIPTS_FOLDER = "claude_cleaned_50"

print("DATABASE_URL =", DATABASE_URL)
print("DATABASE_URL exists:", DATABASE_URL is not None)


def get_db():
    print("Attempting PostgreSQL connection...")

    conn = psycopg2.connect(
        DATABASE_URL,
        connect_timeout=10
    )

    print("Connected successfully!")

    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id SERIAL PRIMARY KEY,
        video_id TEXT UNIQUE,
        reviewer TEXT,
        status TEXT,
        comment TEXT,
        started_at TIMESTAMP,
        reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        time_taken INTEGER DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'scholar',
        is_active BOOLEAN DEFAULT TRUE
    );
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()


def load_videos():
    with open(VIDEO_MAP_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_review(video_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT reviewer, status, comment, reviewed_at, time_taken
        FROM reviews
        WHERE video_id=%s
    """, (video_id,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    return row


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
        SELECT * FROM users
        WHERE email=%s AND password=%s AND is_active=TRUE
        """, (
            request.form["email"],
            request.form["password"]
        ))

        user = cur.fetchone()

        cur.close()
        conn.close()

        if not user:
            return "Invalid Login"

        session["user"] = user[1]
        session["role"] = user[4]

        return redirect("/videos")

    return """
    <style>
    body{
        background:#f5f7fb;
        font-family:Arial,sans-serif;
        display:flex;
        justify-content:center;
        align-items:center;
        height:100vh;
    }
    .card{
        background:white;
        padding:40px;
        border-radius:20px;
        box-shadow:0 15px 40px rgba(0,0,0,0.08);
        width:400px;
    }
    input,button{
        width:100%;
        padding:14px;
        margin-top:10px;
        border-radius:10px;
        border:1px solid #ddd;
    }
    button{
        background:#2563eb;
        color:white;
        border:none;
        font-weight:bold;
    }
    a{
        text-decoration:none;
        color:#2563eb;
    }
    </style>

    <div class="card">
    <h2>Islamic Transcript Review Portal</h2>
    <form method='post'>
    Email<br>
    <input name='email'><br>
    Password<br>
    <input type='password' name='password'><br>
    <button>Login</button>
    </form>
    <br>
    <a href='/register'>Create Account</a>
    </div>
    """


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO users (name,email,password,role)
        VALUES (%s,%s,%s,%s)
        """, (
            request.form["name"],
            request.form["email"],
            request.form["password"],
            "scholar"
        ))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/")

    return """
    <style>
    body{
        background:#f5f7fb;
        font-family:Arial,sans-serif;
        display:flex;
        justify-content:center;
        align-items:center;
        height:100vh;
    }
    .card{
        background:white;
        padding:40px;
        border-radius:20px;
        box-shadow:0 15px 40px rgba(0,0,0,0.08);
        width:400px;
    }
    input,button{
        width:100%;
        padding:14px;
        margin-top:10px;
        border-radius:10px;
        border:1px solid #ddd;
    }
    button{
        background:#16a34a;
        color:white;
        border:none;
    }
    </style>

    <div class="card">
    <h2>Create Scholar Account</h2>
    <form method='post'>
    Name<br><input name='name'><br>
    Email<br><input name='email'><br>
    Password<br><input type='password' name='password'><br>
    <button>Create Account</button>
    </form>
    </div>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/videos")
def videos():
    if "user" not in session:
        return redirect("/")

    search = request.args.get("q", "").lower()
    status_filter = request.args.get("status", "")

    vids = load_videos()

    html = f"""
    <style>
    body{{background:#f5f7fb;font-family:Arial;padding:30px;}}
    .container{{max-width:1200px;margin:auto;}}
    .card{{background:white;padding:25px;border-radius:18px;box-shadow:0 8px 25px rgba(0,0,0,0.08);}}
    .video-item{{padding:12px;margin:8px 0;background:#fafafa;border-radius:10px;}}
    input,select,button{{padding:10px;border-radius:10px;border:1px solid #ddd;}}
    button{{background:#2563eb;color:white;border:none;}}
    </style>

    <div class="container">
    <div class="card">

    <h2>Welcome {session['user']}</h2>
    <a href='/logout'>Logout</a> |
    <a href='/admin'>Admin Dashboard</a>

    <br><br>

    <form>
    <input name='q' placeholder='Search title' value='{search}'>

    <select name='status'>
        <option value=''>All</option>
        <option value='Pending'>Pending</option>
        <option value='Approved'>Approved</option>
        <option value='Minor'>Minor</option>
        <option value='Major'>Major</option>
    </select>

    <button>Search</button>
    </form>
    <hr>
    """

    count = 0

    for _, video in vids.items():
        title = video["title"]
        review = reviews.get(video["video_id"])

        if search and search not in title.lower():
            continue

        if status_filter:
            if status_filter == "Pending" and review:
                continue
            elif status_filter != "Pending":
                if not review or review[1] != status_filter:
                    continue

        if review:
            badge = "🟢" if review[1] == "Approved" else ("🟡" if review[1] == "Minor" else "🔴")
        else:
            badge = "⚪ Pending"

        html += f"<div class='video-item'>{badge} <a href='/review/{video['video_id']}'>{title}</a></div>"
        count += 1

    html += f"<hr><b>Total Shown:</b> {count}</div></div>"
    return html


@app.route("/review/<video_id>", methods=["GET", "POST"])
def review(video_id):
    if "user" not in session:
        return redirect("/")

    vids = load_videos()
        conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            video_id,
            reviewer,
            status,
            comment,
            reviewed_at,
            time_taken
        FROM reviews
    """)

    review_rows = cur.fetchall()

    cur.close()
    conn.close()

    reviews = {}

    for row in review_rows:
        reviews[row[0]] = row
    selected = None

    for _, v in vids.items():
        if v["video_id"] == video_id:
            selected = v
            break

    if not selected:
        return "Video not found"

    existing_review = get_review(video_id)

    if existing_review and session.get("role") != "admin":
        return f"""
        Already reviewed by {existing_review[0]}<br><br>
        Status: {existing_review[1]}<br><br>
        Comment: {existing_review[2]}
        """

    start_time = time.time()

    with open(selected["transcript_file"], "r", encoding="utf-8") as f:
        transcript_text = f.read()

    all_clean_files = sorted(os.listdir(CLEAN_TRANSCRIPTS_FOLDER))
    video_list = list(vids.values())

    clean_transcript = ""

    current_index = None

    for i, v in enumerate(video_list):
        if v["video_id"] == video_id:
            current_index = i
            break

    if current_index is not None and current_index < len(all_clean_files):
        clean_path = os.path.join(CLEAN_TRANSCRIPTS_FOLDER, all_clean_files[current_index])

        with open(clean_path, "r", encoding="utf-8") as f:
            clean_transcript = f.read()

    next_link = ""

    for i, v in enumerate(video_list):
        if v["video_id"] == video_id:
            for nxt in video_list[i + 1:]:
                if not get_review(nxt["video_id"]):
                    next_link = f"/review/{nxt['video_id']}"
                    break

    if request.method == "POST":
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO reviews
        (video_id, reviewer, status, comment, time_taken)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (video_id)
        DO UPDATE SET
            reviewer = EXCLUDED.reviewer,
            status = EXCLUDED.status,
            comment = EXCLUDED.comment,
            time_taken = EXCLUDED.time_taken,
            reviewed_at = CURRENT_TIMESTAMP
        """, (
            video_id,
            session["user"],
            request.form["status"],
            request.form["comment"],
            int(time.time() - start_time)
        ))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/videos")

    return render_template_string("""
    <style>
    body{background:#f5f7fb;font-family:Arial;padding:20px;}
    .container{max-width:1600px;margin:auto;}
    .card{background:white;padding:20px;border-radius:18px;box-shadow:0 8px 25px rgba(0,0,0,0.08);}
    textarea{border-radius:12px;padding:15px;background:#fafafa;}
    button,select{padding:10px 14px;border:none;border-radius:10px;background:#2563eb;color:white;}
    .compare-grid{display:flex;gap:20px;}
    .next-btn{background:#16a34a;padding:10px 18px;border-radius:10px;color:white;text-decoration:none;}
    </style>

    <div class="container">
    <div class="card">

    <a href='/videos'>← Back</a>
    <h2>{{title}}</h2>

    <iframe width="100%" height="500"
    style="border-radius:15px;"
    src="https://www.youtube.com/embed/{{video_id}}"></iframe>

    <br><br>

    <label>Choose Font:</label>

    <select onchange="changeFont(this.value)">
        <option value="'Noto Nastaliq Urdu','Jameel Noori Nastaleeq'" selected>Nastaliq</option>
        <option value="'Noto Naskh Arabic','Amiri'">Naskh</option>
        <option value="'Arial'">Simple</option>
    </select>

    <br><br>

    <div class="compare-grid">

        <div style="width:50%;">
            <h3>Raw Transcript</h3>

            <button onclick="changeSize('rawbox',2)">A+</button>
            <button onclick="changeSize('rawbox',-2)">A-</button>

            <textarea id="rawbox"
            style="width:100%;height:500px;font-family:'Noto Nastaliq Urdu';font-size:24px;line-height:2.2;direction:rtl;text-align:right;"
            readonly>{{transcript}}</textarea>
        </div>

        <div style="width:50%;">
            <h3>Clean Transcript</h3>

            <button onclick="changeSize('cleanbox',2)">A+</button>
            <button onclick="changeSize('cleanbox',-2)">A-</button>

            <textarea id="cleanbox"
            style="width:100%;height:500px;font-family:'Noto Nastaliq Urdu';font-size:24px;line-height:2.2;direction:rtl;text-align:right;"
            readonly>{{clean_transcript}}</textarea>
        </div>

    </div>

    <br>

    {% if next_link %}
    <a class="next-btn" href="{{next_link}}">Next Pending →</a>
    <br><br>
    {% endif %}

    <form method="post">

    <select name="status">
        <option value="Approved">Approved</option>
        <option value="Minor">Minor Correction</option>
        <option value="Major">Major Correction</option>
    </select>

    <br><br>

    <textarea name="comment" style="width:100%;height:120px;"></textarea>

    <br><br>

    <button>Save Review</button>
    </form>

        <script>
    function changeSize(id, amount) {
        let box = document.getElementById(id);
        let currentSize = parseFloat(window.getComputedStyle(box).fontSize);
        box.style.fontSize = (currentSize + amount) + "px";
    }

    function changeFont(font) {
        document.getElementById("rawbox").style.fontFamily = font;
        document.getElementById("cleanbox").style.fontFamily = font;
    }
    </script>

    </div>
    </div>
    """,
    title=selected["title"],
    video_id=selected["video_id"],
    transcript=transcript_text,
    clean_transcript=clean_transcript,
    next_link=next_link
    )


@app.route("/admin")
def admin():
    if session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM reviews")
    total_reviews = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM reviews WHERE status='Approved'")
    approved = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM reviews WHERE status='Minor'")
    minor = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM reviews WHERE status='Major'")
    major = cur.fetchone()[0]

    cur.execute("""
    SELECT reviewer, COUNT(*), AVG(time_taken)
    FROM reviews
    GROUP BY reviewer
    ORDER BY COUNT(*) DESC
    """)

    reviewers = cur.fetchall()

    cur.close()
    conn.close()

    total_videos = len(load_videos())
    pending = total_videos - total_reviews
    progress = round((total_reviews / total_videos) * 100, 2)

    html = f"""
    <style>
    body{{background:#f5f7fb;font-family:Arial;padding:30px;}}
    .card{{max-width:800px;margin:auto;background:white;padding:30px;border-radius:18px;box-shadow:0 8px 25px rgba(0,0,0,0.08);}}
    progress{{width:100%;height:25px;}}
    </style>

    <div class="card">
    <h1>Admin Dashboard</h1>
    <a href='/videos'>← Back</a><hr>

    Total Videos: {total_videos}<br><br>
    Progress: {progress}%<br>
    <progress value="{total_reviews}" max="{total_videos}"></progress><br><br>

    Pending: {pending}<br><br>
    Approved: {approved}<br><br>
    Minor: {minor}<br><br>
    Major: {major}<hr>

    <h2>Reviewer Stats</h2>
    """

    for r in reviewers:
        avg_time = int(r[2]) if r[2] else 0
        mins = avg_time // 60
        secs = avg_time % 60

        html += f"{r[0]} : {r[1]} reviews | Avg Time: {mins}m {secs}s<br>"

    html += "</div>"
    return html


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
