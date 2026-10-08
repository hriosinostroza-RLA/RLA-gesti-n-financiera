import os
from datetime import datetime, date
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
    datos_trabajos = []
    datos_gastos = []
    hoy = date.today()

    # 1. Obtener Trabajos (Plazo de edición: 10 días)
    try:
        resp_trabajos = supabase.table("trabajos").select("*").execute()
        if resp_trabajos.data:
            for item in resp_trabajos.data:
                neto_val = float(item.get('neto') if item.get('neto') is not None else item.get('monto_neto', 0))
                item['neto'] = neto_val
                item['monto_neto'] = neto_val
                item['iva'] = neto_val * 0.19
                item['total_bruto'] = neto_val * 1.19
                
                editable = False
                fecha_ref = item.get('created_at') or item.get('fecha', '')
                if fecha_ref:
                    try:
                        f_reg = datetime.strptime(fecha_ref.split('T')[0], '%Y-%m-%d').date()
                        dias_transcurridos = (hoy - f_reg).days
                        if 0 <= dias_transcurridos <= 10:
                            editable = True
                    except Exception:
                        pass
                item['editable'] = editable

            datos_trabajos = resp_trabajos.data
    except Exception as e:
        print(f"Error al consultar trabajos en Supabase: {e}")

    # 2. Obtener Gastos Fijos (Plazo de edición: 10 días)
    try:
        resp_gastos = supabase.table("gastos_fijos").select("*").execute()
        if resp_gastos.data:
            for item in resp_gastos.data:
                mes_val = item.get('mes') if item.get('mes') is not None else item.get('periodo', '')
                item['mes'] = mes_val
                item['periodo'] = mes_val
                
                editable = False
                fecha_ref = item.get('created_at', '')
                if fecha_ref:
                    try:
                        f_reg = datetime.strptime(fecha_ref.split('T')[0], '%Y-%m-%d').date()
                        dias_transcurridos = (hoy - f_reg).days
                        if 0 <= dias_transcurridos <= 10:
                            editable = True
                    except Exception:
                        pass
                else:
                    # Si no tiene created_at registrado, permitimos editar por defecto o ajustamos
                    editable = True
                item['editable'] = editable

            datos_gastos = resp_gastos.data
    except Exception as e:
        print(f"Error al consultar gastos fijos en Supabase: {e}")

    # Cálculos financieros
    total_ingresos = sum(float(item.get('total_bruto', 0)) for item in datos_trabajos if str(item.get('estado', '')).lower() in ['pagado', 'completado'])
    total_pendientes = sum(float(item.get('total_bruto', 0)) for item in datos_trabajos if str(item.get('estado', '')).lower() not in ['pagado', 'completado'])
    
    total_gastos_op = sum(float(item.get('gastos_op') or 0) for item in datos_trabajos)
    total_gastos_fijos = sum(float(item.get('monto') or 0) for item in datos_gastos)
    egresos = total_gastos_op + total_gastos_fijos

    capital_disponible = total_ingresos - egresos

    return render_template(
        'index.html',
        datos=datos_trabajos,
        gastos=datos_gastos,
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
            "estado": request.form.get('estado', 'Pendiente'),
            "created_at": datetime.now().isoformat()
        }
        supabase.table("trabajos").insert(nuevo_trabajo).execute()
    except Exception as e:
        print(f"Error al guardar el trabajo en Supabase: {e}")
    
    return redirect(url_for('index'))

@app.route('/marcar_pagado/<int:id>', methods=['POST'])
def marcar_pagado(id):
    try:
        supabase.table("trabajos").update({"estado": "Pagado"}).eq("id", id).execute()
    except Exception as e:
        print(f"Error al actualizar estado a pagado: {e}")
    return redirect(url_for('index'))

@app.route('/agregar_gasto', methods=['POST'])
@app.route('/guardar_gasto', methods=['POST'])
def agregar_gasto():
    try:
        nuevo_gasto = {
            "concepto": request.form.get('concepto', ''),
            "monto": float(request.form.get('monto') or 0),
            "mes": request.form.get('periodo', ''),
            "created_at": datetime.now().isoformat()
        }
        supabase.table("gastos_fijos").insert(nuevo_gasto).execute()
    except Exception as e:
        print(f"Error al guardar el gasto fijo en Supabase: {e}")
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
