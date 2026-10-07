from flask import Flask, render_template, request, redirect, url_for
import os
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_flash'

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL", "")
    # Render bloquea el puerto 5432 en cuentas gratuitas; cambiamos al puerto 6543 (pooler)
    if ":5432" in db_url:
        db_url = db_url.replace(":5432", ":6543")
    
    conn = psycopg2.connect(db_url, sslmode='require')
    return conn

# Crear tablas automáticamente si no existen
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS trabajos (
                id SERIAL PRIMARY KEY,
                n_factura VARCHAR(50),
                fecha VARCHAR(50),
                cliente VARCHAR(150),
                equipo VARCHAR(150),
                servicio TEXT,
                monto_neto NUMERIC,
                gastos_op NUMERIC DEFAULT 0,
                viaticos NUMERIC DEFAULT 0,
                estado VARCHAR(50)
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS gastos_fijos (
                id SERIAL PRIMARY KEY,
                concepto VARCHAR(150),
                monto NUMERIC,
                mes VARCHAR(50)
            )
        ''')
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Error inicializando la base de datos:", e)

init_db()

# Filtro para moneda chilena
@app.template_filter('clp')
def formato_clp(value):
    try:
        return f"${int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

@app.route('/')
def index():
    trabajos = []
    gastos_fijos = []
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        cur.execute("SELECT * FROM trabajos ORDER BY id DESC")
        trabajos = cur.fetchall()
        
        cur.execute("SELECT * FROM gastos_fijos ORDER BY id DESC")
        gastos_fijos = cur.fetchall()
        
        cur.close()
        conn.close()
    except Exception as e:
        print("Error al consultar la base de datos:", e)

    total_ingresos = sum(float(t['monto_neto'] or 0) for t in trabajos if t['estado'] == 'Pagado')
    total_pendientes = sum(float(t['monto_neto'] or 0) for t in trabajos if t['estado'] == 'Pendiente')
    
    total_egresos_trabajos = sum(float(t['gastos_op'] or 0) + float(t['viaticos'] or 0) for t in trabajos)
    total_gastos_fijos = sum(float(g['monto'] or 0) for g in gastos_fijos)
    total_egresos = total_egresos_trabajos + total_gastos_fijos
    
    capital_disponible = total_ingresos - total_egresos

    return render_template('index.html',
                           total_ingresos=total_ingresos,
                           total_pendientes=total_pendientes,
                           total_egresos=total_egresos,
                           capital_disponible=capital_disponible,
                           trabajos=trabajos,
                           gastos_fijos=gastos_fijos)

@app.route('/guardar_trabajo', methods=['POST'])
def guardar_trabajo():
    n_factura = request.form.get('n_factura')
    fecha = request.form.get('fecha')
    cliente = request.form.get('cliente')
    equipo = request.form.get('equipo')
    servicio = request.form.get('servicio')
    monto_neto = float(request.form.get('monto_neto', 0))
    gastos_op = float(request.form.get('gastos_op', 0))
    viaticos = float(request.form.get('viaticos', 0))
    estado = request.form.get('estado')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trabajos (n_factura, fecha, cliente, equipo, servicio, monto_neto, gastos_op, viaticos, estado) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (n_factura, fecha, cliente, equipo, servicio, monto_neto, gastos_op, viaticos, estado)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Error al guardar trabajo:", e)

    return redirect(url_for('index'))

@app.route('/guardar_gasto_fijo', methods=['POST'])
def guardar_gasto_fijo():
    concepto = request.form.get('concepto')
    monto = float(request.form.get('monto', 0))
    mes = request.form.get('mes')

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO gastos_fijos (concepto, monto, mes) VALUES (%s, %s, %s)",
            (concepto, monto, mes)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Error al guardar gasto fijo:", e)

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
