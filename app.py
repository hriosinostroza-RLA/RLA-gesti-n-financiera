import os
import io
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, send_file
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

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

    # 1. Obtener Trabajos
    try:
        resp_trabajos = supabase.table("trabajos").select("*").execute()
        if resp_trabajos.data:
            for item in resp_trabajos.data:
                neto_val = float(item.get('neto') if item.get('neto') is not None else item.get('monto_neto', 0))
                item['neto'] = neto_val
                item['monto_neto'] = neto_val
                item['iva'] = neto_val * 0.19
                item['total_bruto'] = neto_val * 1.19
                item['editable'] = True
            datos_trabajos = resp_trabajos.data
    except Exception as e:
        print(f"Error al consultar trabajos en Supabase: {e}")

    # 2. Obtener Gastos Fijos
    try:
        resp_gastos = supabase.table("gastos_fijos").select("*").execute()
        if resp_gastos.data:
            for item in resp_gastos.data:
                mes_val = item.get('mes') if item.get('mes') is not None else item.get('periodo', '')
                item['mes'] = mes_val
                item['periodo'] = mes_val
                item['editable'] = True
            datos_gastos = resp_gastos.data
    except Exception as e:
        print(f"Error al consultar gastos fijos en Supabase: {e}")

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

@app.route('/exportar_pdf')
def exportar_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#22252a'), spaceAfter=12)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#444444'), spaceAfter=6, spaceBefore=12)
    normal_style = styles['Normal']

    elements.append(Paragraph("<b>RLA | Gestión Financiera y Técnica</b>", title_style))
    elements.append(Paragraph(f"Reporte generado el: {date.today().strftime('%d-%m-%Y')}", normal_style))
    elements.append(Spacer(1, 15))

    try:
        resp_trabajos = supabase.table("trabajos").select("*").execute()
        datos_trabajos = resp_trabajos.data if resp_trabajos.data else []
    except Exception:
        datos_trabajos = []

    try:
        resp_gastos = supabase.table("gastos_fijos").select("*").execute()
        datos_gastos = resp_gastos.data if resp_gastos.data else []
    except Exception:
        datos_gastos = []

    # Tabla Trabajos PDF
    elements.append(Paragraph("<b>Historial de Trabajos y Servicios</b>", subtitle_style))
    t_data = [["Factura", "Fecha", "Cliente", "Equipo", "Neto", "Estado"]]
    for item in datos_trabajos:
        neto_val = item.get('neto') or item.get('monto_neto', 0)
        t_data.append([
            str(item.get('n_factura', '')),
            str(item.get('fecha', '')),
            str(item.get('cliente', '')),
            str(item.get('equipo', '')),
            f"${int(neto_val):,}".replace(",", "."),
            str(item.get('estado', ''))
        ])
    
    t_table = Table(t_data, colWidths=[55, 65, 100, 110, 80, 80])
    t_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#22252a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dcdcdc'))
    ]))
    elements.append(t_table)
    elements.append(Spacer(1, 15))

    # Tabla Gastos Fijos PDF
    elements.append(Paragraph("<b>Historial de Gastos Fijos</b>", subtitle_style))
    g_data = [["Concepto", "Periodo / Mes", "Monto"]]
    for gasto in datos_gastos:
        g_data.append([
            str(gasto.get('concepto', '')),
            str(gasto.get('mes', '') or gasto.get('periodo', '')),
            f"${int(gasto.get('monto', 0)):,}".replace(",", ".")
        ])
    
    g_table = Table(g_data, colWidths=[200, 150, 140])
    g_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#22252a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dcdcdc'))
    ]))
    elements.append(g_table)

    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"Reporte_Financiero_RLA_{date.today().strftime('%Y-%m-%d')}.pdf", mimetype='application/pdf')

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

@app.route('/editar_trabajo/<int:id>', methods=['GET', 'POST'])
def editar_trabajo(id):
    if request.method == 'POST':
        try:
            datos_actualizados = {
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
            supabase.table("trabajos").update(datos_actualizados).eq("id", id).execute()
        except Exception as e:
            print(f"Error al actualizar trabajo: {e}")
        return redirect(url_for('index'))
    
    try:
        resp = supabase.table("trabajos").select("*").eq("id", id).execute()
        trabajo = resp.data[0] if resp.data else None
        if trabajo:
            neto_val = trabajo.get('neto') if trabajo.get('neto') is not None else trabajo.get('monto_neto', 0)
            trabajo['monto_neto'] = neto_val
    except Exception as e:
        print(f"Error al obtener trabajo para editar: {e}")
        trabajo = None

    return render_template('editar_trabajo.html', trabajo=trabajo)

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

@app.route('/editar_gasto/<int:id>', methods=['GET', 'POST'])
def editar_gasto(id):
    if request.method == 'POST':
        try:
            datos_actualizados = {
                "concepto": request.form.get('concepto', ''),
                "monto": float(request.form.get('monto') or 0),
                "mes": request.form.get('periodo', '')
            }
            supabase.table("gastos_fijos").update(datos_actualizados).eq("id", id).execute()
        except Exception as e:
            print(f"Error al actualizar gasto fijo: {e}")
        return redirect(url_for('index'))
    
    try:
        resp = supabase.table("gastos_fijos").select("*").eq("id", id).execute()
        gasto = resp.data[0] if resp.data else None
        if gasto:
            gasto['periodo'] = gasto.get('mes') or gasto.get('periodo', '')
    except Exception as e:
        print(f"Error al obtener gasto fijo para editar: {e}")
        gasto = None

    return render_template('editar_gasto.html', gasto=gasto)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
