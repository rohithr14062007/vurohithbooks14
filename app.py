import os
import random
from datetime import timedelta
from dotenv import load_dotenv

from flask import Flask, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

# Load environment variables from supabase.env
load_dotenv('supabase.env')

app = Flask(__name__)

# Initialize Supabase client
try:
    from supabase import create_client
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")
    if SUPABASE_URL and SUPABASE_SECRET_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    else:
        raise ValueError("Supabase credentials not found in environment")
except Exception as e:
    print(f"Error: Could not initialize Supabase: {e}")
    supabase = None

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
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


def init_db():
    """Ensure default categories exist in Supabase."""
    if not supabase:
        return
    
    default_categories = ["Story Books", "Lesson Books", "Mathematics Books", "Others"]
    try:
        # Check and insert missing categories
        existing = supabase.table("categories").select("name").execute()
        existing_names = {row["name"] for row in existing.data}
        
        for cat_name in default_categories:
            if cat_name not in existing_names:
                supabase.table("categories").insert({"name": cat_name}).execute()
        
        # Ensure admin user exists
        admin_check = supabase.table("users").select("id").eq("username", "admin").execute()
        if not admin_check.data:
            supabase.table("users").insert({
                "name": "Administrator",
                "email": "admin@books.local",
                "username": "admin",
                "password_hash": generate_password_hash("admin123"),
                "role": "admin",
                "phone": "0000000000",
                "is_admin": True
            }).execute()
    except Exception as e:
        print(f"Warning: Could not initialize database: {e}")


@app.before_request
def setup_session_and_db():
    init_db()
    if "user_id" in session:
        session.permanent = True


def get_user_by_id(user_id):
    if not user_id or not supabase:
        return None
    try:
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error getting user by ID: {e}")
        return None


def get_user_by_username(username):
    if not supabase:
        return None
    try:
        response = supabase.table("users").select("*").eq("username", username).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error getting user by username: {e}")
        return None


def get_user_role(user):
    if not user:
        return "student"
    if user.get("is_admin"):
        return "admin"
    role = (user.get("role") or "student").strip().lower()
    return role if role in {"student", "other"} else "student"


def conn_total(query_type, **kwargs):
    """Get count from Supabase tables."""
    if not supabase:
        return 0
    try:
        if query_type == "downloads":
            response = supabase.table("download_history").select("id", count="exact").execute()
            return response.count if hasattr(response, 'count') else len(response.data or [])
        elif query_type == "reviews":
            response = supabase.table("reviews").select("id", count="exact").execute()
            return response.count if hasattr(response, 'count') else len(response.data or [])
        return 0
    except Exception as e:
        print(f"Error getting count: {e}")
        return 0


def get_categories():
    if not supabase:
        return []
    try:
        response = supabase.table("categories").select("*").order("name").execute()
        return response.data or []
    except Exception as e:
        print(f"Error getting categories: {e}")
        return []


def get_books(search=None, category_id=None):
    if not supabase:
        return []
    try:
        query = supabase.table("books").select("*, users(username), categories(name)")
        
        if search:
            search_lower = search.strip().lower()
            query = query.or_(f"title.ilike.%{search_lower}%,author.ilike.%{search_lower}%")
        
        if category_id:
            query = query.eq("category_id", category_id)
        
        response = query.order("uploaded_at", desc=True).order("id", desc=True).execute()
        
        # Transform response to match expected format
        books = []
        for book in response.data or []:
            book_item = dict(book)
            book_item["uploader"] = book.get("users", {}).get("username", "Unknown") if isinstance(book.get("users"), dict) else "Unknown"
            book_item["category_name"] = book.get("categories", {}).get("name", "Others") if isinstance(book.get("categories"), dict) else "Others"
            books.append(book_item)
        
        return books
    except Exception as e:
        print(f"Error getting books: {e}")
        return []


def get_book_by_id(book_id):
    if not supabase:
        return None
    try:
        response = supabase.table("books").select("*, users(username), categories(name)").eq("id", book_id).execute()
        if not response.data:
            return None
        book = response.data[0]
        book["uploader"] = book.get("users", {}).get("username", "Unknown") if isinstance(book.get("users"), dict) else "Unknown"
        book["category_name"] = book.get("categories", {}).get("name", "Others") if isinstance(book.get("categories"), dict) else "Others"
        return book
    except Exception as e:
        print(f"Error getting book: {e}")
        return None


def get_users():
    if not supabase:
        return []
    try:
        response = supabase.table("users").select("*").order("id", desc=True).execute()
        return response.data or []
    except Exception as e:
        print(f"Error getting users: {e}")
        return []


