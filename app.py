import os
import csv
import io
import time
import random
import sqlite3
import smtplib
import threading

from dotenv import load_dotenv

load_dotenv()

from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_from_directory, send_file
from werkzeug.utils import secure_filename
import cv2
import numpy as np
import pickle
import qrcode

# -------------------------------------------------------------
# HARDWARE GPIO SETUP
# -------------------------------------------------------------
GPIO_AVAILABLE = False
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(2, GPIO.OUT, initial=GPIO.LOW)  # RED LED
    GPIO.setup(3, GPIO.OUT, initial=GPIO.LOW)  # GREEN LED
    GPIO.setup(4, GPIO.OUT, initial=GPIO.LOW)  # BLUE LED
    GPIO_AVAILABLE = True
except Exception:
    try:
        from gpiozero import LED
        led_red = LED(2)
        led_green = LED(3)
        led_blue = LED(4)
        GPIO_AVAILABLE = "gpiozero"
    except Exception:
        GPIO_AVAILABLE = False


def trigger_led(status):
    def _blink():
        try:
            if GPIO_AVAILABLE is True:
                if status == "present":
                    GPIO.output(3, GPIO.HIGH); time.sleep(1.2); GPIO.output(3, GPIO.LOW)
                elif status == "duplicate":
                    GPIO.output(4, GPIO.HIGH); time.sleep(1.2); GPIO.output(4, GPIO.LOW)
                elif status == "unknown":
                    GPIO.output(2, GPIO.HIGH); time.sleep(1.2); GPIO.output(2, GPIO.LOW)
            elif GPIO_AVAILABLE == "gpiozero":
                if status == "present":
                    led_green.on(); time.sleep(1.2); led_green.off()
                elif status == "duplicate":
                    led_blue.on(); time.sleep(1.2); led_blue.off()
                elif status == "unknown":
                    led_red.on(); time.sleep(1.2); led_red.off()
        except Exception as e:
            print(f"[-] LED Hardware Error: {e}")

    threading.Thread(target=_blink, daemon=True).start()


# -------------------------------------------------------------
# FLASK APPLICATION CONFIGURATION
# -------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")

UPLOAD_FOLDER = 'student_photos'
MATERIALS_FOLDER = 'shared_materials'
QR_FOLDER = 'student_qrs'
ENCODINGS_FILE = 'face_data/encodings.pickle'
RETURNED_CSV = 'returned_components_history.csv'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(MATERIALS_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
os.makedirs('face_data', exist_ok=True)

SCAN_STATE = {
    "is_scanning": False,
    "current_session_id": None,
    "subject": "General",
    "target_group": "Group 1"
}
camera = None


def get_camera():
    global camera
    if camera is None or not camera.isOpened():
        camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
        if not camera.isOpened():
            camera = cv2.VideoCapture(0)
        if camera and camera.isOpened():
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
            camera.set(cv2.CAP_PROP_FPS, 30)
    return camera


def get_greeting(user_name):
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return f"Good morning, {user_name}! ☀️"
    elif 12 <= hour < 17:
        return f"Good afternoon, {user_name}! ⚡"
    elif 17 <= hour < 22:
        return f"Good evening, {user_name}! 🌇"
    return f"Working late, {user_name}? 🌌"


def send_otp_email(recipient_email, otp_code):
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASS = os.getenv("SMTP_PASS")

    try:
        msg = MIMEMultipart()
        msg['From'] = f"AttendVision Security <{SMTP_USER}>"
        msg['To'] = recipient_email
        msg['Subject'] = f"AttendVision Security OTP: {otp_code}"
        body = f"Hello,\n\nYour OTP for password reset is: {otp_code}\nValid for 10 minutes."
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=8)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        print("[+] OTP Email delivered.")
    except Exception as e:
        print(f"[-] SMTP Exception: {e}")


def push_notification(recipient_type, target_group, recipient_usn, title, message):
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        now_str = datetime.now().strftime("%I:%M %p")
        c.execute("""INSERT INTO notifications (recipient_type, target_group, recipient_usn, title, message, created_at, is_read)
                     VALUES (?, ?, ?, ?, ?, ?, 0)""",
                  (recipient_type, target_group, recipient_usn, title, message, now_str))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[-] Push Notification Error: {e}")


