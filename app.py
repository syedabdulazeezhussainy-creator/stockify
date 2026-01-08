from flask import Flask, render_template, request, redirect, session, send_file, flash
import sqlite3
import bcrypt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import datetime
import os
import csv
from flask import Response
app = Flask(__name__)
app.secret_key = "stockify_secret_key"


# ================= DATABASE =================
def get_db():
    conn = sqlite3.connect("inventory.db")
    conn.row_factory = sqlite3.Row
    return conn


# ================= INITIAL SETUP =================
with get_db() as db:
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password BLOB
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        price REAL,
        stock INTEGER
    )
    """)

    db.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product TEXT,
        quantity INTEGER,
        total REAL,
        created_at TEXT
    )
    """)

    # Create default admin
    admin = db.execute(
        "SELECT * FROM users WHERE username='admin'"
    ).fetchone()

    if not admin:
        db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("admin", bcrypt.hashpw(b"admin123", bcrypt.gensalt()))
        )


# ================= LOGIN CHECK =================
def login_required():
    return "user" not in session

@app.route("/export_sales")
def export_sales():
    if login_required():
        return redirect("/login")

    with get_db() as db:
        sales = db.execute(
            "SELECT product, quantity, total, created_at FROM sales ORDER BY created_at"
        ).fetchall()

    def generate():
        data = csv.writer([])
        yield "Product,Quantity,Total,Date\n"

        for s in sales:
            yield f"{s['product']},{s['quantity']},{s['total']},{s['created_at']}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=sales_report.csv"
        }
    )
# ================= SPLASH SCREEN =================
@app.route("/")
def splash():
    return render_template("splash.html")


# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE username=?",
                (u,)
            ).fetchone()

        if user and bcrypt.checkpw(p.encode(), user["password"]):
            session["user"] = u
            return redirect("/dashboard")
        else:
            flash("Invalid username or password")

    return render_template("login.html")


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if login_required():
        return redirect("/login")

    with get_db() as db:
        total_revenue = db.execute(
            "SELECT SUM(total) AS total FROM sales"
        ).fetchone()["total"] or 0

        total_products = db.execute(
            "SELECT COUNT(*) AS count FROM products"
        ).fetchone()["count"]

        total_sales = db.execute(
            "SELECT COUNT(*) AS count FROM sales"
        ).fetchone()["count"]

        low_stock = db.execute(
            "SELECT COUNT(*) AS count FROM products WHERE stock < 5"
        ).fetchone()["count"]

    return render_template(
        "dashboard.html",
        total_revenue=total_revenue,
        total_products=total_products,
        total_sales=total_sales,
        low_stock=low_stock
    )

# ================= PRODUCTS =================
@app.route("/products", methods=["GET", "POST"])
def products():
    if login_required():
        return redirect("/login")

    filter_stock = request.args.get("filter")

    if request.method == "POST":
        name = request.form["name"]
        price = request.form["price"]
        stock = request.form["stock"]

        with get_db() as db:
            db.execute(
                "INSERT INTO products VALUES (NULL, ?, ?, ?)",
                (name, price, stock)
            )

    with get_db() as db:
        if filter_stock == "low":
            items = db.execute(
                "SELECT * FROM products WHERE stock < 5"
            ).fetchall()
        else:
            items = db.execute(
                "SELECT * FROM products"
            ).fetchall()

    return render_template("products.html", items=items)
# ================= SALES =================
@app.route("/sales", methods=["GET", "POST"])
def sales():
    if login_required():
        return redirect("/login")

    with get_db() as db:
        products = db.execute(
            "SELECT name, price, stock FROM products"
        ).fetchall()

    if request.method == "POST":
        product_name = request.form["product"]
        qty = int(request.form["qty"])

        with get_db() as db:
            item = db.execute(
                "SELECT * FROM products WHERE name=?",
                (product_name,)
            ).fetchone()

            if item and item["stock"] >= qty:
                total = item["price"] * qty
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                db.execute(
                    "INSERT INTO sales VALUES (NULL, ?, ?, ?, ?)",
                    (item["name"], qty, total, now)
                )

                db.execute(
                    "UPDATE products SET stock=stock-? WHERE name=?",
                    (qty, item["name"])
                )
            else:
                flash("Not enough stock")

    with get_db() as db:
        records = db.execute(
            "SELECT * FROM sales ORDER BY created_at DESC"
        ).fetchall()

    return render_template(
        "sales.html",
        products=products,
        records=records
    )
# ================= REPORTS =================
@app.route("/reports", methods=["GET", "POST"])
def reports():
    if login_required():
        return redirect("/login")

    from_date = request.form.get("from_date")
    to_date = request.form.get("to_date")

    with get_db() as db:
        # Overall stats
        total_sales = db.execute(
            "SELECT SUM(total) AS total FROM sales"
        ).fetchone()["total"] or 0

        total_items = db.execute(
            "SELECT COUNT(*) AS count FROM products"
        ).fetchone()["count"]

        low_stock = db.execute(
            "SELECT name, stock FROM products WHERE stock < 5"
        ).fetchall()

        # Today & month
        today_sales = db.execute(
            "SELECT SUM(total) AS total FROM sales WHERE DATE(created_at)=DATE('now')"
        ).fetchone()["total"] or 0

        monthly_sales = db.execute(
            """
            SELECT SUM(total) AS total
            FROM sales
            WHERE strftime('%Y-%m', created_at)=strftime('%Y-%m','now')
            """
        ).fetchone()["total"] or 0

        # Filtered sales table
        if from_date and to_date:
            sales_data = db.execute(
                """
                SELECT * FROM sales
                WHERE DATE(created_at) BETWEEN ? AND ?
                ORDER BY created_at
                """,
                (from_date, to_date)
            ).fetchall()
        else:
            sales_data = db.execute(
                "SELECT * FROM sales ORDER BY created_at"
            ).fetchall()

        # 🔹 SALES TREND DATA (for line chart)
        trend_data = db.execute(
            """
            SELECT DATE(created_at) AS day, SUM(total) AS total
            FROM sales
            GROUP BY DATE(created_at)
            ORDER BY day
            """
        ).fetchall()

    # Prepare chart arrays
    trend_labels = [row["day"] for row in trend_data]
    trend_totals = [row["total"] for row in trend_data]

    return render_template(
        "reports.html",
        total_sales=total_sales,
        total_items=total_items,
        low_stock=low_stock,
        today_sales=today_sales,
        monthly_sales=monthly_sales,
        sales_data=sales_data,
        trend_labels=trend_labels,
        trend_totals=trend_totals
    )
# ================= INVOICE PDF =================
@app.route("/invoice/<int:sale_id>")
def invoice(sale_id):
    if login_required():
        return redirect("/login")

    with get_db() as db:
        sale = db.execute(
            "SELECT * FROM sales WHERE id=?",
            (sale_id,)
        ).fetchone()

    if not sale:
        return "Invoice not found"

    file = f"invoice_{sale_id}.pdf"
    c = canvas.Canvas(file, pagesize=A4)

    c.drawString(100, 800, "STOCKIFY - INVOICE")
    c.drawString(100, 770, f"Invoice ID: {sale_id}")
    c.drawString(100, 740, f"Product: {sale['product']}")
    c.drawString(100, 720, f"Quantity: {sale['quantity']}")
    c.drawString(100, 700, f"Total: ₹ {sale['total']}")
    c.drawString(100, 670, f"Date: {sale['created_at']}")
    c.drawString(100, 630, "Thank you for your business!")

    c.save()

    return send_file(file, as_attachment=True)



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

