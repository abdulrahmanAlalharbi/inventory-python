import mysql.connector
from flask import Flask, render_template, request, redirect, abort, flash, url_for
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ["FLASK_SECRET_KEY"]


# الاتصال بقاعدة البيانات
def get_connection():
    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"]
    )

# الصفحة الرئيسية والبحث عن المنتجات
@app.route("/")
def home():
    search = request.args.get("search", "").strip()

    connection = get_connection()
    cursor = connection.cursor()

    if search:
        cursor.execute(
            """
            SELECT * FROM products
WHERE is_active = TRUE
AND (
    products_Name LIKE %s
    OR product_id = %s
)
            """,
            (
                "%" + search + "%",
                int(search) if search.isdigit() else -1
            )
        )
    else:
        cursor.execute("""
    SELECT
        p.product_ID,
        p.products_Name,
        p.quantity AS opening_quantity,
        p.unit_price,
        p.quantity + COALESCE(
            SUM(
                CASE
                    WHEN sm.movement_type = 'IN'
                        THEN sm.quantity
                    WHEN sm.movement_type = 'OUT'
                        THEN -sm.quantity
                    ELSE 0
                END
            ), 0
        ) AS current_stock
    FROM products p
    LEFT JOIN stock_movements sm
        ON p.product_ID = sm.product_ID
        WHERE p.is_active = TRUE
    GROUP BY
        p.product_ID,
        p.products_Name,
        p.quantity,
        p.unit_price
    ORDER BY p.product_ID
""")

    results = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "Index.html",
        products=results,
        search=search
    )






# إضافة منتج جديد
@app.route("/add_product", methods=["POST"])
def add_product():
    products_Name = request.form["products_Name"]
    quantity = int(request.form["quantity"])
    unit_price = float(request.form["unit_price"])

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO products
        (products_Name, quantity, unit_price)
        VALUES (%s, %s, %s)
        """,
        (products_Name, quantity, unit_price)
    )

    connection.commit()
    cursor.close()
    connection.close()

    return redirect("/")


# تعديل منتج موجود
@app.route("/edit_product/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):

    connection = get_connection()
    cursor = connection.cursor()

    if request.method == "POST":

        products_Name = request.form["products_Name"].strip()
        unit_price = float(request.form["unit_price"])

        if not products_Name or unit_price < 0:
            cursor.close()
            connection.close()
            flash("يرجى إدخال بيانات صحيحة", "error")
            return redirect(url_for("edit_product", product_id=product_id))

        cursor.execute(
            """
            UPDATE products
            SET products_Name = %s,
                unit_price = %s
            WHERE product_id = %s
            """,
            (products_Name, unit_price, product_id)
        )

        connection.commit()
        cursor.close()
        connection.close()

        flash("تم تعديل بيانات المنتج بنجاح", "success")
        return redirect("/")

    cursor.execute(
        "SELECT * FROM products WHERE product_id = %s",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    connection.close()

    if product is None:
        abort(404)

    return render_template(
        "edit_product.html",
        product=product
    )

@app.route("/delete_product/<int:product_id>", methods=["POST"])
def delete_product(product_id):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # التأكد من وجود المنتج
        cursor.execute(
            "SELECT quantity FROM products WHERE product_id = %s",
            (product_id,)
        )
        product = cursor.fetchone()

        if product is None:
            flash("المنتج غير موجود", "error")
            return redirect("/")

        # التأكد من عدم وجود حركات سابقة
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM stock_movements
            WHERE product_id = %s
            """,
            (product_id,)
        )
        movements_count = cursor.fetchone()[0]

        if product[0] != 0 or movements_count > 0:
            flash(
                "لا يمكن حذف المنتج لوجود رصيد أو حركات مخزون سابقة",
                "error"
            )
            return redirect("/")

        cursor.execute(
            "DELETE FROM products WHERE product_id = %s",
            (product_id,)
        )

        connection.commit()
        flash("تم حذف المنتج بنجاح", "success")

    except Exception as e:
        connection.rollback()
        print("DELETE ERROR:", e)
        flash("حدث خطأ أثناء حذف المنتج", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect("/")

#انشاء مسار للارشفة
@app.route("/archive_product/<int:product_id>", methods=["POST"])
def archive_product(product_id):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE products
            SET is_active = FALSE
            WHERE product_id = %s
            """,
            (product_id,)
        )

        connection.commit()

        flash("تمت أرشفة المنتج بنجاح", "success")

    except Exception as e:
        connection.rollback()
        print("ARCHIVE ERROR:", e)
        flash("حدث خطأ أثناء أرشفة المنتج", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect("/")


#انشاء صفحة المنتجات المؤرشفة
@app.route("/archived_products")
def archived_products():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM products
        WHERE is_active = FALSE
    """)

    products = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "archived_products.html",
        products=products
    )

