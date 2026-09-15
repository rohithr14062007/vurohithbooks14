import os
import random
import io
import mimetypes
import uuid
from datetime import timedelta
from dotenv import load_dotenv
from supabase import create_client

from flask import Flask, flash, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Load environment variables from the project file regardless of launch directory.
load_dotenv(os.path.join(BASE_DIR, "supabase.env"), override=True)

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = (
    os.environ.get("SUPABASE_SECRET_KEY")
    or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_KEY")
    or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
)

if not supabase_url or not supabase_key:
    raise RuntimeError(
        "Could not initialize Supabase: Supabase credentials not found in environment. "
        f"URL: {bool(supabase_url)}, KEY: {bool(supabase_key)}"
    )

supabase = create_client(supabase_url, supabase_key)
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "books")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "rohith-books-secret-2026"),
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)

@app.template_filter("slugify")
def slugify_filter(s):
    if not s:
        return ""
    import re
    return re.sub(r'[\W_]+', '-', str(s)).strip('-').lower()

_db_initialized = False

def init_db():
    """Ensure default categories exist in Supabase."""
    global _db_initialized
    if _db_initialized or not supabase:
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
                "password_hash": generate_password_hash("admin@1406"),
                "role": "admin",
                "phone": "0000000000",
                "is_admin": True
            }).execute()
        _db_initialized = True
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


def remove_storage_file(filename):
    """Remove a file from Storage, ignoring cleanup errors during a larger operation."""
    if not filename or not supabase:
        return
    try:
        supabase.storage.from_(STORAGE_BUCKET).remove([filename])
    except Exception as e:
        print(f"Warning: Could not remove storage object {filename}: {e}")


def get_user_by_username(username):
    if not username or not supabase:
        return None
    try:
        clean_name = str(username).strip()
        res_uname = supabase.table("users").select("*").ilike("username", clean_name).execute()
        if res_uname.data:
            return res_uname.data[0]
        res_email = supabase.table("users").select("*").ilike("email", clean_name).execute()
        return res_email.data[0] if res_email.data else None
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
        rev_data = {}
        dl_data = {}
        try:
            rev_res = supabase.table("reviews").select("book_id, rating").execute()
            for r in (rev_res.data or []):
                bid = r["book_id"]
                if bid not in rev_data:
                    rev_data[bid] = []
                rev_data[bid].append(r["rating"])
        except Exception:
            pass

        try:
            dl_res = supabase.table("download_history").select("book_id").execute()
            for d in (dl_res.data or []):
                bid = d["book_id"]
                dl_data[bid] = dl_data.get(bid, 0) + 1
        except Exception:
            pass

        for book in response.data or []:
            book_item = dict(book)
            book_item["uploader"] = book.get("users", {}).get("username", "Unknown") if isinstance(book.get("users"), dict) else "Unknown"
            book_item["category_name"] = book.get("categories", {}).get("name", "Others") if isinstance(book.get("categories"), dict) else "Others"
            ratings = rev_data.get(book["id"], [])
            book_item["review_count"] = len(ratings)
            book_item["avg_rating"] = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
            book_item["download_count"] = dl_data.get(book["id"], 0)
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
        try:
            rev_res = supabase.table("reviews").select("rating").eq("book_id", book_id).execute()
            ratings = [r["rating"] for r in (rev_res.data or [])]
            book["review_count"] = len(ratings)
            book["avg_rating"] = round(sum(ratings) / len(ratings), 1) if ratings else 0.0
        except Exception:
            book["review_count"] = 0
            book["avg_rating"] = 0.0

        try:
            dl_res = supabase.table("download_history").select("id", count="exact").eq("book_id", book_id).execute()
            book["download_count"] = dl_res.count if hasattr(dl_res, 'count') else len(dl_res.data or [])
        except Exception:
            book["download_count"] = 0

        return book
    except Exception as e:
        print(f"Error getting book: {e}")
        return None


