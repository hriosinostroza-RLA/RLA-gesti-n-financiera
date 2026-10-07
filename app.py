import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Credenciales de Supabase mediante API HTTP
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Rescate automático por si se configuró en DATABASE_URL por error
if not SUPABASE_URL and os.environ.get("DATABASE_URL", "").startswith("http"):
    SUPABASE_URL = os.environ.get("DATABASE_URL")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Filtro personalizado para moneda chilena ($) con formato de puntos
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
        # Consulta la tabla de trabajos/servicios en Supabase
        response = supabase.table("trabajos").select("*").execute()
        if response.data:
            datos = response.data
    except Exception as e:
        print(f"Error al consultar Supabase: {e}")

    # Cálculos dinámicos para las tarjetas del panel financiero
    total_ingresos = sum(float(item.get('monto_neto', 0)) for item in datos if str(item.get('estado', '')).lower() in ['pagado', 'completado'])
    total_pendientes = sum(float(item.get('monto_neto', 0)) for item in datos if str(item.get('estado', '')).lower() not in ['pagado', 'completado'])
    egresos = sum(float(item.get('gastos_op', 0)) for item in datos)
    capital_disponible = total_ingresos - egresos

    return render_template(
        'index.html',
        datos=datos,
        total_ingresos=total_ingresos,
        total_pendientes=total_pendientes,
        por_cobrar=total_pendientes,  # Alias por si tu HTML usa por_cobrar
        egresos=egresos,
        capital_disponible=capital_disponible
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
