from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
import bcrypt
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey123")
app.permanent_session_lifetime = 3600  # 1 hour

# ------------------ HELPER FUNCTIONS ------------------
def get_db():
    """Return connection to the active company database."""
    db_name = session.get("db_name")
    if not db_name:
        return sqlite3.connect("default.db")
    return sqlite3.connect(db_name)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in first.", "warning")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

def init_company_db(db_name):
    """Create all tables for a new company database."""
    with sqlite3.connect(db_name) as conn:
        # Users
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password BLOB
            )
        """)
        # Company info
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                gst TEXT,
                category TEXT
            )
        """)
        # Categories
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        """)
        # Suppliers
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT
            )
        """)
        # Products
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                sku TEXT UNIQUE,
                category_id INTEGER,
                supplier_id INTEGER,
                price REAL,
                stock INTEGER DEFAULT 0
            )
        """)
        # Stock in
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_in (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                quantity INTEGER,
                date TEXT
            )
        """)
        # Stock out
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_out (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                quantity INTEGER,
                date TEXT
            )
        """)
        # Sales
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                quantity INTEGER,
                total REAL,
                date TEXT
            )
        """)

        # Insert default admin if not exists
        admin = conn.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        if not admin:
            hashed = bcrypt.hashpw("admin".encode(), bcrypt.gensalt())
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", hashed))

        # Insert default categories
        default_cats = ["Electronics", "Clothing", "Vehicles", "Hardware", "Food Items"]
        for cat in default_cats:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

# ------------------ ROUTES ------------------
@app.route("/test")
def test():
    return render_template("test.html")

@app.route("/")
def splash():
    return render_template("splash.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        company = request.form["company_name"].strip()
        gst = request.form["gst"].strip()
        category = request.form["category"].strip()
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        # Create company-specific database filename
        db_name = f"stockify_{company.replace(' ', '_').lower()}.db"
        session["db_name"] = db_name
        init_company_db(db_name)

        with sqlite3.connect(db_name) as conn:
            # Store/update company info
            conn.execute("DELETE FROM company")
            conn.execute("INSERT INTO company (name, gst, category) VALUES (?, ?, ?)",
                         (company, gst, category))

            # Verify user
            user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user and bcrypt.checkpw(password.encode(), user[2]):
            session.permanent = True
            session["user"] = username
            session["company"] = company
            flash(f"Welcome back, {username}!", "success")
            return redirect("/dashboard")
        else:
            flash("Invalid username or password", "danger")
            return render_template("login.html")

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as db:
        total_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_sales = db.execute("SELECT SUM(total) FROM sales").fetchone()[0] or 0
        low_stock = db.execute("SELECT COUNT(*) FROM products WHERE stock < 5").fetchone()[0]
    return render_template("dashboard.html",
                           total_products=total_products,
                           total_sales=total_sales,
                           low_stock_count=low_stock)

@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    with get_db() as db:
        if request.method == "POST":
            name = request.form["name"]
            price = float(request.form["price"])
            category = request.form["category"]
            supplier = request.form["supplier"]
            # Generate simple SKU
            sku = name[:3].upper() + str(int(datetime.now().timestamp()))[-4:]
            db.execute("""
                INSERT INTO products (name, sku, category_id, supplier_id, price, stock)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (name, sku, category, supplier, price))
            flash("Product added successfully!", "success")

        categories = db.execute("SELECT * FROM categories").fetchall()
        suppliers = db.execute("SELECT * FROM suppliers").fetchall()
        products = db.execute("""
            SELECT p.id, p.name, p.sku, p.price, p.stock,
                   c.name AS cat_name, s.name AS sup_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN suppliers s ON p.supplier_id = s.id
        """).fetchall()

    return render_template("products.html", products=products,
                           categories=categories, suppliers=suppliers)

@app.route("/suppliers", methods=["GET", "POST"])
@login_required
def suppliers():
    with get_db() as db:
        if request.method == "POST":
            name = request.form["name"]
            phone = request.form["phone"]
            db.execute("INSERT INTO suppliers (name, phone) VALUES (?, ?)", (name, phone))
            flash("Supplier added successfully!", "success")

        suppliers = db.execute("SELECT * FROM suppliers").fetchall()
    return render_template("suppliers.html", suppliers=suppliers)

@app.route("/stockin", methods=["GET", "POST"])
@login_required
def stockin():
    with get_db() as db:
        if request.method == "POST":
            product = request.form["product"]
            qty = int(request.form["qty"])
            date = datetime.now().strftime("%Y-%m-%d")
            db.execute("INSERT INTO stock_in (product_id, quantity, date) VALUES (?, ?, ?)",
                       (product, qty, date))
            db.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (qty, product))
            flash(f"Added {qty} units to stock.", "success")

        products = db.execute("SELECT * FROM products").fetchall()
    return render_template("stockin.html", products=products)

@app.route("/stockout", methods=["GET", "POST"])
@login_required
def stockout():
    with get_db() as db:
        if request.method == "POST":
            product = request.form["product"]
            qty = int(request.form["qty"])
            date = datetime.now().strftime("%Y-%m-%d")

            current = db.execute("SELECT stock FROM products WHERE id = ?", (product,)).fetchone()
            if current and current[0] >= qty:
                db.execute("INSERT INTO stock_out (product_id, quantity, date) VALUES (?, ?, ?)",
                           (product, qty, date))
                db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, product))
                flash(f"Removed {qty} units from stock.", "success")
            else:
                flash("Insufficient stock!", "danger")

        products = db.execute("SELECT * FROM products").fetchall()
    return render_template("stockout.html", products=products)

@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    with get_db() as db:
        if request.method == "POST":
            product_id = request.form["product"]
            qty = int(request.form["qty"])

            product = db.execute("SELECT price, stock FROM products WHERE id = ?", (product_id,)).fetchone()
            if product:
                price, stock = product
                if qty > stock:
                    qty = stock
                    flash(f"Quantity reduced to available stock ({stock}).", "warning")
                total = qty * price
                date = datetime.now().strftime("%Y-%m-%d")
                db.execute("INSERT INTO sales (product_id, quantity, total, date) VALUES (?, ?, ?, ?)",
                           (product_id, qty, total, date))
                db.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (qty, product_id))
                flash("Sale recorded successfully!", "success")
            else:
                flash("Product not found.", "danger")

        products = db.execute("SELECT * FROM products").fetchall()
    return render_template("sales.html", products=products)

@app.route("/reports")
@login_required
def reports():
    with get_db() as db:
        # Bar chart data: sales per product
        bar = db.execute("""
            SELECT p.name, SUM(s.total) as total
            FROM sales s
            JOIN products p ON s.product_id = p.id
            GROUP BY p.name
        """).fetchall()
        labels = [row[0] for row in bar]
        totals = [row[1] for row in bar]

        # Pie chart data: current stock per product
        pie = db.execute("SELECT name, stock FROM products WHERE stock > 0").fetchall()
    return render_template("reports.html", labels=labels, totals=totals, pie_data=pie)

@app.route("/tools")
@login_required
def tools():
    return render_template("tools.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)