def get_download_history(user_id=None):
    if not supabase:
        return []
    try:
        query = supabase.table("download_history").select("*, books(id, title, author), users(id, username), categories(name)")
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.order("downloaded_at", desc=True).execute()
        
        # Transform response to match expected format
        downloads = []
        for dl in response.data or []:
            dl_item = {
                "id": dl.get("id"),
                "downloaded_at": dl.get("downloaded_at"),
                "book_id": dl.get("books", {}).get("id"),
                "book_title": dl.get("books", {}).get("title", "Unknown"),
                "author": dl.get("books", {}).get("author", "Unknown"),
                "user_id": dl.get("users", {}).get("id"),
                "username": dl.get("users", {}).get("username", "Unknown"),
                "category_name": dl.get("categories", {}).get("name", "Others") if isinstance(dl.get("categories"), dict) else "Others",
            }
            downloads.append(dl_item)
        
        return downloads
    except Exception as e:
        print(f"Error getting download history: {e}")
        return []


def get_recent_activity(limit=8):
    if not supabase:
        return []
    
    activity = []
    
    try:
        # Recent users
        users = supabase.table("users").select("name, created_at").order("created_at", desc=True).limit(limit).execute()
        for user in users.data or []:
            activity.append({
                "kind": "user",
                "label": f"New user: {user['name']}",
                "created_at": user.get("created_at"),
            })
        
        # Recent books
        books = supabase.table("books").select("title, uploaded_at").order("uploaded_at", desc=True).limit(limit).execute()
        for book in books.data or []:
            activity.append({
                "kind": "book",
                "label": f"New book: {book['title']}",
                "created_at": book.get("uploaded_at"),
            })
        
        # Recent downloads
        downloads = supabase.table("download_history").select("*, books(title)").order("downloaded_at", desc=True).limit(limit).execute()
        for dl in downloads.data or []:
            activity.append({
                "kind": "download",
                "label": f"Downloaded: {dl.get('books', {}).get('title', 'Unknown')}",
                "created_at": dl.get("downloaded_at"),
            })
        
        # Recent reviews
        reviews = supabase.table("reviews").select("*, books(title)").order("created_at", desc=True).limit(limit).execute()
        for review in reviews.data or []:
            activity.append({
                "kind": "review",
                "label": f"Review: {review.get('books', {}).get('title', 'Unknown')}",
                "created_at": review.get("created_at"),
            })
        
        activity.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return activity[:limit]
    except Exception as e:
        print(f"Error getting recent activity: {e}")
        return []


def get_student_entries():
    if not supabase:
        return []
    try:
        response = supabase.table("student_entries").select("*, users(username, phone, role)").order("id", desc=True).execute()
        
        entries = []
        for entry in response.data or []:
            user_data = entry.get("users", {}) if isinstance(entry.get("users"), dict) else {}
            entry_item = {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "username": user_data.get("username", "Unknown"),
                "email": entry.get("email"),
                "phone": entry.get("phone1") or user_data.get("phone", ""),
                "institution": entry.get("institution_name"),
                "student_id": entry.get("student_no"),
                "role": user_data.get("role", "student"),
            }
            entries.append(entry_item)
        
        return entries
    except Exception as e:
        print(f"Error getting student entries: {e}")
        return []


