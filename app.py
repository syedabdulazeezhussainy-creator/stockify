from flask import Flask, render_template, request, redirect, session
import sqlite3
import bcrypt
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecret123"


# ------------------ MULTI-COMPANY DATABASE ------------------
def get_db():
    """Returns the ACTIVE company DB"""
    db_name = session.get("db_name", "default.db")
    return sqlite3.connect(db_name)


def init_db(db_name):
    """Creates database structure for NEW company"""
    with sqlite3.connect(db_name) as db:

        # USERS
        db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password BLOB
        )
        """)

        # COMPANY SETTINGS
        db.execute("""
        CREATE TABLE IF NOT EXISTS company(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            gst TEXT,
            category TEXT,
            address TEXT
        )
        """)

        # CATEGORIES
        db.execute("""
        CREATE TABLE IF NOT EXISTS categories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT
        )
        """)

        # SUPPLIERS
        db.execute("""
        CREATE TABLE IF NOT EXISTS suppliers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT
        )
        """)

        # PRODUCTS
        db.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            sku TEXT,
            category_id INTEGER,
            supplier_id INTEGER,
            price REAL,
            stock INTEGER
        )
        """)

        # STOCK IN
        db.execute("""
        CREATE TABLE IF NOT EXISTS stock_in(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            quantity INTEGER,
            date TEXT
        )
        """)

        # STOCK OUT
        db.execute("""
        CREATE TABLE IF NOT EXISTS stock_out(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            quantity INTEGER,
            date TEXT
        )
        """)

        # SALES
        db.execute("""
        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            quantity INTEGER,
            total REAL,
            date TEXT
        )
        """)

        # Default admin user
        admin = db.execute("SELECT * FROM users").fetchone()
        if not admin:
            pwd = bcrypt.hashpw("admin".encode(), bcrypt.gensalt())
            db.execute("INSERT INTO users(username, password) VALUES(?,?)", ("admin", pwd))

        # Default categories
        defaults = ["Electronics", "Clothing", "Hardware", "Food Items", "Vehicles"]
        for cat in defaults:
            exists = db.execute("SELECT * FROM categories WHERE name=?", (cat,)).fetchone()
            if not exists:
                db.execute("INSERT INTO categories(name) VALUES(?)", (cat,))


# --------------------------- LOGIN ---------------------------
def login_required():
    return "user" not in session


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        company_name = request.form["company_name"]
        gst = request.form["gst"]
        category = request.form["category"]

        username = request.form["username"]
        password = request.form["password"]

        # Generate DB name for company
        db_name = f"stockify_{company_name.replace(' ', '_').lower()}.db"
        session["db_name"] = db_name

        # Create DB if new
        init_db(db_name)

        # Validate user
        with sqlite3.connect(db_name) as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

            # Save company info
            db.execute("DELETE FROM company")
            db.execute("INSERT INTO company(name, gst, category) VALUES(?,?,?)",
                       (company_name, gst, category))

        if user and bcrypt.checkpw(password.encode(), user[2]):
            session["user"] = username
            return redirect("/dashboard")

    return render_template("login.html")


# ------------------------- DASHBOARD -------------------------
@app.route("/dashboard")
def dashboard():
    if login_required():
        return redirect("/")

    with get_db() as db:
        total_products = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_sales = db.execute("SELECT SUM(total) FROM sales").fetchone()[0] or 0
        low_stock = db.execute("SELECT COUNT(*) FROM products WHERE stock < 5").fetchone()[0]

        month_labels = []
        month_totals = []
        rows = db.execute("""
            SELECT strftime('%m', date), SUM(total)
            FROM sales
            GROUP BY strftime('%m', date)
        """).fetchall()

        for m, t in rows:
            month_labels.append(m)
            month_totals.append(t)

    return render_template("dashboard.html",
                           total_products=total_products,
                           total_sales=total_sales,
                           low_stock_count=low_stock,
                           month_labels=month_labels,
                           month_totals=month_totals)