def get_book_reviews(book_id):
    if not supabase:
        return []
    try:
        res = supabase.table("reviews").select("*").eq("book_id", book_id).order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        print(f"Error getting reviews: {e}")
        return []


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
        query = supabase.table("download_history").select("*, books(id, title, author, categories(name)), users(id, username)")
        
        if user_id:
            query = query.eq("user_id", user_id)
        
        response = query.order("downloaded_at", desc=True).execute()
        
        downloads = []
        for dl in response.data or []:
            book_info = dl.get("books") or {}
            cat_info = book_info.get("categories") or {}
            dl_item = {
                "id": dl.get("id"),
                "downloaded_at": dl.get("downloaded_at"),
                "book_id": book_info.get("id"),
                "book_title": book_info.get("title", "Unknown"),
                "author": book_info.get("author", "Unknown"),
                "user_id": dl.get("users", {}).get("id"),
                "username": dl.get("users", {}).get("username", "Unknown"),
                "category_name": cat_info.get("name", "Others") if isinstance(cat_info, dict) else "Others",
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

    section = request.args.get("section", "", type=str).strip()
    search_term = request.args.get("q", "", type=str).strip()
    selected_category_id = request.args.get("category_id", "", type=int) or None
    books = get_books(search=search_term, category_id=selected_category_id)
    student_entry = None
    downloaded_book_ids = set()
    
    if user and not user.get("is_admin"):
        try:
            response = supabase.table("student_entries").select("*").eq("user_id", user["id"]).order("id", desc=True).limit(1).execute()
            student_entry = response.data[0] if response.data else None
        except Exception as e:
            print(f"Error getting student entry: {e}")

        try:
            dl_res = supabase.table("download_history").select("book_id").eq("user_id", user["id"]).execute()
            downloaded_book_ids = {r["book_id"] for r in (dl_res.data or [])}
        except Exception as e:
            print(f"Error getting user downloaded books: {e}")

    default_section = section or ("books" if user else "landing")

    return render_template(
        "index.html",
        current_user=user,
        logged_in=bool(user),
        owner_logged=bool(user and user.get("is_admin")),
        books=books,
        downloaded_book_ids=downloaded_book_ids,
        student_entry=student_entry,
        categories=get_categories(),
        selected_category_id=selected_category_id,
        search_term=search_term,
        recent_activity=get_recent_activity(),
        default_section=default_section,
    )


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    account_id = request.form.get("account_id", "").strip()
    if not account_id:
        account_id = request.form.get("username", "").strip() or request.form.get("email", "").strip()

    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not account_id or not new_password or not confirm_password:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("home", section="auth"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "error")
        return redirect(url_for("home", section="auth"))

    if len(new_password) < 6:
        flash("Password must be at least 6 characters long.", "error")
        return redirect(url_for("home", section="auth"))

    if not supabase:
        flash("Database error. Please try again later.", "error")
        return redirect(url_for("home", section="auth"))

    user = None
    try:
        # 1. Search by username (case-insensitive)
        res_uname = supabase.table("users").select("*").ilike("username", account_id).execute()
        if res_uname.data:
            user = res_uname.data[0]
        else:
            # 2. Search by email (case-insensitive)
            res_email = supabase.table("users").select("*").ilike("email", account_id).execute()
            if res_email.data:
                user = res_email.data[0]
    except Exception as e:
        print(f"Error finding user for reset: {e}")

    if not user:
        flash(f"No account found matching '{account_id}'.", "error")
        return redirect(url_for("home", section="auth"))

    try:
        supabase.table("users").update({
            "password_hash": generate_password_hash(new_password)
        }).eq("id", user["id"]).execute()
        flash(f"Password reset successfully for '{user.get('username')}'! Please log in with your new password.", "success")
    except Exception as e:
        flash(f"Error resetting password: {e}", "error")

    return redirect(url_for("home", section="auth"))


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        flash("Please enter both username/email and password.", "error")
        return redirect(url_for("home", section="auth"))

    user = get_user_by_username(username)
    if not user or not check_password_hash(user.get("password_hash", ""), password):
        flash("Invalid username or password.", "error")
        return redirect(url_for("home", section="auth"))

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


@app.route("/settings/update-profile", methods=["POST"])
def update_profile():
    if not session.get("user_id"):
        flash("Please log in to update your profile.", "error")
        return redirect(url_for("home"))

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()

    if not name or not email:
        flash("Name and email are required.", "error")
        return redirect(url_for("settings_page"))

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("settings_page"))

    try:
        supabase.table("users").update({
            "name": name,
            "email": email,
            "phone": phone or None,
        }).eq("id", session["user_id"]).execute()
        flash("Profile updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating profile: {e}", "error")

    return redirect(url_for("settings_page"))


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

    if session.get("is_admin"):
        flash("The Administrator account cannot be deleted.", "error")
        return redirect(url_for("settings_page"))

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
            
            # Delete uploaded book files from Storage or the legacy local folder.
            for book in uploaded_books.data or []:
                file_path = os.path.join(UPLOAD_FOLDER, book["filename"])
                if os.path.exists(file_path):
                    os.remove(file_path)
                else:
                    remove_storage_file(book["filename"])
            
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

    mandatory_fields = [
        name, email, date_of_birth, fathers_name, mothers_name,
        phone1, emergency_contact, address, pincode,
        institution_name, blood_group, nationality, religion, parent_occupation
    ]
    if not all(mandatory_fields):
        flash("All fields except Phone 2 and Aadhaar Number are required.", "error")
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

    filename = f"{uuid.uuid4().hex}_{safe_name}"

    if not supabase:
        flash("Database error.", "error")
        return redirect(url_for("home"))

    storage_uploaded = False
    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            filename,
            uploaded.read(),
            {
                "content-type": uploaded.mimetype or "application/octet-stream",
                "upsert": False,
            },
        )
        storage_uploaded = True

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
        if storage_uploaded:
            remove_storage_file(filename)
        flash(f"Error uploading book to Supabase bucket '{STORAGE_BUCKET}': {e}", "error")
    
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


