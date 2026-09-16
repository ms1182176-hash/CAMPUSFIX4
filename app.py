from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory
)

import sqlite3
import os
import secrets
import json
import urllib.request
import re

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__, template_folder="templates")

app.secret_key = "campusfix-hackathon-secret-key"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE = os.path.join(
    BASE_DIR,
    "database.db"
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


# =========================================================
# CONSTANTS
# =========================================================

CATEGORIES = [
    "Water Leakage",
    "AC / Fan Failure",
    "Electricity / Light",
    "Washroom",
    "Furniture",
    "Wi-Fi / Internet",
    "Classroom",
    "Cleanliness",
    "Canteen Issue",
    "Studio Equipment",
    "Projector / Smart Board",
    "Lift",
    "Door / Window",
    "Sound / Speaker",
    "Other Maintenance",
    "Other"
]


LOCATIONS = [
    "Canteen",
    "Library",
    "Ground Floor - Authority Area",
    "Basement 1 - BJMC Studio",
    "Basement 2 - Playground",
    "1st Floor",
    "2nd Floor",
    "3rd Floor",
    "4th Floor",
    "Other"
]


STATUSES = [
    "Submitted",
    "Acknowledged",
    "Assigned",
    "In Progress",
    "Resolved",
    "Rejected"
]


ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}


# =========================================================
# DATABASE
# =========================================================

def get_db():

    connection = sqlite3.connect(
        DATABASE
    )

    connection.row_factory = sqlite3.Row

    return connection


def current_time():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def allowed_file(filename):

    return (
        "."
        in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def initialize_database():

    connection = get_db()

    # -----------------------------------------------------
    # USERS TABLE
    # -----------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            password TEXT NOT NULL,

            role TEXT NOT NULL DEFAULT 'student',

            created_at TEXT NOT NULL

        )
    """)

    # -----------------------------------------------------
    # ISSUES TABLE
    # -----------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS issues (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            student_id INTEGER NOT NULL,

            category TEXT NOT NULL,

            location TEXT NOT NULL,

            room TEXT,

            description TEXT NOT NULL,

            photo TEXT,

            anonymous INTEGER DEFAULT 0,

            priority TEXT DEFAULT 'Medium',

            status TEXT DEFAULT 'Submitted',

            assigned_to TEXT,

            admin_note TEXT,

            created_at TEXT NOT NULL,

            updated_at TEXT NOT NULL,

            FOREIGN KEY(student_id)
            REFERENCES users(id)

        )
    """)

    # -----------------------------------------------------
    # DATABASE MIGRATION
    # -----------------------------------------------------

    columns = [
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    ]

    if "course" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN course TEXT"
        )

    if "semester" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN semester TEXT"
        )

    if "qr_token" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN qr_token TEXT"
        )

    # -----------------------------------------------------
    # HEALTH PROFILE COLUMNS
    # -----------------------------------------------------

    if "blood_group" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN blood_group TEXT"
        )

    if "allergies" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN allergies TEXT"
        )

    if "ongoing_treatment" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN ongoing_treatment TEXT"
        )

    if "emergency_notes" not in columns:

        connection.execute(
            "ALTER TABLE users ADD COLUMN emergency_notes TEXT"
        )

    # -----------------------------------------------------
    # CONTACT MESSAGES TABLE
    # -----------------------------------------------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            subject TEXT NOT NULL,

            message TEXT NOT NULL,

            created_at TEXT NOT NULL,

            FOREIGN KEY(user_id)
            REFERENCES users(id)

        )
    """)

    # -----------------------------------------------------
    # CREATE ADMIN
    # -----------------------------------------------------

    admin = connection.execute(
        """
        SELECT id
        FROM users
        WHERE email = ?
        """,
        ("admin@college.com",)
    ).fetchone()

    if admin is None:

        connection.execute("""
            INSERT INTO users
            (
                name,
                email,
                password,
                role,
                created_at
            )

            VALUES (?, ?, ?, ?, ?)

        """, (

            "College Authority",

            "admin@college.com",

            generate_password_hash(
                "admin123"
            ),

            "admin",

            current_time()

        ))

    # -----------------------------------------------------
    # CREATE DEMO STUDENT
    # -----------------------------------------------------

    student = connection.execute(
        """
        SELECT id
        FROM users
        WHERE email = ?
        """,
        ("student@college.com",)
    ).fetchone()

    if student is None:

        connection.execute("""
            INSERT INTO users
            (
                name,
                email,
                password,
                role,
                course,
                semester,
                qr_token,
                created_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            "Demo Student",

            "student@college.com",

            generate_password_hash(
                "student123"
            ),

            "student",

            "BCA",

            "1st Semester",

            secrets.token_urlsafe(32),

            current_time()

        ))

    # -----------------------------------------------------
    # GIVE QR TOKEN TO OLD STUDENTS
    # -----------------------------------------------------

    students_without_qr = connection.execute("""
        SELECT id
        FROM users
        WHERE role = 'student'
        AND (qr_token IS NULL OR qr_token = '')
    """).fetchall()

    for student in students_without_qr:

        connection.execute(
            """
            UPDATE users
            SET qr_token = ?
            WHERE id = ?
            """,
            (
                secrets.token_urlsafe(32),
                student["id"]
            )
        )

    connection.commit()

    connection.close()


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    if "user_id" in session:

        if session["role"] == "admin":

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    return render_template(
        "index.html"
    )


