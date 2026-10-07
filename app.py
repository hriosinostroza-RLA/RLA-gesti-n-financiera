import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from supabase import create_client, Client

app = Flask(__name__)

# Credenciales de Supabase mediante API HTTP (evita bloqueos de puertos en Render)
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
    try:
        # Ejemplo de consulta a una tabla de Supabase (ajusta el nombre de tu tabla si es necesario)
        # response = supabase.table("transacciones").select("*").execute()
        # datos = response.data
        datos = []
        return render_template('index.html', datos=datos)
    except Exception as e:
        return render_template('index.html', datos=[], error=str(e))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
