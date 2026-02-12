import sqlite3
import smtplib
import os
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
SENDER_EMAIL = "ascii.weather.alert@gmail.com"
SENDER_PASSWORD = "rcxg jftr wzel nwel"

# ==============================================================================
# 2. EMERGENCY HOTLINE DATABASE
# ==============================================================================
HOTLINES = {
    'Angeles City, Pampanga': "• Angeles CDRRMO: (045) 322-7796\n• Pampanga PDRRMO: (045) 961-0414\n• Police: 166",
    'City of San Fernando, Pampanga': "• San Fernando Rescue: (045) 961-1422\n• Pampanga PDRRMO: (045) 961-0414",
    'San Fernando, Pampanga': "• San Fernando Rescue: (045) 961-1422\n• Pampanga PDRRMO: (045) 961-0414",
    'Mabalacat City, Pampanga': "• Mabalacat CDRRMO: (045) 331-0000\n• Pampanga PDRRMO: (045) 961-0414",
    'Manila, Metro Manila': "• Manila DRRMO: (02) 8527-5174\n• MMDA: 136\n• Red Cross: 143",
    'Quezon City, Metro Manila': "• QC DRRMO: 122\n• National Emergency: 911",
    'Baguio City, Benguet': "• Baguio CDRRMO: (074) 442-1900\n• Police: 166",
    'Tagaytay City, Cavite': "• Tagaytay CDRRMO: (046) 483-0000\n• Cavite PDRRMO: (046) 419-1919",
    'Cebu City, Cebu': "• Cebu CDRRMO: (032) 255-0000\n• ERUF: 161",
    'Davao City, Davao del Sur': "• Davao Central 911: 911\n• Police: (082) 224-1313"
}

# ==============================================================================
# 3. DATABASE SETUP (Self-Healing)
# ==============================================================================
def init_db():
    try:
        conn = sqlite3.connect('thunderguard.db')
        c = conn.cursor()
        
        # Create table if not exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                password TEXT NOT NULL,
                is_online INTEGER DEFAULT 0 
            )
        ''')
        
        # Add 'is_online' if missing
        try:
            c.execute("SELECT is_online FROM users LIMIT 1")
        except sqlite3.OperationalError:
            print("⚠️ Adding missing column 'is_online'...")
            c.execute("ALTER TABLE users ADD COLUMN is_online INTEGER DEFAULT 0")
        
        # Reset everyone to Offline on startup
        c.execute("UPDATE users SET is_online = 0")
        
        conn.commit()
        conn.close()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"❌ Database Error: {e}")

init_db()

# ==============================================================================
# 4. EMAIL LOGIC (Threaded)
# ==============================================================================
def send_email_task(recipient_email, subject, body):
    if not SENDER_PASSWORD:
        print("❌ EMAIL ERROR: Password not configured.")
        return

    try:
        print(f"⏳ Sending email to {recipient_email}...") # Debug log
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Timeout set to 10s
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ EMAIL SENT to {recipient_email}")
        
    except OSError:
        print(f"⚠️ CLOUD BLOCK: Render blocked connection to {recipient_email}. (Works locally).")
    except Exception as e:
        print(f"❌ EMAIL FAILED to {recipient_email}: {str(e)}")

def send_real_email(recipient_email, subject, body):
    # Start in background thread
    thread = threading.Thread(target=send_email_task, args=(recipient_email, subject, body))
    thread.start()

def send_simulated_sms(phone_number, message):
    print(f"\n[SMS GATEWAY] Sending to {phone_number}: {message}")

# ==============================================================================
# 5. ROUTES
# ==============================================================================
@app.route('/')
def home(): return render_template('login.html')

@app.route('/dashboard')
def dashboard(): return render_template('index.html')

@app.route('/login')
def login_page(): return render_template('login.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    try:
        conn = sqlite3.connect('thunderguard.db')
        c = conn.cursor()
        c.execute("INSERT INTO users (name, role, phone, email, password, is_online) VALUES (?, ?, ?, ?, ?, 0)",
                  (data['name'], data['role'], data['phone'], data.get('email', ''), data['password']))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Registered!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/login', methods=['POST'])
def api_login():  
    data = request.json
    user_input = data['phone']
    password = data['password']

    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE (phone=? OR email=?) AND password=?", (user_input, user_input, password))
    user = c.fetchone()

    if user:
        # User found! Mark ONLINE
        user_id = user[0]
        c.execute("UPDATE users SET is_online = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "user": user[1], "role": user[2]})
    else:
        conn.close()
        return jsonify({"status": "error", "message": "Invalid credentials"})

# ==============================================================================
# 6. TRIGGER ALERTS (THE FIX)
# ==============================================================================
@app.route('/api/trigger-alert', methods=['POST'])
def trigger_alert():
    data = request.json
    level = data.get('level')
    location = data.get('location', 'Angeles City, Pampanga')
    
    local_hotlines = HOTLINES.get(location, "National Emergency: 911")

    if level == 'yellow':
        subject = f"⚠️ ACSCI-gurado: YELLOW WARNING ({location})"
        msg_body = (f"WARNING: Heavy rain detected in {location}.\n\nHOTLINES:\n{local_hotlines}")
    elif level == 'orange':
        subject = f"🚨 ACSCI-gurado: ORANGE WARNING ({location})"
        msg_body = (f"EMERGENCY: Severe storm in {location}. Evacuate immediately.\n\nHOTLINES:\n{local_hotlines}")
    else:
        return jsonify({"status": "ignored"})

    # Fetch ONLY ONLINE USERS
    try:
        conn = sqlite3.connect('thunderguard.db')
        c = conn.cursor()
        users = c.execute("SELECT name, phone, email FROM users WHERE is_online = 1").fetchall()
        conn.close()
    except Exception as e:
        print("DB Error:", e)
        users = []

    print(f"\n--- TRIGGERING {level.upper()} ALERT FOR {len(users)} ONLINE USERS ---")

    for user in users:
        name = user[0]
        phone = user[1]
        registered_email = user[2] 
        
        personal_msg = f"Hello {name},\n\n{msg_body}"
        
        # 1. Send SMS
        if phone:
            send_simulated_sms(phone, personal_msg)
            
        # 2. Send Email (DEBUGGING ADDED)
        if registered_email and registered_email.strip() != "":
            print(f"📧 Found valid email for {name}: {registered_email}. Sending now...")
            send_real_email(registered_email, subject, personal_msg)
        else:
            print(f"⚠️ NO EMAIL found for user {name}. Skipping email.")

    return jsonify({"status": "success", "count": len(users)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
