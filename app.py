import calendar
import json
import math
import os
import secrets
from datetime import date
from datetime import datetime

from flask import Flask
from flask import flash
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from flask import url_for
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from database.db import check_db
from database.db import get_db


base_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(base_dir, "config", "settings.json")

with open(config_file, "r", encoding="utf-8") as file:
    config = json.load(file)

app = Flask(__name__)

# Session security is configured below after route registration.

app.config["APP_NAME"] = config["app_name"]
app.config["WARRANTY_ALERT_DAYS"] = config["warranty_alert_days"]
app.config["TESSERACT_CMD"] = config.get("tesseract_cmd", "")

app.config["DATABASE_FILE"] = os.path.join(
    base_dir,
    os.environ.get("ASSUREX_DATABASE", config["database_file"])
)

app.config["UPLOAD_FOLDER"] = os.path.join(
    base_dir,
    os.environ.get("ASSUREX_UPLOADS", config["upload_folder"])
)


def add_months(start_date, months):
    year = start_date.year
    month = start_date.month + months

    year += (month - 1) // 12
    month = (month - 1) % 12 + 1

    day = min(
        start_date.day,
        calendar.monthrange(year, month)[1]
    )

    return date(year, month, day)


def get_warranty_status(expiry_date, alert_days, start_date=None):
    today = date.today()

    days_left = (expiry_date - today).days

    if start_date and start_date > today:
        return "Upcoming", days_left

    if days_left < 0:
        return "Expired", days_left

    if days_left <= alert_days:
        return "Approaching Expiry", days_left

    return "Active", days_left


