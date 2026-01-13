from flask import Flask, render_template, request, send_file, redirect, session, after_this_request
import os, sqlite3
from datetime import date, timedelta
from PIL import Image
import razorpay
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "static/output"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ---------- RAZORPAY ----------
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

# ---------- DATABASE ----------
def get_db():
    return sqlite3.connect("limits.db")

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS limit_usage (
            ip TEXT,
            date TEXT,
            count INTEGER
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS premium_users (
            payment_id TEXT,
            expiry TEXT
        )
    """)
    db.commit()
    db.close()

init_db()

# ---------- PREMIUM CHECK ----------
def is_premium():
    pid = session.get("payment_id")
    if not pid:
        return False

    today = str(date.today())
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM premium_users WHERE payment_id=? AND expiry>=?",
        (pid, today)
    )
    row = cur.fetchone()
    db.close()
    return row is not None

# ---------- DAILY LIMIT ----------
def check_limit(ip):
    if is_premium():
        return True   # premium unlimited

    today = str(date.today())
    db = get_db()
    cur = db.cursor()

    cur.execute(
        "SELECT count FROM limit_usage WHERE ip=? AND date=?",
        (ip, today)
    )
    row = cur.fetchone()

    if row:
        if row[0] >= 3:
            db.close()
            return False
        cur.execute(
            "UPDATE limit_usage SET count=count+1 WHERE ip=? AND date=?",
            (ip, today)
        )
    else:
        cur.execute(
            "INSERT INTO limit_usage VALUES (?, ?, 1)",
            (ip, today)
        )

    db.commit()
    db.close()
    return True

# ---------- ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":

        user_ip = request.remote_addr

        if not check_limit(user_ip):
            return redirect("/premium?limit=over")

        # ✅ FILE CHECK
        if "image" not in request.files:
            return "No file selected"

        file = request.files["image"]
        if file.filename == "":
            return "Empty filename"

        convert_type = request.form.get("type")

        # ✅ SAFE filename
        filename = file.filename.replace(" ", "_")
        input_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(input_path)

        img = Image.open(input_path)
        name = filename.rsplit(".", 1)[0]

        output_path = None

        try:
            if convert_type == "jpg_to_png":
                output_path = os.path.join(OUTPUT_FOLDER, name + ".png")
                img.save(output_path)

            elif convert_type == "png_to_jpg":
                output_path = os.path.join(OUTPUT_FOLDER, name + ".jpg")
                img.convert("RGB").save(output_path)

            elif convert_type == "img_to_pdf":
                output_path = os.path.join(OUTPUT_FOLDER, name + ".pdf")
                img.convert("RGB").save(output_path, "PDF")

            else:
                return "Invalid conversion type"

        except Exception as e:
            return f"Image conversion failed: {e}"

        # ✅ FINAL FILE CHECK
        if not output_path or not os.path.exists(output_path):
            return "Output file not created"

        return send_file(output_path, as_attachment=True)

    return render_template("index.html")

      

@app.route("/premium")
def premium():
    order = client.order.create({
        "amount": 9900,   # ₹99
        "currency": "INR",
        "payment_capture": 1
    })
    return render_template(
        "premium.html",
        order=order,
        key=RAZORPAY_KEY_ID
    )

@app.route("/payment-success", methods=["POST"])
def payment_success():
    data = request.form

    try:
        client.utility.verify_payment_signature({
            'razorpay_order_id': data['razorpay_order_id'],
            'razorpay_payment_id': data['razorpay_payment_id'],
            'razorpay_signature': data['razorpay_signature']
        })
    except:
        return "Payment verification failed"

    expiry = str(date.today() + timedelta(days=30))

    db = get_db()
    db.execute(
        "INSERT INTO premium_users VALUES (?, ?)",
        (data['razorpay_payment_id'], expiry)
    )
    db.commit()
    db.close()

    session["payment_id"] = data['razorpay_payment_id']
    session.permanent = True

    return redirect("/")


@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/refund")
def refund():
    return render_template("refund.html")



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

