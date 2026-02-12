import os 
import sqlite3
import smtplib
import threading 
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, render_template

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

# ==============================================================================
# 1. CONFIGURATION (THE SENDER)
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
# 3. DATABASE SETUP
# ==============================================================================
def init_db():
    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    # Create table with EMAIL column
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
# 4. HELPER FUNCTIONS
# ==============================================================================
def send_email_task(recipient_email, subject, body):
    """
    Background task to send email. Catches errors so the server doesn't crash.
    """
    if not SENDER_PASSWORD:
        print(f"❌ EMAIL SKIPPED: Password not set.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Add a timeout so it doesn't hang forever on Render
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ EMAIL SENT to {recipient_email}")
        
    except OSError:
        print(f"⚠️ CLOUD BLOCK: Render blocked email to {recipient_email}. (Normal on free tier).")
    except Exception as e:
        print(f"❌ EMAIL FAILED to {recipient_email}: {str(e)}")

def send_real_email(recipient_email, subject, body):
    """
    Wrapper that starts the email task in a background thread.
    This prevents the 'WORKER TIMEOUT' error on Render.
    """
    thread = threading.Thread(target=send_email_task, args=(recipient_email, subject, body))
    thread.start()
def send_simulated_sms(phone_number, message):
    print(f"\n[SMS GATEWAY] Sending to {phone_number}: {message}")
    print("---------------------------------------------------")

# ==============================================================================
# 5. WEB PAGE ROUTES
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

# ==============================================================================
# 6. API: REGISTER USER
# ==============================================================================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    try:
        # Save the user's specific email to the database
        c.execute("INSERT INTO users (name, role, phone, email, password) VALUES (?, ?, ?, ?, ?)",
                  (data['name'], data['role'], data['phone'], data.get('email', ''), data['password']))
        conn.commit()
        return jsonify({"status": "success", "message": "User registered successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
    finally:
        conn.close()

# ==============================================================================
# 7. API: LOGIN USER
# ==============================================================================
@app.route('/api/login', methods=['POST'])
def api_login():  
    data = request.json
    user_input = data['phone']  # Can be Email OR Phone
    password = data['password']

    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    
    # Check if input matches Phone OR Email
    c.execute("""
        SELECT * FROM users 
        WHERE (phone=? OR email=?) AND password=?
    """, (user_input, user_input, password))
    
    user = c.fetchone()
    conn.close()

    if user:
        return jsonify({"status": "success", "user": user[1], "role": user[2]})
    else:
        return jsonify({"status": "error", "message": "Invalid credentials"})

# ==============================================================================
# 8. API: TRIGGER ALERTS (UPDATED WITH LOCATION & HOTLINES)
# ==============================================================================
@app.route('/api/trigger-alert', methods=['POST'])
def trigger_alert():
    data = request.json
    level = data.get('level')
    
    # Get the location sent from the frontend (Default to Angeles if missing)
    location = data.get('location', 'Angeles City, Pampanga')
    
    # 1. Fetch the correct hotlines for this location
    local_hotlines = HOTLINES.get(location, "National Emergency: 911")

    # 2. Define Message Content based on Alert Level
    if level == 'yellow':
        subject = f"⚠️ ACSCI-gurado: YELLOW WARNING ({location})"
        msg_body = (
            f"WARNING: Heavy rain detected in {location}.\n"
            "Flooding is possible in low-lying areas.\n\n"
            "PRECAUTIONARY MEASURES:\n"
            "- Monitor local news.\n"
            "- Prepare emergency kit.\n\n"
            f"EMERGENCY HOTLINES FOR {location.upper()}:\n"
            f"{local_hotlines}"
        )
    elif level == 'orange':
        subject = f"🚨 ACSCI-gurado: ORANGE WARNING ({location})"
        msg_body = (
            f"EMERGENCY: Severe thunderstorm imminent in {location}. Evacuate immediately.\n"
            "Proceed to a nearby evacuation zone.\n\n"
            f"For emergency contact these hotlines of {location.upper()}:\n"
            f"{local_hotlines}"
        )
    else:
        return jsonify({"status": "ignored"})

    # --- 3. GET ALL USERS FROM DATABASE ---
    conn = sqlite3.connect('thunderguard.db')
    c = conn.cursor()
    users = c.execute("SELECT name, phone, email FROM users").fetchall()
    conn.close()

    print(f"\n--- TRIGGERING {level.upper()} ALERT FOR {location} ---")

    # --- 4. LOOP AND SEND TO EACH REGISTERED EMAIL ---
    for user in users:
        name = user[0]
        phone = user[1]
        registered_email = user[2] 
        
        personal_msg = f"Hello {name},\n\n{msg_body}"
        
        # Send SMS (Simulated)
        if phone:
            send_simulated_sms(phone, personal_msg)
            
        # Send Email (Real)
        if registered_email:
            send_real_email(registered_email, subject, personal_msg)

    return jsonify({"status": "success", "count": len(users)})

# --- REPLACE THE BOTTOM OF YOUR FILE WITH THIS ---

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
