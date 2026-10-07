from flask import Flask, render_template, request, redirect, url_for
import os
from supabase import create_client, Client

app = Flask(__name__)

# Credenciales de Supabase mediante API HTTP (evita bloqueos de puertos en Render)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Si pusiste la URL en DATABASE_URL por error, la rescatamos automáticamente por si acaso:
if not SUPABASE_URL and os.environ.get("DATABASE_URL", "").startswith("http"):
    SUPABASE_URL = os.environ.get("DATABASE_URL")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Filtro personalizado para moneda chilena ($)
@app.template_filter('clp')
def formato_clp(value):
    try:
        return f"${int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

@app.route('/')
def index():
    try:
        res_trabajos = supabase.table("trabajos").select("*").execute()
        trabajos = res_trabajos.data if res_trabajos.data else []

        res_gastos = supabase.table("gastos_fijos").select("*").execute()
        gastos_fijos = res_gastos.data if res_gastos.data else []
    except Exception as e:
        print("Error al consultar Supabase:", e)
        trabajos = []
        gastos_fijos = []

    # Cálculos financieros
    total_ingresos = sum(float(t.get('monto_neto', 0)) for t in trabajos if t.get('estado') == 'Pagado')
    total_pendientes = sum(float(t.get('monto_neto', 0)) for t in trabajos if t.get('estado') == 'Pendiente')
    
    total_egresos_trabajos = sum(float(t.get('gastos_op', 0)) + float(t.get('viaticos', 0)) for t in trabajos)
    total_gastos_fijos = sum(float(g.get('monto', 0)) for g in gastos_fijos)
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
    try:
        supabase.table("trabajos").insert({
            "n_factura": request.form.get('n_factura'),
            "fecha": request.form.get('fecha'),
            "cliente": request.form.get('cliente'),
            "equipo": request.form.get('equipo'),
            "servicio": request.form.get('servicio'),
            "monto_neto": float(request.form.get('monto_neto', 0)),
            "gastos_op": float(request.form.get('gastos_op', 0)),
            "viaticos": float(request.form.get('viaticos', 0)),
            "estado": request.form.get('estado')
        }).execute()
    except Exception as e:
        print("Error al guardar trabajo:", e)

    return redirect(url_for('index'))

@app.route('/guardar_gasto_fijo', methods=['POST'])
def guardar_gasto_fijo():
    try:
        supabase.table("gastos_fijos").insert({
            "concepto": request.form.get('concepto'),
            "monto": float(request.form.get('monto', 0)),
            "mes": request.form.get('mes')
        }).execute()
    except Exception as e:
        print("Error al guardar gasto fijo:", e)

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
