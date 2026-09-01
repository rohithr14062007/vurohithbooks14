import os
import random
import sqlite3
from datetime import timedelta

from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "books.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "rohith-books-secret-2026"),
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)



def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student',
                phone TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        default_categories = ["Story Books", "Lesson Books", "Mathematics Books", "Others"]
        for category_name in default_categories:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                (category_name,),
            )

        conn.execute(
            "DELETE FROM categories WHERE name NOT IN (?, ?, ?, ?)",
            ("Story Books", "Lesson Books", "Mathematics Books", "Others"),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                filename TEXT NOT NULL,
                original_name TEXT NOT NULL,
                author TEXT,
                description TEXT,
                category_id INTEGER,
                uploaded_by INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(category_id) REFERENCES categories(id),
                FOREIGN KEY(uploaded_by) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(book_id) REFERENCES books(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                rating INTEGER DEFAULT 0,
                comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(book_id) REFERENCES books(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                date_of_birth TEXT,
                gender TEXT,
                category TEXT,
                grade_division TEXT,
                fathers_name TEXT,
                mothers_name TEXT,
                phone1 TEXT,
                phone2 TEXT,
                emergency_contact TEXT,
                address TEXT,
                city TEXT,
                state TEXT,
                pincode TEXT,
                institution_name TEXT,
                blood_group TEXT,
                nationality TEXT,
                aadhaar_number TEXT,
                religion TEXT,
                parent_occupation TEXT,
                student_no TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )

        user_columns = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "role" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
        if "phone" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        if "is_admin" not in user_columns:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            "UPDATE users SET role = 'admin' WHERE is_admin = 1 AND (role IS NULL OR role = '')"
        )
        conn.execute(
            "UPDATE users SET role = 'student' WHERE is_admin = 0 AND (role IS NULL OR role = '')"
        )

        book_columns = [row[1] for row in conn.execute("PRAGMA table_info(books)").fetchall()]
        for column_name, column_sql in {
            "author": "ALTER TABLE books ADD COLUMN author TEXT",
            "description": "ALTER TABLE books ADD COLUMN description TEXT",
            "category_id": "ALTER TABLE books ADD COLUMN category_id INTEGER",
        }.items():
            if column_name not in book_columns:
                conn.execute(column_sql)

        default_category_id = conn.execute(
            "SELECT id FROM categories WHERE name = 'Others' LIMIT 1"
        ).fetchone()
        if default_category_id:
            conn.execute(
                "UPDATE books SET category_id = ? WHERE category_id IS NULL",
                (default_category_id["id"],),
            )
            conn.execute(
                "UPDATE books SET category_id = ? WHERE category_id NOT IN (SELECT id FROM categories)",
                (default_category_id["id"],),
            )

        student_columns = [row[1] for row in conn.execute("PRAGMA table_info(student_entries)").fetchall()]
        for column_name in [
            "email",
            "date_of_birth",
            "gender",
            "category",
            "city",
            "state",
            "pincode",
            "institution_name",
            "emergency_contact",
            "blood_group",
            "nationality",
            "aadhaar_number",
            "religion",
            "parent_occupation",
        ]:
            if column_name not in student_columns:
                conn.execute(f"ALTER TABLE student_entries ADD COLUMN {column_name} TEXT")

        legacy_student_fields = {"gender", "category", "grade_division", "city", "state"}
        if legacy_student_fields.intersection(student_columns):
            existing_student_columns = [row[1] for row in conn.execute("PRAGMA table_info(student_entries)").fetchall()]
            legacy_table_name = "student_entries_legacy"
            conn.execute(f"ALTER TABLE student_entries RENAME TO {legacy_table_name}")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS student_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT,
                    date_of_birth TEXT,
                    fathers_name TEXT,
                    mothers_name TEXT,
                    phone1 TEXT,
                    phone2 TEXT,
                    emergency_contact TEXT,
                    address TEXT,
                    pincode TEXT,
                    institution_name TEXT,
                    blood_group TEXT,
                    nationality TEXT,
                    aadhaar_number TEXT,
                    religion TEXT,
                    parent_occupation TEXT,
                    student_no TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )

            target_columns = [
                "id",
                "user_id",
                "name",
                "email",
                "date_of_birth",
                "fathers_name",
                "mothers_name",
                "phone1",
                "phone2",
                "emergency_contact",
                "address",
                "pincode",
                "institution_name",
                "blood_group",
                "nationality",
                "aadhaar_number",
                "religion",
                "parent_occupation",
                "student_no",
                "created_at",
            ]
            available_columns = [col for col in target_columns if col in existing_student_columns]
            if available_columns:
                insert_columns = ", ".join(available_columns)
                source_sql = f"INSERT INTO student_entries ({insert_columns}) SELECT {insert_columns} FROM {legacy_table_name}"
                conn.execute(source_sql)
            conn.execute(f"DROP TABLE {legacy_table_name}")

        admin_exists = conn.execute(
            "SELECT id FROM users WHERE username = ? LIMIT 1",
            ("admin",),
        ).fetchone()
        if not admin_exists:
            conn.execute(
                "INSERT INTO users (name, email, username, password_hash, role, phone, is_admin) VALUES (?, ?, ?, ?, ?, ?, 1)",
                ("Administrator", "admin@books.local", "admin", generate_password_hash("admin123"), "admin", "0000000000"),
            )


