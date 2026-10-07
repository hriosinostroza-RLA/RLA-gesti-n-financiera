import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL and os.environ.get("DATABASE_URL", "").startswith("http"):
    SUPABASE_URL = os.environ.get("DATABASE_URL")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.template_filter('clp')
def formato_clp(value):
    try:
        return f"${int(value):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

@app.route('/')
def index():
    datos = []
    try:
        response = supabase.table("trabajos").select("*").execute()
        if response.data:
            for item in response.data:
                neto_val = float(item.get('neto') if item.get('neto') is not None else item.get('monto_neto', 0))
                item['neto'] = neto_val
                item['monto_neto'] = neto_val
                # Calculamos el 19% de IVA por cada registro
                item['iva'] = neto_val * 0.19
                item['total_bruto'] = neto_val * 1.19
            datos = response.data
    except Exception as e:
        print(f"Error al consultar Supabase: {e}")

    # Ingresos con IVA incluido (Bruto) para los pagados/completados
    total_ingresos = sum(float(item.get('total_bruto', 0)) for item in datos if str(item.get('estado', '')).lower() in ['pagado', 'completado'])
    total_pendientes = sum(float(item.get('total_bruto', 0)) for item in datos if str(item.get('estado', '')).lower() not in ['pagado', 'completado'])
    egresos = sum(float(item.get('gastos_op') or 0) for item in datos)
    capital_disponible = total_ingresos - egresos

    return render_template(
        'index.html',
        datos=datos,
        total_ingresos=total_ingresos,
        total_pendientes=total_pendientes,
        por_cobrar=total_pendientes,
        egresos=egresos,
        total_egresos=egresos,
        capital_disponible=capital_disponible
    )

@app.route('/agregar_trabajo', methods=['POST'])
@app.route('/guardar_trabajo', methods=['POST'])
def agregar_trabajo():
    try:
        nuevo_trabajo = {
            "n_factura": request.form.get('factura', ''),
            "fecha": request.form.get('fecha', ''),
            "cliente": request.form.get('cliente', ''),
            "equipo": request.form.get('equipo', ''),
            "servicio": request.form.get('servicio', ''),
            "neto": float(request.form.get('monto_neto') or 0),
            "gastos_op": float(request.form.get('gastos_op') or 0),
            "viaticos": float(request.form.get('viaticos') or 0),
            "estado": request.form.get('estado', 'Pendiente')
        }
        supabase.table("trabajos").insert(nuevo_trabajo).execute()
    except Exception as e:
        print(f"Error al guardar el trabajo en Supabase: {e}")
    
    return redirect(url_for('index'))

@app.route('/agregar_gasto', methods=['POST'])
@app.route('/guardar_gasto', methods=['POST'])
def agregar_gasto():
    try:
        nuevo_gasto = {
            "concepto": request.form.get('concepto', ''),
            "monto": float(request.form.get('monto') or 0),
            "periodo": request.form.get('periodo', '')
        }
        supabase.table("gastos_fijos").insert(nuevo_gasto).execute()
    except Exception as e:
        print(f"Error al guardar el gasto fijo en Supabase: {e}")
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
