import os
import sqlite3
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "ascii.weather.alert@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# ==============================================================================
# 2. EMERGENCY HOTLINES
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
# 3. DATABASE SETUP
# ==============================================================================
def init_db():
    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# 4. BACKGROUND EMAIL WORKER (UPDATED TO PORT 465 SSL)
# ==============================================================================
def send_bulk_emails(users, subject, msg_body):
    """
    Runs in the background. Uses Port 465 (SSL) which is more reliable
    for Cloud Hosting than Port 587.
    """
    if not SENDER_PASSWORD:
        print("❌ SKIPPING EMAILS: Password not found in Environment Variables.")
        return

    print(f"🔄 BACKGROUND TASK: Sending emails to {len(users)} users...")

    try:
        # --- FIX: USE SMTP_SSL ON PORT 465 ---
        # This is the "Secure" port that often fixes 'Network Unreachable' errors
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        
        # Login
        server.login(SENDER_EMAIL, SENDER_PASSWORD)

        count = 0
        for user in users:
            name = user[0]
            phone = user[1]
            user_email = user[2]
            
            if user_email:
                try:
                    personal_msg = f"Hello {name},\n\n{msg_body}"
                    msg = MIMEMultipart()
                    msg['From'] = SENDER_EMAIL
                    msg['To'] = user_email
                    msg['Subject'] = subject
                    msg.attach(MIMEText(personal_msg, 'plain'))
                    
                    server.send_message(msg)
                    count += 1
                    print(f"   -> Sent to {user_email}")
                except Exception as e:
                    print(f"   -> Failed for {user_email}: {e}")

        server.quit()
        print(f"✅ FINISHED: Sent {count} emails successfully.")

    except Exception as e:
        print(f"❌ BULK EMAIL ERROR: {e}")

# ==============================================================================
# 5. ROUTES
# ==============================================================================
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (name, role, phone, email, password) VALUES (?, ?, ?, ?, ?)",
                  (data['name'], data['role'], data['phone'], data.get('email', ''), data['password']))
        conn.commit()
        return jsonify({"status": "success", "message": "User registered successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():  
    data = request.json
    user_input = data['phone']
    password = data['password']

    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE (phone=? OR email=?) AND password=?", (user_input, user_input, password))
    user = c.fetchone()
    conn.close()

    if user:
        return jsonify({"status": "success", "user": user[1], "role": user[2]})
    else:
        return jsonify({"status": "error", "message": "Invalid credentials"})

# ==============================================================================
# 6. TRIGGER ALERT
# ==============================================================================
@app.route('/api/trigger-alert', methods=['POST'])
def trigger_alert():
    data = request.json
    level = data.get('level')
    location = data.get('location', 'Angeles City, Pampanga')
    
    local_hotlines = HOTLINES.get(location, "National Emergency: 911")

    if level == 'yellow':
        subject = f"⚠️ ACSCI-gurado: YELLOW WARNING ({location})"
        msg_body = (
            f"WARNING: Heavy rain detected in {location}.\n"
            "Flooding is possible in low-lying areas.\n\n"
            f"EMERGENCY HOTLINES:\n{local_hotlines}"
        )
    elif level == 'orange':
        subject = f"🚨 ACSCI-gurado: ORANGE WARNING ({location})"
        msg_body = (
            f"EMERGENCY: Severe thunderstorm in {location}. Evacuate immediately.\n\n"
            f"EMERGENCY HOTLINES:\n{local_hotlines}"
        )
    else:
        return jsonify({"status": "ignored"})

    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    users = c.execute("SELECT name, phone, email FROM users").fetchall()
    conn.close()

    # Start Background Thread
    email_thread = threading.Thread(target=send_bulk_emails, args=(users, subject, msg_body))
    email_thread.start()

    return jsonify({"status": "success", "message": "Alert broadcast started in background."})

# ==============================================================================
# 7. DEBUG ROUTE (TEST EMAIL MANUALLY)
# ==============================================================================
@app.route('/debug-email')
def debug_email():
    """
    Use this route to test if emails work.
    Go to: https://your-website.com/debug-email
    """
    recipient = "jrtomasva09@gmail.com" # Default test email
    
    if not SENDER_PASSWORD:
        return "❌ ERROR: SENDER_PASSWORD is missing in Environment Variables."
    
    try:
        # Using SMTP_SSL (Port 465) for Debug too
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        msg = MIMEText("This is a DEBUG email from your live website.")
        msg['Subject'] = "Debug Test (Port 465)"
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient
        
        server.send_message(msg)
        server.quit()
        return f"✅ SUCCESS! Email sent to {recipient} using Port 465."
        
    except Exception as e:
        return f"❌ FAILED. Error: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True, port=5000)