@app.route("/")
def home():
    user = get_user_by_id(session.get("user_id"))
    if user and user.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    search_term = request.args.get("q", "", type=str).strip()
    selected_category_id = request.args.get("category_id", "", type=int) or None
    books = get_books(search=search_term, category_id=selected_category_id)
    student_entry = None
    
    if user and not user.get("is_admin"):
        try:
            response = supabase.table("student_entries").select("*").eq("user_id", user["id"]).order("id", desc=True).limit(1).execute()
            student_entry = response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting student entry: {e}")

    return render_template(
        "index.html",
        current_user=user,
        logged_in=bool(user),
        owner_logged=bool(user and user.get("is_admin")),
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
    session["is_admin"] = bool(user.get("is_admin"))
    flash("Login successful.", "success")
    if user.get("is_admin"):
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

    if not supabase:
        flash("Database error. Please try again later.", "error")
        return redirect(url_for("home"))
    
    try:
        supabase.table("users").insert({
            "name": name,
            "email": email,
            "username": username,
            "password_hash": generate_password_hash(password),
            "role": role,
            "phone": phone or None,
        }).execute()
    except Exception as e:
        if "duplicate" in str(e).lower():
            flash("A user with that email already exists.", "error")
        else:
            flash(f"Registration error: {e}", "error")
        return redirect(url_for("home"))

    user = get_user_by_username(username)
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = get_user_role(user)
    session["logged_in"] = True
    session["is_admin"] = bool(user.get("is_admin"))
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

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("settings_page"))
    
    try:
        supabase.table("users").update({
            "password_hash": generate_password_hash(new_password)
        }).eq("id", session["user_id"]).execute()
        flash("Your password was changed successfully.", "success")
    except Exception as e:
        flash(f"Error changing password: {e}", "error")
    
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

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("settings_page"))
    
    user_id = session["user_id"]
    
    try:
        # Get uploaded books
        uploaded_books = supabase.table("books").select("id, filename").eq("uploaded_by", user_id).execute()
        uploaded_book_ids = [book["id"] for book in uploaded_books.data or []]
        
        # Delete reviews and downloads for uploaded books
        if uploaded_book_ids:
            for book_id in uploaded_book_ids:
                supabase.table("reviews").delete().eq("book_id", book_id).execute()
                supabase.table("download_history").delete().eq("book_id", book_id).execute()
            
            # Delete uploaded book files
            for book in uploaded_books.data or []:
                file_path = os.path.join(UPLOAD_FOLDER, book["filename"])
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            # Delete books
            supabase.table("books").delete().eq("uploaded_by", user_id).execute()
        
        # Delete user data
        supabase.table("reviews").delete().eq("user_id", user_id).execute()
        supabase.table("download_history").delete().eq("user_id", user_id).execute()
        supabase.table("student_entries").delete().eq("user_id", user_id).execute()
        supabase.table("users").delete().eq("id", user_id).execute()
        
        session.clear()
        flash("Your account and related data were permanently deleted.", "success")
    except Exception as e:
        flash(f"Error deleting account: {e}", "error")
    
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

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("home"))

    student_no = str(random.randint(100000, 999999))

    try:
        supabase.table("student_entries").insert({
            "user_id": session["user_id"],
            "name": name,
            "email": email,
            "date_of_birth": date_of_birth,
            "fathers_name": fathers_name,
            "mothers_name": mothers_name,
            "phone1": phone1,
            "phone2": phone2,
            "emergency_contact": emergency_contact,
            "address": address,
            "pincode": pincode,
            "institution_name": institution_name,
            "blood_group": blood_group,
            "nationality": nationality,
            "aadhaar_number": aadhaar_number,
            "religion": religion,
            "parent_occupation": parent_occupation,
            "student_no": student_no,
        }).execute()
        flash("Your details were saved successfully.", "success")
    except Exception as e:
        flash(f"Error saving details: {e}", "error")
    
    return redirect(url_for("home"))


@app.route("/upload", methods=["POST"])
def upload_file():
    if not session.get("is_admin"):
        flash("Only the admin can upload books.", "error")
        return redirect(url_for("home"))

    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    description = request.form.get("description", "").strip()
    category_id = request.form.get("category_id", "", type=int) or None
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

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("home"))

    try:
        # Verify category exists, default to Others if not
        if category_id:
            existing_category = supabase.table("categories").select("id").eq("id", category_id).execute()
            if not existing_category.data:
                others = supabase.table("categories").select("id").eq("name", "Others").execute()
                category_id = others.data[0]["id"] if others.data else None
        else:
            others = supabase.table("categories").select("id").eq("name", "Others").execute()
            category_id = others.data[0]["id"] if others.data else None
        
        supabase.table("books").insert({
            "title": title or os.path.splitext(original_name)[0],
            "filename": filename,
            "original_name": original_name,
            "author": author or "Unknown Author",
            "description": description or "No description available.",
            "category_id": category_id,
            "uploaded_by": session["user_id"],
        }).execute()
        
        flash(f"{title or original_name} uploaded successfully!", "success")
    except Exception as e:
        flash(f"Error uploading book: {e}", "error")
    
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
        "total_downloads": conn_total("downloads"),
        "total_reviews": conn_total("reviews"),
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

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("admin_dashboard"))

    try:
        book = supabase.table("books").select("*").eq("id", book_id).execute()
        if book.data:
            book_data = book.data[0]
            file_path = os.path.join(UPLOAD_FOLDER, book_data["filename"])
            if os.path.exists(file_path):
                os.remove(file_path)
            
            supabase.table("books").delete().eq("id", book_id).execute()
            flash(f"{book_data['title']} was removed.", "success")
        else:
            flash("Book not found.", "error")
    except Exception as e:
        flash(f"Error deleting book: {e}", "error")

    return redirect(url_for("admin_dashboard"))


@app.route("/download/<int:book_id>")
def download_book(book_id):
    if not session.get("user_id"):
        flash("Please log in to download books.", "error")
        return redirect(url_for("home"))

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("home"))

    try:
        book = supabase.table("books").select("*").eq("id", book_id).execute()
        if not book.data:
            flash("Book not found.", "error")
            return redirect(url_for("home"))
        
        book_data = book.data[0]
        
        # Record download
        supabase.table("download_history").insert({
            "user_id": session["user_id"],
            "book_id": book_id,
        }).execute()
        
        return send_from_directory(UPLOAD_FOLDER, book_data["filename"], as_attachment=True)
    except Exception as e:
        flash(f"Error downloading book: {e}", "error")
        return redirect(url_for("home"))


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