# --------------------------- PRODUCTS -------------------------
@app.route("/products", methods=["GET", "POST"])
def products():
    if login_required():
        return redirect("/")

    with get_db() as db:
        categories = db.execute("SELECT * FROM categories").fetchall()
        suppliers = db.execute("SELECT * FROM suppliers").fetchall()

        if request.method == "POST":
            name = request.form["name"]
            price = request.form["price"]
            category = request.form["category"]
            supplier = request.form["supplier"]

            # Auto SKU
            sku = name[:3].upper() + str(int(datetime.now().timestamp()))[-4:]

            db.execute("""
                INSERT INTO products(name, sku, price, stock, category_id, supplier_id)
                VALUES(?,?,?,?,?,?)
            """, (name, sku, price, 0, category, supplier))

        products = db.execute("""
            SELECT products.*, categories.name, suppliers.name
            FROM products
            LEFT JOIN categories ON products.category_id = categories.id
            LEFT JOIN suppliers ON products.supplier_id = suppliers.id
        """).fetchall()

    return render_template("products.html", products=products,
                           categories=categories, suppliers=suppliers)


# --------------------------- SUPPLIERS -------------------------
@app.route("/suppliers", methods=["GET", "POST"])
def suppliers():
    if login_required():
        return redirect("/")

    with get_db() as db:
        if request.method == "POST":
            name = request.form["name"]
            phone = request.form["phone"]
            db.execute("INSERT INTO suppliers(name, phone) VALUES(?,?)", (name, phone))

        suppliers = db.execute("SELECT * FROM suppliers").fetchall()

    return render_template("suppliers.html", suppliers=suppliers)


# --------------------------- STOCK IN --------------------------
@app.route("/stockin", methods=["GET", "POST"])
def stock_in():
    if login_required():
        return redirect("/")

    with get_db() as db:
        if request.method == "POST":
            product = request.form["product"]
            qty = int(request.form["qty"])
            date = datetime.now().strftime("%Y-%m-%d")

            db.execute("INSERT INTO stock_in(product_id, quantity, date) VALUES(?,?,?)",
                       (product, qty, date))
            db.execute("UPDATE products SET stock = stock + ? WHERE id=?", (qty, product))

        products = db.execute("SELECT * FROM products").fetchall()

    return render_template("stockin.html", products=products)


# --------------------------- STOCK OUT -------------------------
@app.route("/stockout", methods=["GET", "POST"])
def stock_out():
    if login_required():
        return redirect("/")

    with get_db() as db:
        if request.method == "POST":
            product = request.form["product"]
            qty = int(request.form["qty"])

            current = db.execute("SELECT stock FROM products WHERE id=?", (product,)).fetchone()[0]
            if qty > current:
                qty = current

            date = datetime.now().strftime("%Y-%m-%d")

            db.execute("INSERT INTO stock_out(product_id, quantity, date) VALUES(?,?,?)",
                       (product, qty, date))
            db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, product))

        products = db.execute("SELECT * FROM products").fetchall()

    return render_template("stockout.html", products=products)


# ----------------------------- SALES ---------------------------
@app.route("/sales", methods=["GET", "POST"])
def sales():
    if login_required():
        return redirect("/")

    with get_db() as db:
        if request.method == "POST":
            product_id = request.form["product"]
            qty = int(request.form["qty"])

            price, stock = db.execute("SELECT price, stock FROM products WHERE id=?", (product_id,)).fetchone()

            if qty > stock:
                qty = stock

            total = qty * price
            date = datetime.now().strftime("%Y-%m-%d")

            db.execute(
                "INSERT INTO sales(product_id, quantity, total, date) VALUES(?,?,?,?)",
                (product_id, qty, total, date)
            )
            db.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, product_id))

        products = db.execute("SELECT * FROM products").fetchall()

    return render_template("sales.html", products=products)


# ----------------------------- REPORTS ---------------------------
@app.route("/reports")
def reports():
    if login_required():
        return redirect("/")

    with get_db() as db:
        sales = db.execute("""
            SELECT sales.date, products.name, sales.quantity, sales.total
            FROM sales
            JOIN products ON sales.product_id = products.id
        """).fetchall()

        bar_data = db.execute("""
            SELECT products.name, SUM(sales.total)
            FROM sales
            JOIN products ON sales.product_id = products.id
            GROUP BY products.name
        """).fetchall()

        labels = [row[0] for row in bar_data]
        totals = [row[1] for row in bar_data]

        pie_data = db.execute("SELECT name, stock FROM products").fetchall()

    return render_template("reports.html",
                           sales=sales,
                           labels=labels,
                           totals=totals,
                           pie_data=pie_data)


# ----------------------------- LOGOUT ---------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ----------------------------- RUN ---------------------------
if __name__ == "__main__":
    app.run(debug=True)