@app.before_request
def setup_session_and_db():
    init_db()
    if "user_id" in session:
        session.permanent = True


def get_user_by_id(user_id):
    if not user_id:
        return None
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(username):
    with get_db() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_role(user):
    if not user:
        return "student"
    if user["is_admin"]:
        return "admin"
    role = (user["role"] or "student").strip().lower()
    return role if role in {"student", "other"} else "student"


def conn_total(query, params=()):
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
        if row is None:
            return 0
        return row[0] if isinstance(row, tuple) else next(iter(row))


def get_categories():
    with get_db() as conn:
        return conn.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()


def get_books(search=None, category_id=None):
    with get_db() as conn:
        query = """
            SELECT b.*, u.username AS uploader, c.name AS category_name
            FROM books b
            LEFT JOIN users u ON u.id = b.uploaded_by
            LEFT JOIN categories c ON c.id = b.category_id
        """
        filters = []
        params = []

        if search:
            search_term = f"%{search.strip().lower()}%"
            filters.append("(LOWER(b.title) LIKE ? OR LOWER(COALESCE(b.author, '')) LIKE ?)")
            params.extend([search_term, search_term])

        if category_id:
            filters.append("b.category_id = ?")
            params.append(category_id)

        if filters:
            query += " WHERE " + " AND ".join(filters)

        query += " ORDER BY b.uploaded_at DESC, b.id DESC"
        return conn.execute(query, params).fetchall()