##استعادة المنتج
@app.route("/restore_product/<int:product_id>", methods=["POST"])
def restore_product(product_id):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE products
        SET is_active = TRUE
        WHERE product_id = %s
    """, (product_id,))

    connection.commit()

    cursor.close()
    connection.close()

    return redirect("/archived_products")



##انشاء صفحة سجل الحركات
@app.route("/movement_history")
def movement_history():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            sm.movement_ID,
            p.products_Name,
            sm.movement_type,
            sm.quantity,
            sm.movement_date
        FROM stock_movements sm
        JOIN products p
            ON sm.product_ID = p.product_ID
        ORDER BY sm.movement_date DESC
    """)

    movements = cursor.fetchall()

    cursor.close()
    connection.close()

    return render_template(
        "movement_history.html",
        movements=movements
    )






@app.route("/stock_movement", methods=["POST"])
def stock_movement():
    if request.method != "POST":
        return redirect("/")
    connection =None
    cursor = None

    try:
        product_id = int(request.form["product_id"])
        movement_type = request.form["movement_type"]
        quantity = int(request.form["quantity"])

        if quantity <= 0 or movement_type not in ("IN", "OUT"):
            flash("نوع الحركة أو الكمية غير صحيحة", "error")
            return redirect("/")

        
        connection=get_connection()
        cursor = connection.cursor()

        # جلب الرصيد الافتتاحي للمنتج
        cursor.execute(
            "SELECT quantity FROM products WHERE product_ID = %s",
            (product_id,)
        )
        product = cursor.fetchone()

        if product is None:
            cursor.close()
            connection.close()
            flash("المنتج غير موجود", "error")
            return redirect("/")

        opening_quantity = product[0]

        # حساب الرصيد الحالي من جميع الحركات السابقة
        cursor.execute(
            """
            SELECT COALESCE(
                SUM(
                    CASE
                        WHEN movement_type = 'IN' THEN quantity
                        WHEN movement_type = 'OUT' THEN -quantity
                        ELSE 0
                    END
                ), 0
            )
            FROM stock_movements
            WHERE product_id = %s
            """,
            (product_id,)
        )

        movement_result = cursor.fetchone()
        movement_total = movement_result[0] or 0
        current_stock = opening_quantity + movement_total

        # منع الصرف إذا كانت الكمية غير كافية
        if movement_type == "OUT" and quantity > current_stock:
            cursor.close()
            connection.close()

            return redirect(
                url_for(
                    "home",
                    stock_error=1,
                    available=current_stock,
                    requested=quantity

                    
                )

            )
            

        # تسجيل حركة المخزون
        cursor.execute(
            """
            INSERT INTO stock_movements
                (product_id, movement_type, quantity)
            VALUES (%s, %s, %s)
            """,
            (product_id, movement_type, quantity)
        )

        connection.commit()
        cursor.close()
        connection.close()

        flash("تم تسجيل حركة المخزون بنجاح", "success")
        return redirect("/")



    except Exception as e:
        print("STOCK MOVEMENT ERROR:", repr(e))

    if connection is not None:
        try:
            connection.rollback()
        except Exception:
            pass

    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass

    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass

    flash("تعذر تسجيل حركة المخزون، راجع Terminal", "error")
    return redirect("/")

    




# تشغيل البرنامج
if __name__ == "__main__":
    app.run(debug=True)