# =========================================================
# AUTHORITY PROFILES
# =========================================================

@app.route(
    "/authority/<int:authority_id>"
)
def authority(authority_id):

    authorities = {

        1: {
            "name": "Shri Sandeep Singh",
            "designation": "Chairman, Avviare Educational Hub",
            "role": "Chairman",
            "photo": "sandeep.jpg",

            "about": """
            Shri Sandeep Singh is the Chairman
            of Avviare Educational Hub. His leadership
            focuses on creating an educational environment
            that combines academic knowledge, values,
            practical learning and career development.
            """,

            "vision": """
            His vision focuses on helping students grow
            beyond academics by developing practical skills,
            confidence and a professional mindset for
            their future careers.
            """
        },

        2: {
            "name": "Mrs. Kanika Singh",
            "designation": "Managing Director, Avviare Educational Hub",
            "role": "Managing Director",
            "photo": "kanika.jpg",

            "about": """
            Mrs. Kanika Singh is the Managing Director
            of Avviare Educational Hub. She contributes
            to the institution's management and its focus
            on creating meaningful learning opportunities
            for students.
            """,

            "vision": """
            Her approach focuses on supporting students
            throughout their educational journey while
            creating opportunities for learning, growth
            and career development.
            """
        },

        3: {
            "name": "Mr. Amresh Kumar",
            "designation": "Executive Director, Avviare Educational Hub",
            "role": "Executive Director",
            "photo": "amresh.jpg",

            "about": """
            Mr. Amresh Kumar is the Executive Director
            of Avviare Educational Hub. He is involved
            in developing an environment that connects
            education with practical skills and
            real-world opportunities.
            """,

            "vision": """
            His vision focuses on helping learners build
            confidence, develop relevant skills and become
            prepared for the changing professional world.
            """
        }

    }

    selected_authority = authorities.get(
        authority_id
    )

    if selected_authority is None:

        return (
            "Authority not found",
            404
        )

    return render_template(
        "authority.html",
        authority=selected_authority
    )