def get_book_by_id(book_id):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT b.*, u.username AS uploader, c.name AS category_name
            FROM books b
            LEFT JOIN users u ON u.id = b.uploaded_by
            LEFT JOIN categories c ON c.id = b.category_id
            WHERE b.id = ?
            """,
            (book_id,),
        ).fetchone()


def get_users():
    with get_db() as conn:
        return conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()


def get_download_history(user_id=None):
    with get_db() as conn:
        query = """
            SELECT d.id, d.downloaded_at, b.id AS book_id, b.title AS book_title, b.author,
                   u.id AS user_id, u.username, c.name AS category_name
            FROM download_history d
            JOIN books b ON b.id = d.book_id
            LEFT JOIN users u ON u.id = d.user_id
            LEFT JOIN categories c ON c.id = b.category_id
        """
        params = []
        if user_id:
            query += " WHERE d.user_id = ?"
            params.append(user_id)
        query += " ORDER BY d.downloaded_at DESC"
        return conn.execute(query, params).fetchall()


def get_recent_activity(limit=8):
    with get_db() as conn:
        activity = []

        for row in conn.execute(
            "SELECT 'user' AS kind, name AS label, created_at AS created_at FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall():
            activity.append({
                "kind": row["kind"],
                "label": f"New user: {row['label']}",
                "created_at": row["created_at"],
            })

        for row in conn.execute(
            "SELECT 'book' AS kind, title AS label, uploaded_at AS created_at FROM books ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall():
            activity.append({
                "kind": row["kind"],
                "label": f"New book: {row['label']}",
                "created_at": row["created_at"],
            })

        for row in conn.execute(
            """
            SELECT 'download' AS kind, b.title AS label, d.downloaded_at AS created_at
            FROM download_history d
            JOIN books b ON b.id = d.book_id
            ORDER BY d.downloaded_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall():
            activity.append({
                "kind": row["kind"],
                "label": f"Downloaded: {row['label']}",
                "created_at": row["created_at"],
            })

        for row in conn.execute(
            """
            SELECT 'review' AS kind, b.title AS label, r.created_at AS created_at
            FROM reviews r
            JOIN books b ON b.id = r.book_id
            ORDER BY r.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall():
            activity.append({
                "kind": row["kind"],
                "label": f"Review: {row['label']}",
                "created_at": row["created_at"],
            })

        activity.sort(key=lambda item: item["created_at"], reverse=True)
        return activity[:limit]


def get_student_entries():
    with get_db() as conn:
        return conn.execute(
            """
            SELECT
                s.id,
                s.name,
                u.username,
                s.email,
                COALESCE(NULLIF(s.phone1, ''), u.phone) AS phone,
                s.institution_name AS institution,
                s.student_no AS student_id,
                u.role
            FROM student_entries s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.id DESC
            """
        ).fetchall()


@app.route("/")
def home():
    user = get_user_by_id(session.get("user_id"))
    if user and user["is_admin"]:
        return redirect(url_for("admin_dashboard"))

    search_term = request.args.get("q", "", type=str).strip()
    selected_category_id = request.args.get("category_id", "", type=int)
    books = get_books(search=search_term, category_id=selected_category_id)
    student_entry = None
    if user and not user["is_admin"]:
        with get_db() as conn:
            student_entry = conn.execute("SELECT * FROM student_entries WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()

    return render_template(
        "index.html",
        current_user=user,
        logged_in=bool(user),
        owner_logged=bool(user and user["is_admin"]),
        books=books,
        student_entry=student_entry,
        categories=get_categories(),
        selected_category_id=selected_category_id,
        search_term=search_term,
    )


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Invalid username or password.", "error")
        return redirect(url_for("home"))

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    role = get_user_role(user)
    session["role"] = role
    session["logged_in"] = True
    session["is_admin"] = bool(user["is_admin"])
    flash("Login successful.", "success")
    if user["is_admin"]:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("home"))


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    username = request.form.get("username", "").strip()
    phone = request.form.get("phone", "").strip()
    role = request.form.get("role", "student").strip().lower()
    password = request.form.get("password", "").strip()

    if not all([name, email, username, password]):
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("home"))

    if role not in {"student", "other"}:
        role = "student"

    if get_user_by_username(username):
        flash("This username is already taken.", "error")
        return redirect(url_for("home"))

    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO users (name, email, username, password_hash, role, phone) VALUES (?, ?, ?, ?, ?, ?)",
                (name, email, username, generate_password_hash(password), role, phone or None),
            )
        except sqlite3.IntegrityError:
            flash("A user with that email already exists.", "error")
            return redirect(url_for("home"))

    user = get_user_by_username(username)
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = get_user_role(user)
    session["logged_in"] = True
    session["is_admin"] = bool(user["is_admin"])
    flash("Registration successful! You can now download books.", "success")
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/settings")
def settings_page():
    if not session.get("user_id"):
        flash("Please log in to access your settings.", "error")
        return redirect(url_for("home"))

    return render_template(
        "settings.html",
        current_user=get_user_by_id(session.get("user_id")),
        logged_in=True,
        owner_logged=bool(session.get("is_admin")),
    )


@app.route("/settings/change-password", methods=["POST"])
def change_password():
    if not session.get("user_id"):
        flash("Please log in to change your password.", "error")
        return redirect(url_for("home"))

    current_password = request.form.get("current_password", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not current_password or not new_password or not confirm_password:
        flash("Please fill in all password fields.", "error")
        return redirect(url_for("settings_page"))

    if new_password != confirm_password:
        flash("New password and confirmation password do not match.", "error")
        return redirect(url_for("settings_page"))

    if len(new_password) < 6:
        flash("New password must be at least 6 characters long.", "error")
        return redirect(url_for("settings_page"))

    user = get_user_by_id(session["user_id"])
    if not user or not check_password_hash(user["password_hash"], current_password):
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("settings_page"))

    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(new_password), session["user_id"]),
        )

    flash("Your password was changed successfully.", "success")
    return redirect(url_for("settings_page"))


@app.route("/settings/delete-account", methods=["POST"])
def delete_account():
    if not session.get("user_id"):
        flash("Please log in to delete your account.", "error")
        return redirect(url_for("home"))

    password = request.form.get("delete_password", "").strip()
    confirm_delete = request.form.get("confirm_delete", "").strip().lower() in {"on", "true", "1", "yes"}

    user = get_user_by_id(session["user_id"])
    if not user or not check_password_hash(user["password_hash"], password):
        flash("Your password is required to delete your account.", "error")
        return redirect(url_for("settings_page"))

    if not confirm_delete:
        flash("Please confirm that you want to permanently delete your account.", "error")
        return redirect(url_for("settings_page"))

    user_id = session["user_id"]
    with get_db() as conn:
        uploaded_books = conn.execute(
            "SELECT id, filename FROM books WHERE uploaded_by = ?",
            (user_id,),
        ).fetchall()

        uploaded_book_ids = [book["id"] for book in uploaded_books]
        if uploaded_book_ids:
            placeholders = ", ".join("?" for _ in uploaded_book_ids)
            conn.execute(f"DELETE FROM reviews WHERE book_id IN ({placeholders})", tuple(uploaded_book_ids))
            conn.execute(f"DELETE FROM download_history WHERE book_id IN ({placeholders})", tuple(uploaded_book_ids))

            for book in uploaded_books:
                file_path = os.path.join(UPLOAD_FOLDER, book["filename"])
                if os.path.exists(file_path):
                    os.remove(file_path)

            conn.execute("DELETE FROM books WHERE uploaded_by = ?", (user_id,))

        conn.execute("DELETE FROM reviews WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM download_history WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM student_entries WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    session.clear()
    flash("Your account and related data were permanently deleted.", "success")
    return redirect(url_for("home"))


@app.route("/submit-details", methods=["POST"])
def submit_details():
    if not session.get("logged_in") or session.get("is_admin"):
        flash("Only students or other users can submit details.", "error")
        return redirect(url_for("home"))

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    date_of_birth = request.form.get("date_of_birth", "").strip()
    fathers_name = request.form.get("fathers_name", "").strip()
    mothers_name = request.form.get("mothers_name", "").strip()
    phone1 = request.form.get("phone1", "").strip()
    phone2 = request.form.get("phone2", "").strip()
    emergency_contact = request.form.get("emergency_contact", "").strip()
    address = request.form.get("address", "").strip()
    pincode = request.form.get("pincode", "").strip()
    institution_name = request.form.get("institution_name", "").strip()
    blood_group = request.form.get("blood_group", "").strip()
    nationality = request.form.get("nationality", "").strip()
    aadhaar_number = request.form.get("aadhaar_number", "").strip()
    religion = request.form.get("religion", "").strip()
    parent_occupation = request.form.get("parent_occupation", "").strip()

    if not all([name, phone1, address]):
        flash("Name, phone number and address are required.", "error")
        return redirect(url_for("home"))

    student_no = str(random.randint(100000, 999999))

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO student_entries (
                user_id, name, email, date_of_birth,
                fathers_name, mothers_name, phone1, phone2,
                emergency_contact, address, pincode, institution_name,
                blood_group, nationality, aadhaar_number, religion, parent_occupation, student_no
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                name,
                email,
                date_of_birth,
                fathers_name,
                mothers_name,
                phone1,
                phone2,
                emergency_contact,
                address,
                pincode,
                institution_name,
                blood_group,
                nationality,
                aadhaar_number,
                religion,
                parent_occupation,
                student_no,
            ),
        )

    flash("Your details were saved successfully.", "success")
    return redirect(url_for("home"))


@app.route("/upload", methods=["POST"])
def upload_file():
    if not session.get("is_admin"):
        flash("Only the admin can upload books.", "error")
        return redirect(url_for("home"))

    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    description = request.form.get("description", "").strip()
    category_id = request.form.get("category_id", "", type=int)
    uploaded = request.files.get("file")
    if not uploaded or uploaded.filename == "":
        flash("Please choose a file to upload.", "error")
        return redirect(url_for("home"))

    original_name = uploaded.filename
    safe_name = secure_filename(original_name)
    if not safe_name:
        flash("Invalid file name.", "error")
        return redirect(url_for("home"))

    filename = f"{len(os.listdir(UPLOAD_FOLDER)) + 1}_{safe_name}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    uploaded.save(file_path)

    with get_db() as conn:
        existing_category = conn.execute(
            "SELECT id FROM categories WHERE id = ? LIMIT 1",
            (category_id,),
        ).fetchone()
        if not existing_category:
            category_id = conn.execute(
                "SELECT id FROM categories WHERE name = 'Others' LIMIT 1"
            ).fetchone()["id"]

        conn.execute(
            "INSERT INTO books (title, filename, original_name, author, description, category_id, uploaded_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                title or os.path.splitext(original_name)[0],
                filename,
                original_name,
                author or "Unknown Author",
                description or "No description available.",
                category_id,
                session["user_id"],
            ),
        )

    flash(f"{title or original_name} uploaded successfully!", "success")
    return redirect(url_for("home"))


@app.route("/book/<int:book_id>")
def book_details(book_id):
    book = get_book_by_id(book_id)
    if not book:
        flash("Book not found.", "error")
        return redirect(url_for("home"))

    return render_template(
        "book_details.html",
        book=book,
        current_user=get_user_by_id(session.get("user_id")),
        logged_in=bool(session.get("user_id")),
    )


@app.route("/admin")
def admin_dashboard():
    if not session.get("is_admin"):
        flash("You need admin access to view the dashboard.", "error")
        return redirect(url_for("home"))

    stats = {
        "total_users": len(get_users()),
        "total_books": len(get_books()),
        "total_categories": len(get_categories()),
        "total_downloads": conn_total("SELECT COUNT(*) FROM download_history"),
        "total_reviews": conn_total("SELECT COUNT(*) FROM reviews"),
    }

    return render_template(
        "admin.html",
        books=get_books(),
        users=get_users(),
        student_entries=get_student_entries(),
        current_user=get_user_by_id(session.get("user_id")),
        categories=get_categories(),
        stats=stats,
        recent_activity=get_recent_activity(),
    )


@app.route("/delete-book/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    if not session.get("is_admin"):
        flash("Only the admin can remove books.", "error")
        return redirect(url_for("home"))

    with get_db() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if book:
            file_path = os.path.join(UPLOAD_FOLDER, book["filename"])
            if os.path.exists(file_path):
                os.remove(file_path)
            conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
            flash(f"{book['title']} was removed.", "success")

    return redirect(url_for("admin_dashboard"))


@app.route("/download/<int:book_id>")
def download_book(book_id):
    if not session.get("user_id"):
        flash("Please log in to download books.", "error")
        return redirect(url_for("home"))

    with get_db() as conn:
        book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("home"))

        conn.execute(
            "INSERT INTO download_history (user_id, book_id) VALUES (?, ?)",
            (session["user_id"], book_id),
        )

    return send_from_directory(UPLOAD_FOLDER, book["filename"], as_attachment=True)


@app.route("/my-downloads")
def my_downloads():
    if not session.get("user_id"):
        flash("Please log in to view your download history.", "error")
        return redirect(url_for("home"))

    return render_template(
        "my_downloads.html",
        downloads=get_download_history(user_id=session["user_id"]),
        current_user=get_user_by_id(session.get("user_id")),
        logged_in=True,
    )


@app.route("/uploads/<path:filename>")
def served_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=2111)