def generate_qr_image(usn):
    img = qrcode.make(usn.strip().upper())
    qr_path = os.path.join(QR_FOLDER, f"{usn.strip().upper()}.png")
    img.save(qr_path)
    return qr_path


def log_returned_component_to_csv(req_id, usn, name, group_name, component_name, notes, approved_date, returned_date):
    file_exists = os.path.isfile(RETURNED_CSV)
    with open(RETURNED_CSV, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Request ID", "USN", "Student Name", "Group", "Component Name", "Details/Notes", "Approved Date", "Returned Date"])
        writer.writerow([req_id, usn, name, group_name, component_name, notes, approved_date, returned_date])


def retrain_face_encodings():
    try:
        import face_recognition
        known_encodings = []
        known_names = []
        for usn in os.listdir(UPLOAD_FOLDER):
            user_dir = os.path.join(UPLOAD_FOLDER, usn)
            if os.path.isdir(user_dir):
                for img_file in os.listdir(user_dir):
                    if img_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        path = os.path.join(user_dir, img_file)
                        img = cv2.imread(path)
                        if img is not None:
                            h, w = img.shape[:2]
                            if w > 400:
                                scale = 400.0 / w
                                img = cv2.resize(img, (int(w * scale), int(h * scale)))
                            rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                            boxes = face_recognition.face_locations(rgb, model='hog')
                            if boxes:
                                enc = face_recognition.face_encodings(rgb, boxes)[0]
                                known_encodings.append(enc)
                                known_names.append(usn.upper())
        with open(ENCODINGS_FILE, 'wb') as f:
            pickle.dump({"encodings": known_encodings, "names": known_names}, f)
        print(f"[+] Trained on {len(known_encodings)} face samples.")
    except Exception as e:
        print(f"[-] Retraining error: {e}")


def mark_student_attendance(usn, method="Face Recognition", reason=""):
    if not SCAN_STATE["is_scanning"] or not SCAN_STATE["current_session_id"]:
        return "inactive", "Scanner Off"

    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()
    target_grp = SCAN_STATE.get("target_group", "All Groups")
    
    if target_grp != "All Groups":
        c.execute("SELECT name, is_active, student_group FROM students WHERE usn = ?", (usn,))
        row = c.fetchone()
        if not row or row[1] == 0:
            conn.close()
            trigger_led("unknown")
            return "unknown", "Unknown"
        if row[2] != target_grp:
            conn.close()
            return "duplicate", f"{row[0]} (Not in {target_grp})"
    else:
        c.execute("SELECT name, is_active FROM students WHERE usn = ?", (usn,))
        row = c.fetchone()
        if not row or row[1] == 0:
            conn.close()
            trigger_led("unknown")
            return "unknown", "Unknown"
    
    student_name = row[0]
    session_id = SCAN_STATE["current_session_id"]
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%I:%M:%S %p")
    subj = SCAN_STATE["subject"]
    
    c.execute("SELECT id FROM attendance WHERE student_usn = ? AND session_id = ? AND status = 'PRESENT'", (usn, session_id))
    existing = c.fetchone()
    
    if existing:
        conn.close()
        trigger_led("duplicate")
        return "duplicate", student_name
    
    c.execute('''INSERT OR REPLACE INTO attendance (session_id, student_usn, name, status, date, time, subject, method, reason)
                 VALUES (?, ?, ?, 'PRESENT', ?, ?, ?, ?, ?)''', (session_id, usn, student_name, today, now_time, subj, method, reason))
    conn.commit()
    conn.close()
    trigger_led("present")
    return "present", student_name


def finalize_session_absentees_async(session_id, date_str, time_str, subject_str, target_group):
    def _run():
        try:
            conn = sqlite3.connect('attendance.db')
            c = conn.cursor()
            if target_group == "All Groups":
                c.execute("SELECT usn, name FROM students WHERE is_active = 1")
            else:
                c.execute("SELECT usn, name FROM students WHERE is_active = 1 AND student_group = ?", (target_group,))
            active_students = c.fetchall()
            
            for usn, name in active_students:
                c.execute("SELECT id FROM attendance WHERE session_id = ? AND student_usn = ?", (session_id, usn))
                row = c.fetchone()
                if not row:
                    c.execute('''INSERT INTO attendance (session_id, student_usn, name, status, date, time, subject, method, reason)
                                 VALUES (?, ?, ?, 'ABSENT', ?, ?, ?, 'None', 'Session Concluded')''',
                              (session_id, usn, name, date_str, time_str, subject_str))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Finalize Absentees Error: {e}")

    threading.Thread(target=_run, daemon=True).start()


def generate_live_frames():
    try:
        import face_recognition
    except ImportError:
        face_recognition = None

    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        pyzbar_decode = None

    cam = get_camera()
    qr_cv = cv2.QRCodeDetector()
    known_data = {"encodings": [], "names": []}
    if os.path.exists(ENCODINGS_FILE):
        try:
            with open(ENCODINGS_FILE, 'rb') as f:
                known_data = pickle.load(f)
        except Exception:
            pass

    frame_count = 0
    face_locations = []
    face_tags = []

    while True:
        if not SCAN_STATE["is_scanning"]:
            time.sleep(0.1)
            continue

        if cam is None or not cam.isOpened():
            cam = get_camera()
            time.sleep(0.05)
            continue

        success, frame = cam.read()
        if not success or frame is None:
            time.sleep(0.03)
            continue

        frame_count += 1

        if pyzbar_decode:
            try:
                decoded_objs = pyzbar_decode(frame)
                for obj in decoded_objs:
                    qr_text = obj.data.decode('utf-8').strip().upper()
                    if qr_text:
                        status, name = mark_student_attendance(qr_text, method="QR Code")
                        color = (0, 255, 0) if status == "present" else (255, 100, 0) if status == "duplicate" else (0, 0, 255)
                        cv2.putText(frame, f"QR: {name}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)
            except Exception:
                pass

        if face_recognition and (frame_count % 5 == 0):
            face_tags = []
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            small_rgb = np.ascontiguousarray(cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB))
            face_locations = face_recognition.face_locations(small_rgb, model='hog')

            if len(face_locations) > 0:
                try:
                    face_encodings = face_recognition.face_encodings(small_rgb, face_locations)
                    for face_encoding in face_encodings:
                        status = "unknown"
                        display_name = "NOT RECOGNIZED"
                        box_color = (0, 0, 255)

                        if len(known_data.get("encodings", [])) > 0:
                            face_distances = face_recognition.face_distance(known_data["encodings"], face_encoding)
                            best_idx = np.argmin(face_distances)
                            if face_distances[best_idx] < 0.58:
                                usn_matched = known_data["names"][best_idx]
                                status, display_name = mark_student_attendance(usn_matched, method="Face Recognition")

                        if status == "present":
                            box_color = (0, 255, 0)
                            tag_label = f"{display_name} - PRESENT"
                        elif status == "duplicate":
                            box_color = (255, 100, 0)
                            tag_label = f"{display_name} - MARKED"
                        else:
                            box_color = (0, 0, 255)
                            tag_label = "NOT RECOGNIZED"

                        face_tags.append((box_color, tag_label, status))
                except Exception:
                    face_tags = []

        if len(face_locations) == len(face_tags):
            for (top, right, bottom, left), (box_color, tag_label, status) in zip(face_locations, face_tags):
                top = int(top * 4.0); right = int(right * 4.0); bottom = int(bottom * 4.0); left = int(left * 4.0)
                cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)
                cv2.rectangle(frame, (left, max(0, top - 24)), (left + len(tag_label)*9, top), box_color, cv2.FILLED)
                cv2.putText(frame, tag_label, (left + 4, max(14, top - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 40])
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


# ------------------ ROUTING AND VIEWS ------------------ #

@app.route("/")
def home():
    if session.get("role") == "admin":
        return redirect("/admin")
    elif session.get("role") == "student":
        return redirect("/student_dashboard")
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role_type = request.form.get("role", "Staff")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = sqlite3.connect("attendance.db")
        c = conn.cursor()

        if role_type == "Staff":
            c.execute("SELECT password, email FROM admin_config WHERE username = ?", (username,))
            row = c.fetchone()
            conn.close()
            if row and row[0] == password:
                session["role"] = "admin"
                session["username"] = username
                session["greeting"] = get_greeting("Admin")
                return redirect("/admin")
            return "<script>alert('Invalid Staff Credentials!'); window.location.href='/login';</script>"

        else:
            c.execute("SELECT usn, name, email, student_group, is_active, password FROM students WHERE (LOWER(email) = LOWER(?) OR UPPER(usn) = UPPER(?))", (username, username))
            row = c.fetchone()
            conn.close()

            if row:
                st_usn, st_name, st_email, st_group, is_active, st_pwd = row
                if is_active == 0:
                    return "<script>alert('Account Inactive.'); window.location.href='/login';</script>"
                if st_pwd != password:
                    return "<script>alert('Incorrect Password!'); window.location.href='/login';</script>"

                session["role"] = "student"
                session["student_usn"] = st_usn
                session["student_name"] = st_name
                session["student_email"] = st_email
                session["student_group"] = st_group
                session["greeting"] = get_greeting(st_name.split()[0])
                return redirect("/student_dashboard")

            return "<script>alert('Student not found in database!'); window.location.href='/login';</script>"

    return render_template("login.html")


@app.route("/forgot_password_otp", methods=["POST"])
def forgot_password_otp():
    identifier = request.form.get("reset_identifier", "").strip()
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT email FROM admin_config WHERE id = 1")
    row = c.fetchone()
    admin_email = row[0] if row else "YOUR_GMAIL_ADDRESS_HERE"

    otp = f"{random.randint(100000, 999999)}"
    expiry = time.time() + 600

    c.execute("INSERT OR REPLACE INTO otp_tokens (email, otp, expiry) VALUES (?, ?, ?)", (admin_email, otp, expiry))
    conn.commit()
    conn.close()

    threading.Thread(target=send_otp_email, args=(admin_email, otp), daemon=True).start()
    return jsonify({"success": True, "message": f"OTP sent to {admin_email}"})


@app.route("/verify_reset_password", methods=["POST"])
def verify_reset_password():
    otp_entered = request.form.get("otp_code", "").strip()
    new_password = request.form.get("new_password", "").strip()
    target_usn = request.form.get("target_usn", "").strip()

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT otp, expiry, email FROM otp_tokens WHERE email = (SELECT email FROM admin_config WHERE id = 1)")
    row = c.fetchone()

    if not row or time.time() > row[1] or row[0] != otp_entered:
        conn.close()
        return "<script>alert('Invalid or expired OTP!'); window.location.href='/login';</script>"

    if target_usn:
        c.execute("UPDATE students SET password = ? WHERE usn = ?", (new_password, target_usn.upper()))
    else:
        c.execute("UPDATE admin_config SET password = ? WHERE id = 1", (new_password,))

    c.execute("DELETE FROM otp_tokens WHERE email = ?", (row[2],))
    conn.commit()
    conn.close()
    return "<script>alert('Password updated! Please login.'); window.location.href='/login';</script>"


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect("/login")

    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    
    c.execute("SELECT student_usn, name, status, time, subject, method, reason FROM attendance WHERE date = ? ORDER BY id DESC LIMIT 50", (today,))
    today_records = [{"student_usn": r[0], "name": r[1], "status": r[2], "time": r[3], "subject": r[4], "method": r[5], "reason": r[6]} for r in c.fetchall()]

    c.execute("SELECT usn, name, email, password, student_group, is_active FROM students ORDER BY usn ASC")
    raw_students = c.fetchall()
    
    students_by_group = {"Group 1": [], "Group 2": [], "Group 3": [], "Group 4": [], "Group 5": []}
    for usn, name, email, pwd, grp, active in raw_students:
        grp_name = grp or "Group 1"
        if grp_name not in students_by_group:
            students_by_group[grp_name] = []
        
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_usn = ?", (usn,))
        tot = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM attendance WHERE student_usn = ? AND status = 'PRESENT'", (usn,))
        pres = c.fetchone()[0]
        pct = round((pres / tot * 100), 1) if tot > 0 else 100.0

        students_by_group[grp_name].append({
            "usn": usn, "name": name, "email": email, "password": pwd,
            "group": grp_name, "is_active": active, "percentage": pct,
            "present_count": pres, "total_count": tot
        })

    c.execute("SELECT id, filename, title, target_group, upload_date FROM shared_files ORDER BY id DESC")
    shared_files = [{"id": f[0], "filename": f[1], "title": f[2], "group": f[3], "date": f[4]} for f in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM component_requests WHERE status = 'PENDING'")
    pending_hardware_count = c.fetchone()[0]

    conn.close()
    greeting = session.pop("greeting", None)

    return render_template("admin.html", today=today, today_records=today_records,
                           students_by_group=students_by_group, scan_state=SCAN_STATE,
                           shared_files=shared_files, greeting=greeting,
                           pending_hardware_count=pending_hardware_count)


@app.route("/manual_attendance", methods=["POST"])
def manual_attendance():
    if session.get("role") != "admin":
        return redirect("/login")
    usn = request.form.get("usn", "").strip().upper()
    status = request.form.get("status", "PRESENT").upper()
    subject = request.form.get("subject", "General").strip() or "General"
    reason = request.form.get("reason", "Manual Override").strip()
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%I:%M:%S %p")
    session_id = f"Manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT name FROM students WHERE usn = ?", (usn,))
    row = c.fetchone()
    st_name = row[0] if row else "Student"

    c.execute('''INSERT INTO attendance (session_id, student_usn, name, status, date, time, subject, method, reason)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 'Manual Entry', ?)''',
              (session_id, usn, st_name, status, today, now_time, subject, reason))
    conn.commit()
    conn.close()
    return redirect("/admin?view=scanner")


@app.route("/add_student", methods=["POST"])
def add_student():
    if session.get("role") != "admin":
        return redirect("/login")
    usn = request.form.get("usn", "").strip().upper()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip() or usn
    student_group = request.form.get("student_group", "Group 1").strip()
    department = request.form.get("department", "ISE").strip()
    semester = request.form.get("semester", "Sem 3").strip()
    photos = request.files.getlist("photos")

    student_dir = os.path.join(UPLOAD_FOLDER, usn)
    os.makedirs(student_dir, exist_ok=True)
    generate_qr_image(usn)

    has_new_photos = False
    if photos:
        for idx, photo in enumerate(photos):
            if photo and photo.filename != "":
                ext = os.path.splitext(photo.filename)[1] or ".jpg"
                file_path = os.path.join(student_dir, f"{int(time.time())}_{idx}{ext}")
                photo.save(file_path)
                try:
                    loaded = cv2.imread(file_path)
                    if loaded is not None:
                        h, w = loaded.shape[:2]
                        if w > 400:
                            scale = 400.0 / w
                            loaded = cv2.resize(loaded, (int(w * scale), int(h * scale)))
                            cv2.imwrite(file_path, loaded, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                except Exception:
                    pass
                has_new_photos = True

    if has_new_photos:
        threading.Thread(target=retrain_face_encodings, daemon=True).start()

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO students (usn, name, department, semester, email, password, student_group, is_active, qr_id) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)',
              (usn, name, department, semester, email, password, student_group, usn))
    conn.commit()
    conn.close()
    return redirect(f"/admin?view=groups&group={student_group}")