# =========================================================
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        course = request.form.get(
            "course",
            ""
        )

        semester = request.form.get(
            "semester",
            ""
        )

        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not name:

            flash(
                "Please enter your name.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        if not email:

            flash(
                "Please enter your email.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        if len(password) < 6:

            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )

            return render_template(
                "register.html"
            )

        connection = get_db()

        try:

            qr_token = secrets.token_urlsafe(32)

            connection.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    role,
                    course,
                    semester,
                    qr_token,
                    created_at
                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            """, (

                name,

                email,

                generate_password_hash(
                    password
                ),

                "student",

                course,

                semester,

                qr_token,

                current_time()

            ))

            connection.commit()

            new_user = connection.execute(
                """
                SELECT id, qr_token
                FROM users
                WHERE email = ?
                """,
                (email,)
            ).fetchone()

            session["user_id"] = new_user["id"]

            session["name"] = name

            session["role"] = "student"

            session["qr_token"] = new_user["qr_token"]

            flash(
                "Account created successfully!",
                "success"
            )

            return redirect(
                url_for(
                    "my_qr"
                )
            )

        except sqlite3.IntegrityError:

            flash(
                "This email is already registered.",
                "danger"
            )

        finally:

            connection.close()

    return render_template(
        "register.html"
    )


# =========================================================
# LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        connection = get_db()

        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        connection.close()

        if user and check_password_hash(
            user["password"],
            password
        ):

            session["user_id"] = user["id"]

            session["name"] = user["name"]

            session["role"] = user["role"]

            session["qr_token"] = user["qr_token"]

            if user["role"] == "admin":

                return redirect(
                    url_for(
                        "admin_dashboard"
                    )
                )

            return redirect(
                url_for(
                    "student_dashboard"
                )
            )

        flash(
            "Invalid email or password.",
            "danger"
        )

    return render_template(
        "login.html"
    )


# =========================================================
# PERSONAL QR PAGE
# =========================================================

@app.route("/my-qr")
def my_qr():

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    if session["role"] != "student":

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    connection = get_db()

    user = connection.execute("""
        SELECT
            name,
            email,
            qr_token
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    connection.close()

    if user is None:

        flash(
            "Student account not found.",
            "danger"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    if not user["qr_token"]:

        flash(
            "QR login is not available.",
            "danger"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    qr_login_url = url_for(
        "qr_login",
        token=user["qr_token"],
        _external=True
    )

    return render_template(
        "my_qr.html",
        user=user,
        qr_login_url=qr_login_url
    )


# =========================================================
# QR LOGIN
# =========================================================

@app.route(
    "/qr-login/<token>"
)
def qr_login(token):

    connection = get_db()

    user = connection.execute("""
        SELECT
            id,
            name,
            role,
            qr_token
        FROM users
        WHERE qr_token = ?
    """, (
        token,
    )).fetchone()

    connection.close()

    if user is None:

        flash(
            "Invalid CampusFix QR.",
            "danger"
        )

        return redirect(
            url_for(
                "index"
            )
        )

    if user["role"] != "student":

        flash(
            "Invalid CampusFix QR.",
            "danger"
        )

        return redirect(
            url_for(
                "index"
            )
        )

    session["user_id"] = user["id"]

    session["name"] = user["name"]

    session["role"] = user["role"]

    session["qr_token"] = user["qr_token"]

    return redirect(
        url_for(
            "student_dashboard"
        )
    )


# =========================================================
# VOICE + AI COMPLAINT PARSER
# =========================================================

@app.route(
    "/voice-parse",
    methods=["POST"]
)
def voice_parse():

    if (
        "user_id" not in session
        or
        session["role"] != "student"
    ):

        return {
            "success": False,
            "message": "Please login first."
        }, 401

    data = request.get_json(
        silent=True
    ) or {}

    transcript = (
        data.get("transcript")
        or
        ""
    ).strip()

    if not transcript:

        return {
            "success": False,
            "message": "No voice text received."
        }, 400

    # -----------------------------------------------------
    # GEMINI AI
    # -----------------------------------------------------

    api_key = os.environ.get(
        "GEMINI_API_KEY",
        ""
    ).strip()

    model_name = os.environ.get(
        "GEMINI_MODEL",
        "gemini-2.5-flash"
    )

    if api_key:

        prompt = f"""
You are the CampusFix complaint assistant.

Convert the student's spoken complaint into JSON only.

Do not invent facts.

Allowed categories:
{", ".join(CATEGORIES)}

Allowed locations:
{", ".join(LOCATIONS)}

Choose the closest matching category and location.

If the location is not clear, use "Other".

Keep the description faithful to what the student said.

Priority must be High only for urgent problems such as:
fire, electric shock, sparking, short circuit,
dangerous electrical fault, flooding or major water leakage.

Otherwise use Medium.

Return exactly:

{{
    "category": "...",
    "location": "...",
    "room": "",
    "description": "...",
    "priority": "High or Medium"
}}

Student said:

{transcript}
"""

        try:

            endpoint = (
                "https://generativelanguage.googleapis.com/"
                "v1beta/models/"
                +
                model_name
                +
                ":generateContent?key="
                +
                api_key
            )

            payload = {

                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],

                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json"
                }

            }

            body = json.dumps(
                payload
            ).encode(
                "utf-8"
            )

            req = urllib.request.Request(

                endpoint,

                data=body,

                headers={
                    "Content-Type":
                    "application/json"
                },

                method="POST"

            )

            with urllib.request.urlopen(
                req,
                timeout=20
            ) as response:

                result = json.loads(
                    response.read().decode(
                        "utf-8"
                    )
                )

            ai_text = (
                result
                ["candidates"]
                [0]
                ["content"]
                ["parts"]
                [0]
                ["text"]
            )

            parsed = json.loads(
                ai_text
            )

            if parsed.get(
                "category"
            ) not in CATEGORIES:

                parsed["category"] = "Other"

            if parsed.get(
                "location"
            ) not in LOCATIONS:

                parsed["location"] = "Other"

            parsed["room"] = str(
                parsed.get(
                    "room"
                )
                or
                ""
            )

            parsed["description"] = str(
                parsed.get(
                    "description"
                )
                or
                transcript
            )

            parsed["priority"] = (
                "High"
                if parsed.get(
                    "priority"
                ) == "High"
                else
                "Medium"
            )

            return {

                "success": True,

                "ai": True,

                "data": parsed

            }

        except Exception:

            pass

    # -----------------------------------------------------
    # OFFLINE SMART FALLBACK
    # -----------------------------------------------------

    text = transcript.lower()

    category = "Other"

    category_words = {

        "Water Leakage": [
            "water",
            "leak",
            "leakage",
            "pipe",
            "tap"
        ],

        "AC / Fan Failure": [
            "ac",
            "air conditioner",
            "air conditioning",
            "fan",
            "cooler"
        ],

        "Electricity / Light": [
            "electric",
            "electricity",
            "light",
            "switch",
            "socket",
            "sparking",
            "wire"
        ],

        "Washroom": [
            "washroom",
            "toilet",
            "bathroom"
        ],

        "Furniture": [
            "chair",
            "table",
            "desk",
            "furniture",
            "bench"
        ],

        "Wi-Fi / Internet": [
            "wifi",
            "wi-fi",
            "internet",
            "network"
        ],

        "Classroom": [
            "classroom",
            "class room"
        ],

        "Cleanliness": [
            "dirty",
            "clean",
            "garbage",
            "dust",
            "cleanliness"
        ],

        "Canteen Issue": [
            "canteen",
            "food"
        ],

        "Projector / Smart Board": [
            "projector",
            "smart board"
        ],

        "Lift": [
            "lift",
            "elevator"
        ],

        "Door / Window": [
            "door",
            "window"
        ],

        "Sound / Speaker": [
            "speaker",
            "sound",
            "microphone",
            "mic"
        ]

    }

    for cat, words in category_words.items():

        if any(
            word in text
            for word in words
        ):

            category = cat

            break

    # -----------------------------------------------------
    # LOCATION
    # -----------------------------------------------------

    location = "Other"

    location_words = {

        "Canteen": [
            "canteen"
        ],

        "Library": [
            "library"
        ],

        "Ground Floor - Authority Area": [
            "ground floor",
            "authority area"
        ],

        "Basement 1 - BJMC Studio": [
            "basement 1",
            "bjmc studio"
        ],

        "Basement 2 - Playground": [
            "basement 2",
            "playground"
        ],

        "1st Floor": [
            "1st floor",
            "first floor"
        ],

        "2nd Floor": [
            "2nd floor",
            "second floor"
        ],

        "3rd Floor": [
            "3rd floor",
            "third floor"
        ],

        "4th Floor": [
            "4th floor",
            "fourth floor"
        ]

    }

    for loc, words in location_words.items():

        if any(
            word in text
            for word in words
        ):

            location = loc

            break

    # -----------------------------------------------------
    # ROOM NUMBER
    # -----------------------------------------------------

    room_match = re.search(
        r"(?:room|class|lab|room no\.?|room number)"
        r"\s*[-:#]?\s*(\d{2,4})",
        text
    )

    room = (
        room_match.group(1)
        if room_match
        else
        ""
    )

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    high_words = [

        "fire",
        "electric shock",
        "shock",
        "sparking",
        "short circuit",
        "flood",
        "major leakage",
        "dangerous"

    ]

    priority = (
        "High"
        if any(
            word in text
            for word in high_words
        )
        else
        "Medium"
    )

    return {

        "success": True,

        "ai": False,

        "data": {

            "category": category,

            "location": location,

            "room": room,

            "description": transcript,

            "priority": priority

        }

    }


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for(
            "index"
        )
    )


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/student")
def student_dashboard():

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    if session["role"] != "student":

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    connection = get_db()

    issues = connection.execute(
        """
        SELECT *
        FROM issues
        WHERE student_id = ?
        ORDER BY id DESC
        """,
        (
            session["user_id"],
        )
    ).fetchall()

    connection.close()

    return render_template(
        "student.html",
        issues=issues
    )