def get_all_reviews():
    if not supabase:
        return []
    try:
        res = supabase.table("reviews").select("*, books(title), users(username, name)").order("created_at", desc=True).execute()
        reviews = []
        for r in res.data or []:
            book_info = r.get("books") or {}
            user_info = r.get("users") or {}
            item = {
                "id": r.get("id"),
                "book_id": r.get("book_id"),
                "book_title": book_info.get("title", "Unknown Book") if isinstance(book_info, dict) else "Unknown Book",
                "user_name": r.get("user_name") or (user_info.get("name") if isinstance(user_info, dict) else None) or (user_info.get("username") if isinstance(user_info, dict) else None) or "Anonymous",
                "rating": r.get("rating", 5),
                "comment": r.get("comment", ""),
                "created_at": r.get("created_at"),
            }
            reviews.append(item)
        return reviews
    except Exception as e:
        print(f"Error getting all reviews: {e}")
        return []


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
        all_reviews=get_all_reviews(),
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
            # Remove dependent rows first when foreign keys are not configured
            # with cascading deletes in Supabase.
            supabase.table("reviews").delete().eq("book_id", book_id).execute()
            supabase.table("download_history").delete().eq("book_id", book_id).execute()
            file_path = os.path.join(UPLOAD_FOLDER, book_data["filename"])
            if os.path.exists(file_path):
                os.remove(file_path)
            else:
                remove_storage_file(book_data.get("filename"))
            
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

        download_name = book_data.get("original_name") or book_data["filename"]
        local_path = os.path.join(UPLOAD_FOLDER, book_data["filename"])
        if os.path.isfile(local_path):
            return send_from_directory(
                UPLOAD_FOLDER,
                book_data["filename"],
                as_attachment=True,
                download_name=download_name,
            )

        file_data = supabase.storage.from_(STORAGE_BUCKET).download(book_data["filename"])
        return send_file(
            io.BytesIO(file_data),
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetypes.guess_type(download_name)[0] or "application/octet-stream",
        )
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


@app.route("/preview/<int:book_id>")
def preview_book(book_id):
    if not session.get("user_id"):
        flash("Please log in to preview books.", "error")
        return redirect(url_for("home"))
    if not supabase:
        return "Database error", 500
    try:
        book = supabase.table("books").select("*").eq("id", book_id).execute()
        if not book.data:
            return "Book not found", 404
        book_data = book.data[0]
        local_path = os.path.join(UPLOAD_FOLDER, book_data["filename"])
        mime = mimetypes.guess_type(book_data.get("original_name") or book_data["filename"])[0] or "application/pdf"
        if os.path.isfile(local_path):
            return send_from_directory(UPLOAD_FOLDER, book_data["filename"], mimetype=mime)
        file_data = supabase.storage.from_(STORAGE_BUCKET).download(book_data["filename"])
        return send_file(io.BytesIO(file_data), mimetype=mime)
    except Exception as e:
        return f"Preview error: {e}", 500