@app.route("/get_qr/<usn>")
def get_qr(usn):
    qr_path = os.path.join(QR_FOLDER, f"{usn.strip().upper()}.png")
    if not os.path.exists(qr_path):
        generate_qr_image(usn)
    return send_file(qr_path, mimetype='image/png')


@app.route("/delete_student/<usn>")
def delete_student(usn):
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("DELETE FROM students WHERE usn = ?", (usn,))
    c.execute("DELETE FROM component_requests WHERE student_usn = ?", (usn,))
    conn.commit()
    conn.close()
    return redirect("/admin?view=groups")


@app.route("/deduplicate_attendance", methods=["POST"])
def deduplicate_attendance():
    if session.get("role") != "admin":
        return redirect("/login")
    target_date = request.form.get("date", datetime.now().strftime("%Y-%m-%d"))
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("""
        DELETE FROM attendance 
        WHERE date = ? AND id NOT IN (
            SELECT MAX(id) FROM attendance 
            WHERE date = ? 
            GROUP BY student_usn, date
        )
    """, (target_date, target_date))
    deleted_count = conn.total_changes
    conn.commit()
    conn.close()
    return f"<script>alert('Cleaned {deleted_count} duplicates!'); window.location.href='/admin?view=scanner';</script>"


@app.route("/start_scan", methods=["POST"])
def start_scan():
    if session.get("role") != "admin":
        return redirect("/login")
    now = datetime.now()
    session_id = f"Session_{now.strftime('%Y%m%d_%H%M%S')}"
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%I:%M:%S %p")
    subj = request.form.get("subject", "General").strip() or "General"
    grp = request.form.get("target_group", "Group 1").strip()

    SCAN_STATE["is_scanning"] = True
    SCAN_STATE["current_session_id"] = session_id
    SCAN_STATE["subject"] = subj
    SCAN_STATE["target_group"] = grp

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("INSERT INTO scan_sessions (session_id, date, time, subject, downloaded) VALUES (?, ?, ?, ?, 0)",
              (session_id, date_str, time_str, f"{subj} ({grp})"))
    conn.commit()
    conn.close()
    return redirect("/admin?view=scanner")


