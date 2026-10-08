import os
import io
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, send_file
from supabase import create_client, Client

# Configurar matplotlib en modo headless para servidores sin interfaz gráfica
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
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

    # 1. Obtener Trabajos desde Supabase
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

    # 2. Obtener Gastos Fijos desde Supabase
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
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#22252a'), spaceAfter=4)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#444444'), spaceAfter=4, spaceBefore=8)
    normal_style = styles['Normal']

    elements.append(Paragraph("<b>RLA | Gestión Financiera y Técnica</b>", title_style))
    elements.append(Paragraph(f"Reporte generado el: {date.today().strftime('%d-%m-%Y')}", normal_style))
    elements.append(Spacer(1, 8))

    # Obtener datos de Supabase
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

    total_ingresos = sum(float(item.get('neto', item.get('monto_neto', 0)) * 1.19) for item in datos_trabajos if str(item.get('estado', '')).lower() in ['pagado', 'completado'])
    total_pendientes = sum(float(item.get('neto', item.get('monto_neto', 0)) * 1.19) for item in datos_trabajos if str(item.get('estado', '')).lower() not in ['pagado', 'completado'])
    total_gastos_op = sum(float(item.get('gastos_op') or 0) for item in datos_trabajos)
    total_gastos_fijos = sum(float(item.get('monto') or 0) for item in datos_gastos)
    egresos = total_gastos_op + total_gastos_fijos
    capital_disponible = total_ingresos - egresos

    # 1. Tabla de Balance General (4 indicadores)
    elements.append(Paragraph("<b>Resumen de Balance General</b>", subtitle_style))
    balance_data = [
        ["Ingresos (Pagados con IVA)", "Por Cobrar (Pendientes)", "Egresos Op. & Fijos", "Capital Disponible"],
        [
            f"${int(total_ingresos):,}".replace(",", "."),
            f"${int(total_pendientes):,}".replace(",", "."),
            f"${int(egresos):,}".replace(",", "."),
            f"${int(capital_disponible):,}".replace(",", ".")
        ]
    ]
    balance_table = Table(balance_data, colWidths=[135, 135, 135, 135])
    balance_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#343a40')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dcdcdc'))
    ]))
    elements.append(balance_table)
    elements.append(Spacer(1, 10))

    # 2. Generar Gráfico con Matplotlib e insertarlo en el PDF
    meses_nombres = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    ingresos_mensuales = [0] * 12
    egresos_mensuales = [0] * 12

    for item in datos_trabajos:
        fecha = str(item.get('fecha', ''))
        if fecha.startswith("2026"):
            try:
                m = int(fecha.split('-')[1]) - 1
                if 0 <= m < 12:
                    if str(item.get('estado', '')).lower() in ['pagado', 'completado']:
                        neto_val = float(item.get('neto', item.get('monto_neto', 0)))
                        ingresos_mensuales[m] += neto_val * 1.19
                    egresos_mensuales[m] += float(item.get('gastos_op', 0))
            except Exception:
                pass

    map_mes_texto = {
        "enero": 0, "january": 0, "ene": 0,
        "febrero": 1, "february": 1, "feb": 1,
        "marzo": 2, "march": 2, "mar": 2,
        "abril": 3, "april": 3, "abr": 3,
        "mayo": 4, "may": 4,
        "junio": 5, "june": 5, "jun": 5,
        "julio": 6, "july": 6, "jul": 6,
        "agosto": 7, "august": 7, "ago": 7,
        "septiembre": 8, "september": 8, "sep": 8,
        "octubre": 9, "october": 9, "oct": 9,
        "noviembre": 10, "november": 10, "nov": 10,
        "diciembre": 11, "december": 11, "dic": 11
    }

    for gasto in datos_gastos:
        texto_mes = str(gasto.get('mes') or gasto.get('periodo') or '').lower()
        m_idx = None
        for nombre, idx in map_mes_texto.items():
            if nombre in texto_mes:
                m_idx = idx
                break
        if m_idx is not None:
            egresos_mensuales[m_idx] += float(gasto.get('monto', 0))

    fig, ax = plt.subplots(figsize=(7, 2.5))
    x = range(12)
    width = 0.35
    ax.bar([i - width/2 for i in x], ingresos_mensuales, width, label='Ingresos (Pagados)', color='#28a745')
    ax.bar([i + width/2 for i in x], egresos_mensuales, width, label='Egresos (Op. & Fijos)', color='#dc3545')
    ax.set_xticks(list(x))
    ax.set_xticklabels(meses_nombres, fontsize=8)
    ax.legend(fontsize=7, loc='upper right')
    ax.set_title("Resumen Financiero Mensual (2026)", fontsize=9, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()

    chart_buffer = io.BytesIO()
    plt.savefig(chart_buffer, format='png', dpi=150)
    plt.close()
    chart_buffer.seek(0)

    elements.append(Paragraph("<b>Gráfico Resumen Financiero Mensual</b>", subtitle_style))
    elements.append(Image(chart_buffer, width=500, height=180))
    elements.append(Spacer(1, 10))

    # 3. Tabla Trabajos PDF
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
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dcdcdc'))
    ]))
    elements.append(t_table)
    elements.append(Spacer(1, 10))

    # 4. Tabla Gastos Fijos PDF
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
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
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
        periodo_val = request.form.get('periodo') or request.form.get('mes') or 'Sin Especificar'
        nuevo_gasto = {
            "concepto": request.form.get('concepto', ''),
            "monto": float(request.form.get('monto') or 0),
            "mes": periodo_val
        }
        supabase.table("gastos_fijos").insert(nuevo_gasto).execute()
    except Exception as e:
        print(f"❌ Error al guardar el gasto fijo en Supabase: {e}")
    
    return redirect(url_for('index'))

@app.route('/editar_gasto/<int:id>', methods=['GET', 'POST'])
def editar_gasto(id):
    if request.method == 'POST':
        try:
            periodo_val = request.form.get('periodo') or request.form.get('mes') or 'Sin Especificar'
            datos_actualizados = {
                "concepto": request.form.get('concepto', ''),
                "monto": float(request.form.get('monto') or 0),
                "mes": periodo_val
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