def update_warranties(user_id):
    try:
        with open(config_file, "r", encoding="utf-8") as file:
            current_config = json.load(file)

        alert_days = int(
            current_config.get("warranty_alert_days", 30)
        )

        db = get_db()

        rows = db.execute(
            """
            SELECT
                warranties.*,
                products.user_id,
                products.product_name,
                products.product_id AS public_product_id
            FROM warranties
            JOIN products
                ON warranties.product_id = products.id
            WHERE products.user_id = ?
            """,
            (user_id,)
        ).fetchall()

        for row in rows:
            expiry_date = datetime.strptime(
                row["expiry_date"],
                "%Y-%m-%d"
            ).date()

            status, days_left = get_warranty_status(
                expiry_date,
                alert_days,
                date.fromisoformat(row["start_date"])
            )

            db.execute(
                """
                UPDATE warranties
                SET status = ?
                WHERE id = ?
                """,
                (
                    status,
                    row["id"]
                )
            )

            if status == "Approaching Expiry":
                message = (
                    row["product_name"]
                    + " (" + row["public_product_id"] + ") warranty expires on "
                    + row["expiry_date"] + "."
                )

                old_alert = db.execute(
                    """
                    SELECT id
                    FROM notifications
                    WHERE user_id = ?
                    AND notification_type = ?
                    AND message = ?
                    """,
                    (
                        user_id,
                        "warranty expiry",
                        message
                    )
                ).fetchone()

                if not old_alert:
                    created_at = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    db.execute(
                        """
                        INSERT INTO notifications
                        (
                            user_id,
                            notification_type,
                            message,
                            is_read,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            "warranty expiry",
                            message,
                            0,
                            created_at
                        )
                    )

        db.commit()
        db.close()

    except Exception as e:
        print("warranty update error:", e)


@app.route("/")
def home():
    rows = check_db()

    return render_template(
        "index.html",
        table_count=len(rows)
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")

        allowed_roles = ["customer"]

        if not name or not email or not password or not role:
            flash("Please fill all required fields.", "danger")
            return render_template("register.html")

        if role not in allowed_roles:
            flash("Invalid account role.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )
            return render_template("register.html")

        try:
            db = get_db()

            old_user = db.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,)
            ).fetchone()

            if old_user:
                db.close()

                flash(
                    "An account with this email already exists.",
                    "danger"
                )

                return render_template("register.html")

            last_user = db.execute(
                """
                SELECT id
                FROM users
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if last_user:
                num = last_user["id"] + 1
            else:
                num = 1

            user_id = "USR-" + secrets.token_hex(6).upper()

            password_hash = generate_password_hash(password)

            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            cur = db.execute(
                """
                INSERT INTO users
                (
                    user_id,
                    name,
                    email,
                    password,
                    phone,
                    role,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    name,
                    email,
                    password_hash,
                    phone,
                    role,
                    created_at
                )
            )

            new_id = cur.lastrowid

            db.execute(
                """
                INSERT INTO audit
                (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    new_id,
                    "account creation",
                    "user registered",
                    created_at
                )
            )

            db.commit()
            db.close()

            flash(
                "Account created. You can now log in.",
                "success"
            )

            return redirect(url_for("login"))

        except Exception as e:
            print("register error:", e)

            flash(
                "Account could not be created.",
                "danger"
            )

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash(
                "Enter your email and password.",
                "danger"
            )

            return render_template("login.html")

        try:
            db = get_db()

            user = db.execute(
                """
                SELECT *
                FROM users
                WHERE email = ?
                """,
                (email,)
            ).fetchone()

            db.close()

            if not user:
                flash(
                    "Email or password is incorrect.",
                    "danger"
                )

                return render_template("login.html")

            if not check_password_hash(
                user["password"],
                password
            ):
                flash(
                    "Email or password is incorrect.",
                    "danger"
                )

                return render_template("login.html")

            session.clear()

            session["user_id"] = user["id"]
            session["public_user_id"] = user["user_id"]
            session["name"] = user["name"]
            session["role"] = user["role"]

            if user["role"] == "customer":
                return redirect(
                    url_for("customer_dashboard")
                )

            if user["role"] == "service_centre_employee":
                return redirect(
                    url_for("employee_dashboard")
                )

            if user["role"] == "reviewer":
                return redirect(
                    url_for("reviewer_dashboard")
                )

            if user["role"] == "admin":
                return redirect(
                    url_for("admin_dashboard")
                )

            session.clear()

            flash(
                "This account does not have a valid role.",
                "danger"
            )

        except Exception as e:
            print("login error:", e)

            flash(
                "Login could not be completed.",
                "danger"
            )

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    try:
        db = get_db()

        user = db.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (session["user_id"],)
        ).fetchone()

        if not user:
            db.close()
            session.clear()

            flash(
                "Account could not be found.",
                "danger"
            )

            return redirect(url_for("login"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            address = request.form.get("address", "").strip()

            if not name or not email:
                db.close()

                flash(
                    "Name and email are required.",
                    "danger"
                )

                return render_template(
                    "profile.html",
                    user=user
                )

            old_email = db.execute(
                """
                SELECT id
                FROM users
                WHERE email = ?
                AND id != ?
                """,
                (
                    email,
                    session["user_id"]
                )
            ).fetchone()

            if old_email:
                db.close()

                flash(
                    "This email is already registered.",
                    "danger"
                )

                return render_template(
                    "profile.html",
                    user=user
                )

            db.execute(
                """
                UPDATE users
                SET
                    name = ?,
                    email = ?,
                    phone = ?,
                    address = ?
                WHERE id = ?
                """,
                (
                    name,
                    email,
                    phone,
                    address,
                    session["user_id"]
                )
            )

            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            db.execute(
                """
                INSERT INTO audit
                (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    "profile update",
                    "profile information updated",
                    created_at
                )
            )

            db.commit()

            session["name"] = name

            user = db.execute(
                """
                SELECT *
                FROM users
                WHERE id = ?
                """,
                (session["user_id"],)
            ).fetchone()

            db.close()

            flash(
                "Profile updated successfully.",
                "success"
            )

            return render_template(
                "profile.html",
                user=user
            )

        db.close()

        return render_template(
            "profile.html",
            user=user
        )

    except Exception as e:
        print("profile error:", e)

        flash(
            "Profile could not be loaded.",
            "danger"
        )

        return redirect(url_for("home"))


@app.route("/products")
def products():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "customer":
        flash(
            "Only customers can manage products.",
            "danger"
        )
        return redirect(url_for("home"))

    try:
        db = get_db()

        rows = db.execute(
            """
            SELECT *
            FROM products
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (session["user_id"],)
        ).fetchall()

        db.close()

        query = request.args.get("q", "").strip().casefold()
        if query:
            rows = [row for row in rows if query in " ".join(str(row[key] or "") for key in ("product_id", "product_name", "serial_number", "category", "brand")).casefold()]
        return render_template(
            "products.html",
            products=rows
        )

    except Exception as e:
        print("products error:", e)

        flash(
            "Products could not be loaded.",
            "danger"
        )

        return redirect(url_for("customer_dashboard"))


@app.route("/products/add", methods=["GET", "POST"])
def add_product():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "customer":
        flash(
            "Only customers can register products.",
            "danger"
        )
        return redirect(url_for("home"))

    if request.method == "POST":
        product_name = request.form.get(
            "product_name",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        brand = request.form.get(
            "brand",
            ""
        ).strip()

        model_number = request.form.get(
            "model_number",
            ""
        ).strip()

        serial_number = request.form.get(
            "serial_number",
            ""
        ).strip()

        purchase_date = request.form.get(
            "purchase_date",
            ""
        ).strip()

        purchase_price = request.form.get(
            "purchase_price",
            ""
        ).strip()

        retailer = request.form.get(
            "retailer",
            ""
        ).strip()

        warranty_duration = request.form.get(
            "warranty_duration",
            ""
        ).strip()

        if (
            not product_name
            or not category
            or not brand
            or not serial_number
            or not purchase_date
            or not purchase_price
            or not retailer
            or not warranty_duration
        ):
            flash(
                "Please fill all required fields.",
                "danger"
            )

            return render_template(
                "add_product.html"
            )

        try:
            price = float(purchase_price)
            duration = int(warranty_duration)

            parsed_purchase = date.fromisoformat(purchase_date)
            if parsed_purchase > date.today():
                raise ValueError("Purchase date cannot be in the future")
            if not math.isfinite(price) or price < 0 or duration < 1 or duration > 1200:
                flash(
                    "Enter valid price and warranty duration.",
                    "danger"
                )

                return render_template(
                    "add_product.html"
                )

        except Exception as e:
            print("product value error:", e)

            flash(
                "Check the purchase date, price and warranty duration (1–1200 months).",
                "danger"
            )

            return render_template(
                "add_product.html"
            )

        try:
            db = get_db()

            last_product = db.execute(
                """
                SELECT id
                FROM products
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if last_product:
                num = last_product["id"] + 1
            else:
                num = 1

            product_id = "PRD-" + secrets.token_hex(6).upper()

            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            product_cursor = db.execute(
                """
                INSERT INTO products
                (
                    product_id,
                    user_id,
                    product_name,
                    category,
                    brand,
                    model_number,
                    serial_number,
                    purchase_date,
                    purchase_price,
                    retailer,
                    warranty_duration,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_id,
                    session["user_id"],
                    product_name,
                    category,
                    brand,
                    model_number,
                    serial_number,
                    purchase_date,
                    price,
                    retailer,
                    duration,
                    created_at
                )
            )

            # Product registration already collects the purchase date,
            # retailer and warranty duration. Persist that warranty too so
            # the product is immediately eligible for a claim.
            product_db_id = product_cursor.lastrowid
            warranty_start = parsed_purchase
            warranty_expiry = add_months(warranty_start, duration)
            warranty_status, _ = get_warranty_status(
                warranty_expiry,
                app.config["WARRANTY_ALERT_DAYS"],
                warranty_start
            )
            db.execute(
                """
                INSERT INTO warranties
                (
                    product_id, warranty_type, provider, start_date,
                    expiry_date, coverage_conditions, exclusions,
                    service_center_details, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_db_id,
                    "standard",
                    retailer,
                    warranty_start.isoformat(),
                    warranty_expiry.isoformat(),
                    "",
                    "",
                    "",
                    warranty_status,
                    created_at
                )
            )

            db.execute(
                """
                INSERT INTO audit
                (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    "product registration",
                    "product " + product_id + " registered",
                    created_at
                )
            )

            db.commit()
            db.close()

            flash(
                "Product and its standard warranty registered successfully.",
                "success"
            )

            return redirect(url_for("products"))

        except Exception as e:
            print("add product error:", e)

            flash(
                "Product could not be registered.",
                "danger"
            )

    return render_template("add_product.html")


@app.route("/warranties")
def warranties():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "customer":
        flash(
            "Only customers can view their warranties.",
            "danger"
        )
        return redirect(url_for("home"))

    update_warranties(session["user_id"])

    try:
        with open(config_file, "r", encoding="utf-8") as file:
            current_config = json.load(file)

        alert_days = current_config.get(
            "warranty_alert_days",
            30
        )

        db = get_db()

        rows = db.execute(
            """
            SELECT
                warranties.*,
                products.product_id AS public_product_id,
                products.product_name,
                products.brand,
                products.model_number
            FROM warranties
            JOIN products
                ON warranties.product_id = products.id
            WHERE products.user_id = ?
            ORDER BY warranties.id DESC
            """,
            (session["user_id"],)
        ).fetchall()

        data = []

        for row in rows:
            expiry_date = datetime.strptime(
                row["expiry_date"],
                "%Y-%m-%d"
            ).date()

            status, days_left = get_warranty_status(
                expiry_date,
                int(alert_days),
                date.fromisoformat(row["start_date"])
            )

            warranty = dict(row)

            if days_left >= 0:
                warranty["days_left"] = days_left
            else:
                warranty["days_left"] = 0

            warranty["status"] = status

            query = request.args.get("q", "").strip().casefold()
            selected_status = request.args.get("status", "")
            if selected_status and selected_status != status:
                continue
            if query and query not in " ".join(str(warranty[key] or "") for key in ("public_product_id", "product_name", "provider", "warranty_type")).casefold():
                continue
            data.append(warranty)

        notifications = db.execute(
            """
            SELECT *
            FROM notifications
            WHERE user_id = ?
            AND notification_type = ?
            ORDER BY id DESC
            """,
            (
                session["user_id"],
                "warranty expiry"
            )
        ).fetchall()

        db.close()

        return render_template(
            "warranties.html",
            warranties=data,
            notifications=notifications,
            alert_days=alert_days
        )

    except Exception as e:
        print("warranties error:", e)

        flash(
            "Warranties could not be loaded.",
            "danger"
        )

        return redirect(url_for("customer_dashboard"))


@app.route(
    "/warranties/add/<int:product_db_id>",
    methods=["GET", "POST"]
)
def add_warranty(product_db_id):
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "customer":
        flash(
            "Only customers can manage warranties.",
            "danger"
        )
        return redirect(url_for("home"))

    try:
        db = get_db()

        product = db.execute(
            """
            SELECT *
            FROM products
            WHERE id = ?
            AND user_id = ?
            """,
            (
                product_db_id,
                session["user_id"]
            )
        ).fetchone()

        if not product:
            db.close()

            flash(
                "Product could not be found.",
                "danger"
            )

            return redirect(url_for("products"))

        if request.method == "POST":
            warranty_type = request.form.get(
                "warranty_type",
                ""
            ).strip()

            provider = request.form.get(
                "provider",
                ""
            ).strip()

            start_date_text = request.form.get(
                "start_date",
                ""
            ).strip()

            duration_text = request.form.get(
                "duration",
                ""
            ).strip()

            coverage_conditions = request.form.get(
                "coverage_conditions",
                ""
            ).strip()

            exclusions = request.form.get(
                "exclusions",
                ""
            ).strip()

            service_center_details = request.form.get(
                "service_center_details",
                ""
            ).strip()

            if warranty_type not in ["standard", "extended"]:
                db.close()

                flash(
                    "Select a valid warranty type.",
                    "danger"
                )

                return render_template(
                    "add_warranty.html",
                    product=product
                )

            if (
                not provider
                or not start_date_text
                or not duration_text
            ):
                db.close()

                flash(
                    "Please fill all required fields.",
                    "danger"
                )

                return render_template(
                    "add_warranty.html",
                    product=product
                )

            try:
                start_date = datetime.strptime(
                    start_date_text,
                    "%Y-%m-%d"
                ).date()

                duration = int(duration_text)

                if duration < 1 or duration > 1200 or start_date < date.fromisoformat(product["purchase_date"]):
                    raise ValueError

            except Exception as e:
                print("warranty value error:", e)

                db.close()

                flash(
                    "Enter a valid start date and duration.",
                    "danger"
                )

                return render_template(
                    "add_warranty.html",
                    product=product
                )

            expiry_date = add_months(
                start_date,
                duration
            )

            with open(
                config_file,
                "r",
                encoding="utf-8"
            ) as file:
                current_config = json.load(file)

            alert_days = int(
                current_config.get(
                    "warranty_alert_days",
                    30
                )
            )

            status, days_left = get_warranty_status(
                expiry_date,
                alert_days,
                start_date
            )

            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            db.execute(
                """
                INSERT INTO warranties
                (
                    product_id,
                    warranty_type,
                    provider,
                    start_date,
                    expiry_date,
                    coverage_conditions,
                    exclusions,
                    service_center_details,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product["id"],
                    warranty_type,
                    provider,
                    start_date.isoformat(),
                    expiry_date.isoformat(),
                    coverage_conditions,
                    exclusions,
                    service_center_details,
                    status,
                    created_at
                )
            )

            db.execute(
                """
                INSERT INTO audit
                (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    "warranty registration",
                    "warranty added for "
                    + product["product_id"],
                    created_at
                )
            )

            if status == "Approaching Expiry":
                message = (
                    product["product_name"]
                    + " (" + product["product_id"] + ") warranty expires on "
                    + expiry_date.isoformat() + "."
                )

                db.execute(
                    """
                    INSERT INTO notifications
                    (
                        user_id,
                        notification_type,
                        message,
                        is_read,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session["user_id"],
                        "warranty expiry",
                        message,
                        0,
                        created_at
                    )
                )

            db.commit()
            db.close()

            flash(
                "Warranty record saved successfully.",
                "success"
            )

            return redirect(url_for("warranties"))

        db.close()

        return render_template(
            "add_warranty.html",
            product=product
        )

    except Exception as e:
        print("add warranty error:", e)

        flash(
            "Warranty could not be saved.",
            "danger"
        )

        return redirect(url_for("products"))


@app.route(
    "/admin/warranty-settings",
    methods=["GET", "POST"]
)
def warranty_settings():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        flash(
            "Only administrators can change this setting.",
            "danger"
        )
        return redirect(url_for("home"))

    try:
        with open(config_file, "r", encoding="utf-8") as file:
            current_config = json.load(file)

        if request.method == "POST":
            days_text = request.form.get(
                "warranty_alert_days",
                ""
            ).strip()

            try:
                days = int(days_text)

                if days < 1:
                    raise ValueError

            except Exception as e:
                print("alert setting error:", e)

                flash(
                    "Enter a valid number of days.",
                    "danger"
                )

                return render_template(
                    "warranty_settings.html",
                    alert_days=current_config.get(
                        "warranty_alert_days",
                        30
                    )
                )

            current_config["warranty_alert_days"] = days
            app.config["WARRANTY_ALERT_DAYS"] = days

            with open(
                config_file,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    current_config,
                    file,
                    indent=4
                )

            created_at = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            db = get_db()

            db.execute(
                """
                INSERT INTO audit
                (
                    user_id,
                    action,
                    details,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    "warranty alert setting",
                    "alert days changed to " + str(days),
                    created_at
                )
            )

            db.commit()
            db.close()

            flash(
                "Warranty alert setting updated.",
                "success"
            )

            return redirect(
                url_for("warranty_settings")
            )

        return render_template(
            "warranty_settings.html",
            alert_days=current_config.get(
                "warranty_alert_days",
                30
            )
        )

    except Exception as e:
        print("warranty setting error:", e)

        flash(
            "Warranty setting could not be loaded.",
            "danger"
        )

        return redirect(url_for("admin_dashboard"))


@app.route("/customer")
def customer_dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "customer":
        flash(
            "You do not have access to this page.",
            "danger"
        )

        return redirect(url_for("home"))

    return redirect(url_for("workflow.dashboard"))


@app.route("/employee")
def employee_dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "service_centre_employee":
        flash(
            "You do not have access to this page.",
            "danger"
        )

        return redirect(url_for("home"))

    return redirect(url_for("workflow.dashboard"))


@app.route("/reviewer")
def reviewer_dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "reviewer":
        flash(
            "You do not have access to this page.",
            "danger"
        )

        return redirect(url_for("home"))

    return redirect(url_for("workflow.dashboard"))


@app.route("/admin")
def admin_dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "danger")
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        flash(
            "You do not have access to this page.",
            "danger"
        )

        return redirect(url_for("home"))

    return redirect(url_for("workflow.dashboard"))


from security import configure_security
from workflow import initialize_database, install_workflow

configure_security(app)
install_workflow(app)
initialize_database(app)


@app.before_request
def refresh_customer_warranties():
    if session.get("role") == "customer" and request.endpoint in ("workflow.dashboard", "workflow.notifications"):
        update_warranties(session["user_id"])


if __name__ == "__main__":
    app.run(port=int(os.environ.get("ASSUREX_PORT", "5000")), debug=os.environ.get("ASSUREX_DEBUG") == "1")