@app.route("/stop_scan", methods=["POST"])
def stop_scan():
    if session.get("role") != "admin":
        return redirect("/login")
    if SCAN_STATE["is_scanning"] and SCAN_STATE["current_session_id"]:
        sid = SCAN_STATE["current_session_id"]
        now = datetime.now()
        finalize_session_absentees_async(sid, now.strftime("%Y-%m-%d"), now.strftime("%I:%M:%S %p"), SCAN_STATE["subject"], SCAN_STATE.get("target_group", "All Groups"))
    SCAN_STATE["is_scanning"] = False
    SCAN_STATE["current_session_id"] = None
    return redirect("/admin?view=scanner")


@app.route("/video_feed")
def video_feed():
    if session.get("role") != "admin":
        return redirect("/login")
    return Response(generate_live_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/report")
def report():
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT session_id, student_usn, name, status, date, time, subject, method, reason FROM attendance ORDER BY id DESC LIMIT 100")
    logs = [{"session_id": r[0], "usn": r[1], "name": r[2], "status": r[3], "date": r[4], "time": r[5], "subject": r[6], "method": r[7], "reason": r[8]} for r in c.fetchall()]
    
    two_days_ago = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    c.execute("SELECT session_id, date, time, subject, downloaded FROM scan_sessions ORDER BY session_id DESC")
    raw_sessions = c.fetchall()
    
    all_sessions = [{"session_id": s[0], "date": s[1], "time": s[2], "subject": s[3], "downloaded": s[4], "is_expired": s[1] < two_days_ago} for s in raw_sessions]
    conn.close()
    return render_template("report.html", logs=logs, all_sessions=all_sessions)


@app.route("/delete_session/<session_id>", methods=["POST"])
def delete_session(session_id):
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("DELETE FROM scan_sessions WHERE session_id = ?", (session_id,))
    c.execute("DELETE FROM attendance WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()
    return redirect("/report")


@app.route("/export_session_csv/<session_id>")
def export_session_csv(session_id):
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT student_usn, name, status, date, time, subject, method, reason FROM attendance WHERE session_id = ? ORDER BY status ASC, student_usn ASC", (session_id,))
    rows = c.fetchall()
    c.execute("UPDATE scan_sessions SET downloaded = 1 WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["USN", "Student Name", "Status", "Date", "Time", "Subject", "Method", "Reason"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=attendance_{session_id}.csv"})


@app.route("/export_all_csv")
def export_all_csv():
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT session_id, student_usn, name, status, date, time, subject, method, reason FROM attendance ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Session ID", "USN", "Student Name", "Status", "Date", "Time", "Subject", "Method", "Reason"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]])
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=master_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"})


@app.route("/admin/components")
def admin_components():
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT id, student_usn, student_name, student_group, component_name, quantity, notes, status, requested_date, approved_date FROM component_requests WHERE status != 'RETURNED' ORDER BY id DESC")
    active_requests = [{"id": r[0], "usn": r[1], "name": r[2], "group": r[3], "comp": r[4], "qty": r[5], "notes": r[6], "status": r[7], "req_date": r[8], "app_date": r[9]} for r in c.fetchall()]
    conn.close()
    return render_template("components_dashboard.html", requests=active_requests)


@app.route("/approve_component/<int:req_id>", methods=["POST"])
def approve_component(req_id):
    if session.get("role") != "admin":
        return redirect("/login")
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("UPDATE component_requests SET status = 'APPROVED', approved_date = ? WHERE id = ?", (now_str, req_id))
    c.execute("SELECT student_usn, component_name FROM component_requests WHERE id = ?", (req_id,))
    req = c.fetchone()
    if req:
        push_notification("STUDENT", None, req[0], "Hardware Approved! 🚀", f"Your request for {req[1]} has been approved.")
    conn.commit()
    conn.close()
    return redirect("/admin/components")


@app.route("/mark_component_received/<int:req_id>", methods=["POST"])
def mark_component_received(req_id):
    if session.get("role") != "admin":
        return redirect("/login")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("SELECT id, student_usn, student_name, student_group, component_name, notes, approved_date FROM component_requests WHERE id = ?", (req_id,))
    item = c.fetchone()
    if item:
        returned_time = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        log_returned_component_to_csv(item[0], item[1], item[2], item[3], item[4], item[5], item[6] or "N/A", returned_time)
        c.execute("UPDATE component_requests SET status = 'RETURNED' WHERE id = ?", (req_id,))
        conn.commit()
    conn.close()
    return redirect("/admin/components")


@app.route("/export_returned_csv")
def export_returned_csv():
    if session.get("role") != "admin":
        return redirect("/login")
    if not os.path.exists(RETURNED_CSV):
        log_returned_component_to_csv(0, "INIT", "Master Header", "Group 1", "None", "None", "", "")
    return send_from_directory(".", RETURNED_CSV, as_attachment=True)


@app.route("/upload_material", methods=["POST"])
def upload_material():
    if session.get("role") != "admin":
        return redirect("/login")
    title = request.form.get("title", "").strip() or "Course Material"
    target_group = request.form.get("target_group", "All Groups").strip()
    uploaded_file = request.files.get("file")

    if uploaded_file and uploaded_file.filename != "":
        safe_name = secure_filename(uploaded_file.filename)
        save_path = os.path.join(MATERIALS_FOLDER, f"{int(time.time())}_{safe_name}")
        uploaded_file.save(save_path)

        conn = sqlite3.connect("attendance.db")
        c = conn.cursor()
        c.execute("INSERT INTO shared_files (filename, title, target_group, upload_date) VALUES (?, ?, ?, ?)",
                  (os.path.basename(save_path), title, target_group, datetime.now().strftime("%Y-%m-%d %I:%M %p")))
        conn.commit()
        conn.close()

        push_notification("GROUP" if target_group != "All Groups" else "ALL", target_group, None, "New Material Uploaded! 📚", f"Staff shared: '{title}' with {target_group}.")
    return redirect("/admin?view=broadcast")


@app.route("/download_file/<filename>")
def download_file(filename):
    if not session.get("role"):
        return redirect("/login")
    return send_from_directory(MATERIALS_FOLDER, filename, as_attachment=True)


# ------------------ STUDENT DASHBOARD ------------------ #

@app.route("/student_dashboard")
def student_dashboard():
    if session.get("role") != "student":
        return redirect("/login")
    
    usn = session.get("student_usn")
    st_group = session.get("student_group", "Group 1")
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_usn = ?", (usn,))
    total_sessions = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM attendance WHERE student_usn = ? AND status = 'PRESENT'", (usn,))
    present_sessions = c.fetchone()[0]
    percentage = round((present_sessions / total_sessions * 100), 1) if total_sessions > 0 else 100.0

    c.execute("SELECT filename, title, target_group, upload_date FROM shared_files WHERE target_group = 'All Groups' OR target_group = ? ORDER BY id DESC", (st_group,))
    shared_files = [{"filename": f[0], "title": f[1], "group": f[2], "date": f[3]} for f in c.fetchall()]

    c.execute("SELECT id, component_name, quantity, notes, status, requested_date, approved_date FROM component_requests WHERE student_usn = ? ORDER BY id DESC", (usn,))
    my_components = [{"id": r[0], "comp": r[1], "qty": r[2], "notes": r[3], "status": r[4], "req_date": r[5], "app_date": r[6]} for r in c.fetchall()]

    c.execute("SELECT usn, name FROM students WHERE student_group = ? AND usn != ? AND is_active = 1", (st_group, usn))
    group_peers = [{"usn": p[0], "name": p[1]} for p in c.fetchall()]

    conn.close()
    greeting = session.pop("greeting", None)

    return render_template("student_dashboard.html",
                           student_name=session.get("student_name"),
                           student_usn=usn,
                           student_group=st_group,
                           percentage=percentage,
                           total_sessions=total_sessions,
                           present_sessions=present_sessions,
                           shared_files=shared_files,
                           my_components=my_components,
                           group_peers=group_peers,
                           greeting=greeting)


@app.route("/student_add_component", methods=["POST"])
def student_add_component():
    if session.get("role") != "student":
        return redirect("/login")
    
    comp_name = request.form.get("component_name", "").strip()
    qty = int(request.form.get("quantity", 1))
    notes = request.form.get("notes", "").strip()
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    if comp_name:
        conn = sqlite3.connect("attendance.db")
        c = conn.cursor()
        c.execute("""INSERT INTO component_requests 
                     (student_usn, student_name, student_group, component_name, quantity, notes, status, requested_date)
                     VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
                  (session.get("student_usn"), session.get("student_name"), session.get("student_group"), comp_name, qty, notes, now_str))
        conn.commit()
        conn.close()

        push_notification("ADMIN", None, None, "New Hardware Requisition ⚡", f"{session.get('student_name')} ({session.get('student_group')}) requested {comp_name} (x{qty}).")

    return redirect("/student_dashboard?view=hardware")


@app.route("/api/send_chat", methods=["POST"])
def send_chat():
    if session.get("role") != "student":
        return jsonify({"success": False}), 403
    
    data = request.get_json() or {}
    msg_type = data.get("type", "group")
    recipient_usn = data.get("recipient_usn")
    msg_text = data.get("message", "").strip()
    now_str = datetime.now().strftime("%I:%M %p")
    my_usn = session.get("student_usn")
    my_name = session.get("student_name")
    my_grp = session.get("student_group")

    if not msg_text:
        return jsonify({"success": False})

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()

    if msg_type == "direct" and recipient_usn:
        c.execute("""INSERT INTO private_messages (sender_usn, receiver_usn, sender_name, message, timestamp)
                     VALUES (?, ?, ?, ?, ?)""", (my_usn, recipient_usn, my_name, msg_text, now_str))
        push_notification("STUDENT", None, recipient_usn, f"Direct Message from {my_name}", msg_text)
    else:
        c.execute("""INSERT INTO group_messages (student_group, sender_usn, sender_name, message, timestamp)
                     VALUES (?, ?, ?, ?, ?)""", (my_grp, my_usn, my_name, msg_text, now_str))
        push_notification("GROUP", my_grp, None, f"{my_grp} Message from {my_name}", msg_text)

    conn.commit()
    conn.close()
    return jsonify({"success": True, "sender_name": my_name, "sender_usn": my_usn, "time": now_str})


@app.route("/api/get_chats")
def get_chats():
    if session.get("role") != "student":
        return jsonify([]), 403
    
    chat_type = request.args.get("type", "group")
    peer_usn = request.args.get("peer_usn")
    my_usn = session.get("student_usn")
    my_grp = session.get("student_group")

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()

    if chat_type == "direct" and peer_usn:
        c.execute("""SELECT sender_usn, sender_name, message, timestamp FROM private_messages
                     WHERE (sender_usn = ? AND receiver_usn = ?) OR (sender_usn = ? AND receiver_usn = ?)
                     ORDER BY id ASC LIMIT 50""", (my_usn, peer_usn, peer_usn, my_usn))
    else:
        c.execute("SELECT sender_usn, sender_name, message, timestamp FROM group_messages WHERE student_group = ? ORDER BY id ASC LIMIT 50", (my_grp,))

    messages = [{"usn": m[0], "name": m[1], "text": m[2], "time": m[3]} for m in c.fetchall()]
    conn.close()
    return jsonify(messages)


@app.route("/api/get_notifications")
def get_notifications():
    role = session.get("role")
    if not role:
        return jsonify([])

    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()

    if role == "admin":
        c.execute("SELECT id, title, message, created_at FROM notifications WHERE recipient_type = 'ADMIN' ORDER BY id DESC LIMIT 10")
    else:
        usn = session.get("student_usn")
        grp = session.get("student_group")
        c.execute("""SELECT id, title, message, created_at FROM notifications
                     WHERE recipient_type = 'ALL' 
                        OR (recipient_type = 'GROUP' AND target_group = ?)
                        OR (recipient_type = 'STUDENT' AND recipient_usn = ?)
                     ORDER BY id DESC LIMIT 10""", (grp, usn))

    notifs = [{"id": r[0], "title": r[1], "message": r[2], "time": r[3]} for r in c.fetchall()]
    conn.close()
    return jsonify(notifs)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