@app.route("/submit-review/<int:book_id>", methods=["POST"])
def submit_review(book_id):
    if not session.get("user_id"):
        flash("Please log in to submit a review.", "error")
        return redirect(url_for("home"))
    rating = int(request.form.get("rating", 5))
    comment = request.form.get("comment", "").strip()
    user = get_user_by_id(session["user_id"])
    if not user:
        flash("User error.", "error")
        return redirect(url_for("book_details", book_id=book_id))
    try:
        supabase.table("reviews").insert({
            "book_id": book_id,
            "user_id": session["user_id"],
            "user_name": user.get("name") or user.get("username") or "Anonymous",
            "rating": rating,
            "comment": comment
        }).execute()
        flash("Review submitted successfully!", "success")
    except Exception as e:
        flash(f"Error submitting review: {e}", "error")
    return redirect(url_for("book_details", book_id=book_id))


@app.route("/admin/edit-book/<int:book_id>", methods=["POST"])
def edit_book(book_id):
    if not session.get("is_admin"):
        flash("Unauthorized", "error")
        return redirect(url_for("home"))
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category_id = request.form.get("category_id")
    description = request.form.get("description", "").strip()
    try:
        payload = {"title": title, "author": author, "description": description}
        if category_id:
            payload["category_id"] = int(category_id)
        supabase.table("books").update(payload).eq("id", book_id).execute()
        flash("Book updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating book: {e}", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add-category", methods=["POST"])
def add_category():
    if not session.get("is_admin"):
        flash("Unauthorized", "error")
        return redirect(url_for("home"))
    name = request.form.get("name", "").strip()
    if name:
        try:
            supabase.table("categories").insert({"name": name}).execute()
            flash(f"Category '{name}' added successfully.", "success")
        except Exception as e:
            flash(f"Error adding category: {e}", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-category/<int:category_id>", methods=["POST"])
def delete_category(category_id):
    if not session.get("is_admin"):
        flash("Unauthorized", "error")
        return redirect(url_for("home"))
    try:
        supabase.table("categories").delete().eq("id", category_id).execute()
        flash("Category deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting category: {e}", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export/students")
def export_students():
    if not session.get("is_admin"):
        flash("Unauthorized", "error")
        return redirect(url_for("home"))
    import csv
    entries = get_student_entries()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID", "Name", "Student No", "Branch", "Year", "Phone1", "Phone2", "Emergency", "Address", "Pincode", "Created At"])
    for e in entries:
        cw.writerow([e.get("id"), e.get("name"), e.get("student_no"), e.get("branch"), e.get("year"), e.get("phone1"), e.get("phone2"), e.get("emergency_contact"), e.get("address"), e.get("pincode"), e.get("created_at")])
    return send_file(io.BytesIO(si.getvalue().encode("utf-8")), mimetype="text/csv", as_attachment=True, download_name="student_visitors.csv")


@app.route("/admin/export/downloads")
def export_downloads():
    if not session.get("is_admin"):
        flash("Unauthorized", "error")
        return redirect(url_for("home"))
    import csv
    history = get_download_history()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID", "Book Title", "User", "Downloaded At"])
    for d in history:
        cw.writerow([d.get("id"), d.get("book_title"), d.get("user_name"), d.get("downloaded_at")])
    return send_file(io.BytesIO(si.getvalue().encode("utf-8")), mimetype="text/csv", as_attachment=True, download_name="download_history.csv")


@app.route("/admin/export/users")
def export_users():
    if not session.get("is_admin"):
        flash("Unauthorized", "error")
        return redirect(url_for("home"))
    import csv
    users = get_users()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID", "Username", "Name", "Email", "Phone", "Role", "Is Admin", "Created At"])
    for u in users:
        cw.writerow([
            u.get("id"),
            u.get("username"),
            u.get("name"),
            u.get("email"),
            u.get("phone"),
            u.get("role"),
            u.get("is_admin"),
            u.get("created_at"),
        ])
    return send_file(
        io.BytesIO(si.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="user_details_export.csv",
    )


@app.route("/activity")
def recent_activity_page():
    if not session.get("user_id") and not session.get("logged_in") and not session.get("is_admin"):
        flash("Please log in to view activity.", "error")
        return redirect(url_for("home"))
    return render_template(
        "activity.html",
        recent_activity=get_recent_activity(limit=50),
    )


@app.route("/uploads/<path:filename>")
def served_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 2111))
    app.run(debug=False, host="0.0.0.0", port=port)