# =========================================================
# REPORT ISSUE
# =========================================================

@app.route(
    "/report",
    methods=["GET", "POST"]
)
def report_issue():

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    if session["role"] != "student":

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if request.method == "POST":

        category = request.form.get(
            "category",
            ""
        )

        location = request.form.get(
            "location",
            ""
        )

        room = request.form.get(
            "room",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        anonymous = (
            1
            if request.form.get(
                "anonymous"
            ) == "on"
            else
            0
        )

        photo = request.files.get(
            "photo"
        )

        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if (
            category not in CATEGORIES
            or
            location not in LOCATIONS
            or
            not description
        ):

            flash(
                "Please fill all required fields.",
                "danger"
            )

            return render_template(
                "report.html",
                categories=CATEGORIES,
                locations=LOCATIONS
            )

        # -------------------------------------------------
        # PHOTO
        # -------------------------------------------------

        filename = None

        if photo and photo.filename:

            if not allowed_file(
                photo.filename
            ):

                flash(
                    "Only PNG, JPG, JPEG and WEBP images are allowed.",
                    "danger"
                )

                return render_template(
                    "report.html",
                    categories=CATEGORIES,
                    locations=LOCATIONS
                )

            safe_name = secure_filename(
                photo.filename
            )

            filename = (
                datetime.now().strftime(
                    "%Y%m%d%H%M%S"
                )
                +
                "_"
                +
                str(
                    session["user_id"]
                )
                +
                "_"
                +
                safe_name
            )

            photo.save(
                os.path.join(
                    UPLOAD_FOLDER,
                    filename
                )
            )

        # -------------------------------------------------
        # PRIORITY
        # -------------------------------------------------

        combined_text = (
            category
            +
            " "
            +
            description
        ).lower()

        high_priority_words = [

            "leak",
            "water",
            "fire",
            "electric",
            "shock",
            "danger",
            "flood",
            "sparking",
            "short circuit"

        ]

        priority = "Medium"

        for word in high_priority_words:

            if word in combined_text:

                priority = "High"

                break

        # -------------------------------------------------
        # SAVE ISSUE
        # -------------------------------------------------

        connection = get_db()

        cursor = connection.execute("""
            INSERT INTO issues
            (
                student_id,
                category,
                location,
                room,
                description,
                photo,
                anonymous,
                priority,
                status,
                created_at,
                updated_at
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

        """, (

            session["user_id"],

            category,

            location,

            room,

            description,

            filename,

            anonymous,

            priority,

            "Submitted",

            current_time(),

            current_time()

        ))

        issue_id = cursor.lastrowid

        connection.commit()

        connection.close()

        flash(
            f"Issue #{issue_id} submitted successfully!",
            "success"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    return render_template(
        "report.html",
        categories=CATEGORIES,
        locations=LOCATIONS
    )


# =========================================================
# ISSUE DETAILS
# =========================================================

@app.route(
    "/issue/<int:issue_id>"
)
def issue_detail(issue_id):

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    connection = get_db()

    issue = connection.execute("""
        SELECT

            issues.*,

            users.name AS student_name,

            users.email AS student_email

        FROM issues

        JOIN users

        ON issues.student_id = users.id

        WHERE issues.id = ?

    """, (
        issue_id,
    )).fetchone()

    connection.close()

    if issue is None:

        flash(
            "Issue not found.",
            "danger"
        )

        return redirect(
            url_for(
                "index"
            )
        )

    if (
        session["role"] == "student"
        and
        issue["student_id"]
        !=
        session["user_id"]
    ):

        flash(
            "You cannot view this issue.",
            "danger"
        )

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    return render_template(
        "issue.html",
        issue=issue
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    if session["role"] != "admin":

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    status_filter = request.args.get(
        "status",
        "All"
    )

    priority_filter = request.args.get(
        "priority",
        "All"
    )

    connection = get_db()

    query = """
        SELECT

            issues.*,

            users.name AS student_name,

            users.email AS student_email

        FROM issues

        JOIN users

        ON issues.student_id = users.id

        WHERE 1 = 1
    """

    parameters = []

    if status_filter != "All":

        query += """
            AND issues.status = ?
        """

        parameters.append(
            status_filter
        )

    if priority_filter != "All":

        query += """
            AND issues.priority = ?
        """

        parameters.append(
            priority_filter
        )

    query += """
        ORDER BY

        CASE issues.priority

            WHEN 'High' THEN 1

            WHEN 'Medium' THEN 2

            ELSE 3

        END,

        issues.id DESC
    """

    issues = connection.execute(
        query,
        parameters
    ).fetchall()

    # -----------------------------------------------------
    # STATISTICS
    # -----------------------------------------------------

    total = connection.execute("""
        SELECT COUNT(*)
        FROM issues
    """).fetchone()[0]

    new = connection.execute("""
        SELECT COUNT(*)
        FROM issues
        WHERE status = 'Submitted'
    """).fetchone()[0]

    progress = connection.execute("""
        SELECT COUNT(*)
        FROM issues
        WHERE status IN
        (
            'Acknowledged',
            'Assigned',
            'In Progress'
        )
    """).fetchone()[0]

    resolved = connection.execute("""
        SELECT COUNT(*)
        FROM issues
        WHERE status = 'Resolved'
    """).fetchone()[0]

    high = connection.execute("""
        SELECT COUNT(*)
        FROM issues
        WHERE priority = 'High'
        AND status != 'Resolved'
    """).fetchone()[0]

    connection.close()

    stats = {

        "total": total,

        "new": new,

        "progress": progress,

        "resolved": resolved,

        "high": high

    }

    return render_template(
        "admin.html",

        issues=issues,

        stats=stats,

        statuses=STATUSES,

        status_filter=status_filter,

        priority_filter=priority_filter
    )


# =========================================================
# ADMIN UPDATE ISSUE
# =========================================================

@app.route(
    "/admin/update/<int:issue_id>",
    methods=["POST"]
)
def update_issue(issue_id):

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    if session["role"] != "admin":

        return redirect(
            url_for(
                "student_dashboard"
            )
        )

    status = request.form.get(
        "status"
    )

    assigned_to = request.form.get(
        "assigned_to",
        ""
    ).strip()

    admin_note = request.form.get(
        "admin_note",
        ""
    ).strip()

    if status not in STATUSES:

        flash(
            "Invalid status.",
            "danger"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    connection = get_db()

    connection.execute("""
        UPDATE issues

        SET

            status = ?,

            assigned_to = ?,

            admin_note = ?,

            updated_at = ?

        WHERE id = ?

    """, (

        status,

        assigned_to,

        admin_note,

        current_time(),

        issue_id

    ))

    connection.commit()

    connection.close()

    flash(
        f"Issue #{issue_id} updated successfully!",
        "success"
    )

    return redirect(
        request.referrer
        or
        url_for(
            "admin_dashboard"
        )
    )


# =========================================================
# HEALTH VAULT
# =========================================================

@app.route(
    "/health",
    methods=["GET", "POST"]
)
def health_vault():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if session["role"] != "student":

        return redirect(
            url_for("admin_dashboard")
        )

    connection = get_db()

    if request.method == "POST":

        blood_group = request.form.get(
            "blood_group",
            ""
        ).strip()

        allergies = request.form.get(
            "allergies",
            ""
        ).strip()

        ongoing_treatment = request.form.get(
            "ongoing_treatment",
            ""
        ).strip()

        emergency_notes = request.form.get(
            "emergency_notes",
            ""
        ).strip()

        connection.execute("""
            UPDATE users

            SET
                blood_group = ?,
                allergies = ?,
                ongoing_treatment = ?,
                emergency_notes = ?

            WHERE id = ?

        """, (

            blood_group,

            allergies,

            ongoing_treatment,

            emergency_notes,

            session["user_id"]

        ))

        connection.commit()

        flash(
            "Health information saved successfully.",
            "success"
        )

    user = connection.execute("""
        SELECT
            name,
            email,
            blood_group,
            allergies,
            ongoing_treatment,
            emergency_notes
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    connection.close()

    return render_template(
        "health.html",
        user=user
    )


# =========================================================
# ADMIN EMERGENCY HEALTH DIRECTORY
# =========================================================

@app.route("/admin/health")
def admin_health():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if session["role"] != "admin":

        return redirect(
            url_for("student_dashboard")
        )

    search = request.args.get(
        "search",
        ""
    ).strip()

    connection = get_db()

    if search:

        students = connection.execute("""
            SELECT
                id,
                name,
                email,
                blood_group,
                allergies,
                ongoing_treatment,
                emergency_notes
            FROM users
            WHERE role = 'student'
            AND (
                name LIKE ?
                OR email LIKE ?
            )
            ORDER BY name
        """, (
            "%" + search + "%",
            "%" + search + "%"
        )).fetchall()

    else:

        students = connection.execute("""
            SELECT
                id,
                name,
                email,
                blood_group,
                allergies,
                ongoing_treatment,
                emergency_notes
            FROM users
            WHERE role = 'student'
            ORDER BY name
        """).fetchall()

    connection.close()

    return render_template(
        "health_admin.html",
        students=students,
        search=search
    )


# =========================================================
# CONTACT US
# =========================================================

@app.route(
    "/contact",
    methods=["GET", "POST"]
)
def contact():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if request.method == "POST":

        subject = request.form.get(
            "subject",
            ""
        ).strip()

        message = request.form.get(
            "message",
            ""
        ).strip()

        if not subject or not message:

            flash(
                "Please enter both subject and message.",
                "danger"
            )

            return render_template(
                "contact.html"
            )

        connection = get_db()

        connection.execute("""
            INSERT INTO contact_messages
            (
                user_id,
                subject,
                message,
                created_at
            )

            VALUES (?, ?, ?, ?)

        """, (

            session["user_id"],

            subject,

            message,

            current_time()

        ))

        connection.commit()

        connection.close()

        flash(
            "Your message has been sent successfully!",
            "success"
        )

        if session["role"] == "admin":

            return redirect(
                url_for("admin_dashboard")
            )

        return redirect(
            url_for("student_dashboard")
        )

    return render_template(
        "contact.html"
    )


# =========================================================
# ADMIN CONTACT MESSAGES
# =========================================================

@app.route(
    "/admin/contact-messages"
)
def admin_contact_messages():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    if session["role"] != "admin":

        return redirect(
            url_for("student_dashboard")
        )

    connection = get_db()

    messages = connection.execute("""
        SELECT
            contact_messages.*,
            users.name AS student_name,
            users.email AS student_email
        FROM contact_messages
        JOIN users
        ON contact_messages.user_id = users.id
        ORDER BY contact_messages.id DESC
    """).fetchall()

    connection.close()

    return render_template(
        "contact_messages.html",
        messages=messages
    )


# =========================================================
# UPLOADED IMAGES
# =========================================================

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    if "user_id" not in session:

        return redirect(
            url_for(
                "login"
            )
        )

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# =========================================================
# START APPLICATION
# =========================================================
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
initialize_database()
if __name__ == '__main__':


    app.run(
        host='0.0.0.0',
        port=int(
            os.environ.get(
                "PORT",
                5000
            )
        ),
        debug=True
    )
