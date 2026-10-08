from flask import Flask, render_template, request, redirect, url_for
# Importa tu conexión o base de datos según corresponda (ej. SQLAlchemy, sqlite3, etc.)

app = Flask(__name__)

# Filtro personalizado para moneda chilena (CLP)
@app.template_filter('clp')
def format_clp(value):
    try:
        val = float(value)
        return f"${val:,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

@app.route('/')
def index():
    # Aquí debes cargar tus listas de datos desde tu base de datos:
    # 'datos' -> lista de trabajos/servicios
    # 'gastos' -> lista de gastos fijos
    # Y calcular tus totales correspondientes.
    return render_template('index.html', datos=[], gastos=[], total_ingresos=0, total_pendientes=0, total_egresos=0, capital_disponible=0)

@app.route('/agregar_trabajo', methods=['POST'])
def agregar_trabajo():
    # Lógica para recibir e insertar el trabajo en la base de datos
    n_factura = request.form.get('factura')
    fecha = request.form.get('fecha')
    cliente = request.form.get('cliente')
    equipo = request.form.get('equipo')
    servicio = request.form.get('servicio')
    monto_neto = float(request.form.get('monto_neto', 0))
    gastos_op = float(request.form.get('gastos_op', 0))
    viaticos = float(request.form.get('viaticos', 0))
    estado = request.form.get('estado')
    
    # [Tu código de inserción aquí]
    return redirect(url_for('index'))

@app.route('/agregar_gasto', methods=['POST'])
def agregar_gasto():
    concepto = request.form.get('concepto')
    monto = float(request.form.get('monto', 0))
    # Captura flexible para evitar que quede vacío sin importar si se envió como 'mes' o 'periodo'
    periodo = request.form.get('mes') or request.form.get('periodo') or 'Sin Especificar'
    
    # [Tu código de inserción en la base de datos para los gastos fijos]
    return redirect(url_for('index'))

@app.route('/editar_gasto/<int:id>', methods=['GET', 'POST'])
def editar_gasto(id):
    if request.method == 'POST':
        # Lógica para actualizar el gasto fijo
        return redirect(url_for('index'))
    # Lógica para mostrar formulario de edición
    return "Formulario de edición de gasto"

if __name__ == '__main__':
    app.run(debug=True)
