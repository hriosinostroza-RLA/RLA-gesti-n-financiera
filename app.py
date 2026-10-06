import os
from datetime import datetime
from dateutil.relativedelta import relativedelta
from flask import Flask, render_template, request, redirect, url_for, flash
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = 'clave_secreta_para_flash'

# URL de conexión a Supabase (PostgreSQL) o fallback local
DATABASE_URL = os.environ.get('https://wdwxzftbpqdnesrzpzmq.supabase.co', 'postgresql://postgres:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Indkd3h6ZnRicHFkbmVzcnpwem1xIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTEzMjYxNjIsImV4cCI6MjEwNjkwMjE2Mn0.MnkwqiHPYgBi7_pr3xylvRpo8OTrA6pOPh6aPqMLHBQ')

@app.template_filter('clp')
def formato_clp(valor):
    try:
        valor = float(valor or 0)
        return f"${valor:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

def obtener_conexion():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

@app.route('/')
def index():
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        
        # 1. Totales de Ingresos (Solo 'Pagado')
        cursor.execute("SELECT SUM(neto) FROM trabajos WHERE estado = 'Pagado'")
        res_ingresos = cursor.fetchone()
        total_ingresos = float(res_ingresos['sum'] or 0) if res_ingresos and res_ingresos['sum'] is not None else 0.0

        # 2. Totales por Cobrar (Pendientes)
        cursor.execute("SELECT SUM(neto) FROM trabajos WHERE estado = 'Pendiente'")
        res_pendientes = cursor.fetchone()
        total_pendientes = float(res_pendientes['sum'] or 0) if res_pendientes and res_pendientes['sum'] is not None else 0.0

        # 3. Gastos Operativos & Viáticos Totales
        cursor.execute("SELECT SUM(gastos_op + viaticos) FROM trabajos")
        res_gastos_op = cursor.fetchone()
        total_gastos_op = float(res_gastos_op['sum'] or 0) if res_gastos_op and res_gastos_op['sum'] is not None else 0.0

        # 4. Gastos Fijos Totales
        cursor.execute("SELECT SUM(monto) FROM gastos_fijos")
        res_gastos_fijos = cursor.fetchone()
        total_gastos_fijos = float(res_gastos_fijos['sum'] or 0) if res_gastos_fijos and res_gastos_fijos['sum'] is not None else 0.0

        # 5. Capital Disponible
        capital_disponible = total_ingresos - (total_gastos_op + total_gastos_fijos)

        # 6. Listados
        cursor.execute("SELECT * FROM trabajos ORDER BY id DESC")
        trabajos = cursor.fetchall()

        cursor.execute("SELECT * FROM gastos_fijos ORDER BY id DESC")
        gastos_fijos = cursor.fetchall()

        # 7. Edición de Trabajo
        edit_id = request.args.get('edit_id')
        edit_trabajo = None
        if edit_id:
            cursor.execute("SELECT * FROM trabajos WHERE id = %s", (edit_id,))
            edit_trabajo = cursor.fetchone()

        current_month = datetime.now().strftime('%Y-%m')

        # 8. Gráfico: Siempre los últimos 12 meses exactos
        current_date = datetime.now()
        meses_12_keys = []
        for i in range(11, -1, -1):
            m = current_date - relativedelta(months=i)
            meses_12_keys.append(m.strftime('%Y-%m'))

        cursor.execute("""
            SELECT SUBSTR(fecha, 1, 7) as mes, 
                   SUM(CASE WHEN estado = 'Pagado' THEN neto ELSE 0 END) as ingresos,
                   SUM(gastos_op + viaticos) as egresos
            FROM trabajos 
            GROUP BY mes
        """)
        db_rows = cursor.fetchall()
        db_res = {row['mes']: {'ingresos': float(row['ingresos'] or 0), 'egresos': float(row['egresos'] or 0)} for row in db_rows}

        meses_grafico = []
        for mes_str in meses_12_keys:
            data = db_res.get(mes_str, {'ingresos': 0.0, 'egresos': 0.0})
            meses_grafico.append({
                'mes': mes_str,
                'ingresos': data['ingresos'],
                'egresos': data['egresos']
            })

        return render_template('index.html', 
                               total_ingresos=total_ingresos, 
                               total_gastos_op=total_gastos_op, 
                               total_gastos_fijos=total_gastos_fijos, 
                               total_pendientes=total_pendientes,
                               capital_disponible=capital_disponible,
                               trabajos=trabajos,
                               gastos_fijos=gastos_fijos,
                               edit_trabajo=edit_trabajo,
                               current_month=current_month,
                               meses_grafico=meses_grafico)
        
    except Exception as e:
        print(f"Error: {e}")
        return render_template('index.html', 
                               total_ingresos=0.0, total_gastos_op=0.0, total_gastos_fijos=0.0, 
                               total_pendientes=0.0, capital_disponible=0.0, trabajos=[], gastos_fijos=[],
                               edit_trabajo=None, current_month=datetime.now().strftime('%Y-%m'), meses_grafico=[])
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/guardar_trabajo', methods=['POST'])
def guardar_trabajo():
    conn = None
    cursor = None
    try:
        trabajo_id = request.form.get('id')
        n_factura = request.form.get('n_factura')
        fecha = request.form.get('fecha')
        cliente = request.form.get('cliente')
        equipo = request.form.get('equipo')
        servicio = request.form.get('servicio')
        neto = float(request.form.get('neto') or 0)
        gastos_op = float(request.form.get('gastos_op') or 0)
        viaticos = float(request.form.get('viaticos') or 0)
        estado = request.form.get('estado')

        conn = obtener_conexion()
        cursor = conn.cursor()

        if trabajo_id and trabajo_id.strip() != '':
            cursor.execute("""
                UPDATE trabajos 
                SET n_factura = %s, fecha = %s, cliente = %s, equipo = %s, servicio = %s, neto = %s, gastos_op = %s, viaticos = %s, estado = %s
                WHERE id = %s
            """, (n_factura, fecha, cliente, equipo, servicio, neto, gastos_op, viaticos, estado, trabajo_id))
            flash('Factura actualizada correctamente.', 'success')
        else:
            cursor.execute("""
                INSERT INTO trabajos (n_factura, fecha, cliente, equipo, servicio, neto, gastos_op, viaticos, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (n_factura, fecha, cliente, equipo, servicio, neto, gastos_op, viaticos, estado))
            flash('Trabajo registrado exitosamente.', 'success')

        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        flash(f'Error: {e}', 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('index'))

@app.route('/guardar_gasto_fijo', methods=['POST'])
def guardar_gasto_fijo():
    conn = None
    cursor = None
    try:
        mes = request.form.get('mes')
        concepto = request.form.get('concepto')
        monto = float(request.form.get('monto') or 0)
        observacion = request.form.get('observacion')

        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO gastos_fijos (mes, concepto, monto, observacion) VALUES (%s, %s, %s, %s)", (mes, concepto, monto, observacion))
        conn.commit()
        flash('Gasto fijo registrado.', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash('Error al procesar gasto.', 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('index'))

@app.route('/eliminar_trabajo/<int:id>')
def eliminar_trabajo(id):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trabajos WHERE id = %s", (id,))
        conn.commit()
        flash('Trabajo eliminado.', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash('Error al eliminar.', 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('index'))

@app.route('/eliminar_gasto/<int:id>')
def eliminar_gasto(id):
    conn = None
    cursor = None
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM gastos_fijos WHERE id = %s", (id,))
        conn.commit()
        flash('Gasto eliminado.', 'success')
    except Exception as e:
        if conn: conn.rollback()
        flash('Error al eliminar.', 'danger')
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
