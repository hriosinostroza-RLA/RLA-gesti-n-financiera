import os
import io
import urllib.request
import urllib.parse
import json
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, send_file
from supabase import create_client, Client
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
        return f"${int(float(value)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"


def limpiar_monto(valor):
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("$", "").replace(" ", "")
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "." in texto:
        partes = texto.split(".")
        if len(partes) == 2 and len(partes[1]) == 3 and partes[1].isdigit():
            texto = "".join(partes)
    texto = texto.replace(",", ".")
    return float(texto or 0)


def _parsear_fecha(fecha_val):
    if not fecha_val:
        return None
    try:
        texto = str(fecha_val).strip()
        if 'T' in texto:
            return datetime.fromisoformat(texto.split('T')[0]).date()
        return datetime.strptime(texto.split()[0], "%Y-%m-%d").date()
    except Exception:
        return None


def _fecha_desde_periodo_gasto(texto_periodo, hoy):
    texto = str(texto_periodo or '').strip().lower()
    if not texto:
        return None

    map_meses = {
        "enero": 1, "january": 1, "ene": 1,
        "febrero": 2, "february": 2, "feb": 2,
        "marzo": 3, "march": 3, "mar": 3,
        "abril": 4, "april": 4, "abr": 4,
        "mayo": 5, "may": 5,
        "junio": 6, "june": 6, "jun": 6,
        "julio": 7, "july": 7, "jul": 7,
        "agosto": 8, "august": 8, "ago": 8,
        "septiembre": 9, "september": 9, "sep": 9, "setiembre": 9,
        "octubre": 10, "october": 10, "oct": 10,
        "noviembre": 11, "november": 11, "nov": 11,
        "diciembre": 12, "december": 12, "dic": 12
    }

    mes_encontrado = None
    for nombre, num in map_meses.items():
        if nombre in texto:
            mes_encontrado = num
            break

    if not mes_encontrado:
        return None

    anio_encontrado = None
    for palabra in texto.replace(",", " ").split():
        if palabra.isdigit() and len(palabra) == 4:
            anio_encontrado = int(palabra)
            break

    if anio_encontrado is None:
        anio_encontrado = hoy.year

    try:
        return date(anio_encontrado, mes_encontrado, 1)
    except Exception:
        return None


def es_editable_trabajo(item):
    """Editable si han pasado <= 30 días desde created_at (o desde fecha del trabajo si no hay created_at)."""
    hoy = date.today()
    fecha_ref = _parsear_fecha(item.get('created_at')) or _parsear_fecha(item.get('fecha'))
    if not fecha_ref:
        return False
    return (hoy - fecha_ref).days <= 30


def es_editable_gasto(item):
    """Editable si tiene <= 30 días desde created_at, o si sin created_at corresponde a un mes dentro de los últimos 30 días."""
    hoy = date.today()
    fecha_creacion = _parsear_fecha(item.get('created_at'))
    if fecha_creacion:
        return (hoy - fecha_creacion).days <= 30

    texto = str(item.get('mes') or item.get('periodo') or '').strip().lower()
    if not texto:
        return False

    fecha_periodo = _fecha_desde_periodo_gasto(texto, hoy)
    if fecha_periodo:
        tiene_anio = any(p.isdigit() and len(p) == 4 for p in texto.replace(",", " ").split())
        if not tiene_anio and fecha_periodo.month == hoy.month:
            fecha_periodo = date(hoy.year, hoy.month, 1)
        return (hoy - fecha_periodo).days <= 30

    return False


@app.route('/')
def index():
    datos_trabajos = []
    datos_gastos = []

    try:
        resp_trabajos = supabase.table("trabajos").select("*").order("fecha", desc=False).execute()
        if resp_trabajos.data:
            for item in resp_trabajos.data:
                neto_val = limpiar_monto(item.get('neto') if item.get('neto') is not None else item.get('monto_neto', 0))
                item['neto'] = neto_val
                item['monto_neto'] = neto_val
                item['iva'] = neto_val * 0.19
                item['total_bruto'] = neto_val * 1.19
                item['editable'] = es_editable_trabajo(item)
            datos_trabajos = resp_trabajos.data
    except Exception as e:
        print(f"Error al consultar trabajos: {e}")

    try:
        resp_gastos = supabase.table("gastos_fijos").select("*").execute()
        if resp_gastos.data:
            for item in resp_gastos.data:
                mes_val = item.get('mes') if item.get('mes') is not None else item.get('periodo', '')
                item['mes'] = mes_val
                item['periodo'] = mes_val
                item['monto'] = limpiar_monto(item.get('monto', 0))
                item['editable'] = es_editable_gasto(item)
            datos_gastos = resp_gastos.data
    except Exception as e:
        print(f"Error al consultar gastos fijos: {e}")

    total_ingresos = sum(float(item.get('total_bruto', 0)) for item in datos_trabajos if str(item.get('estado', '')).lower() in ['pagado', 'completado'])
    total_pendientes = sum(float(item.get('total_bruto', 0)) for item in datos_trabajos if str(item.get('estado', '')).lower() not in ['pagado', 'completado'])

    total_gastos_op = sum(limpiar_monto(item.get('gastos_op') or 0) for item in datos_trabajos)
    total_viaticos = sum(limpiar_monto(item.get('viaticos') or 0) for item in datos_trabajos)
    total_gastos_fijos = sum(limpiar_monto(item.get('monto') or 0) for item in datos_gastos)

    egresos = total_gastos_op + total_viaticos + total_gastos_fijos
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

    try:
        resp_trabajos = supabase.table("trabajos").select("*").order("fecha", desc=False).execute()
        datos_trabajos = resp_trabajos.data if resp_trabajos.data else []
    except Exception:
        datos_trabajos = []

    try:
        resp_gastos = supabase.table("gastos_fijos").select("*").execute()
        datos_gastos = resp_gastos.data if resp_gastos.data else []
    except Exception:
        datos_gastos = []

    total_ingresos = sum(limpiar_monto(item.get('neto', item.get('monto_neto', 0))) * 1.19 for item in datos_trabajos if str(item.get('estado', '')).lower() in ['pagado', 'completado'])
    total_pendientes = sum(limpiar_monto(item.get('neto', item.get('monto_neto', 0))) * 1.19 for item in datos_trabajos if str(item.get('estado', '')).lower() not in ['pagado', 'completado'])
    total_gastos_op = sum(limpiar_monto(item.get('gastos_op') or 0) for item in datos_trabajos)
    total_viaticos = sum(limpiar_monto(item.get('viaticos') or 0) for item in datos_trabajos)
    total_gastos_fijos = sum(limpiar_monto(item.get('monto') or 0) for item in datos_gastos)
    egresos = total_gastos_op + total_viaticos + total_gastos_fijos
    capital_disponible = total_ingresos - egresos

    elements.append(Paragraph("<b>Resumen de Balance General</b>", subtitle_style))
    balance_data = [
        ["Ingresos (Pagados con IVA)", "Por Cobrar (Pendientes)", "Egresos Totales", "Capital Disponible"],
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
                        neto_val = limpiar_monto(item.get('neto', item.get('monto_neto', 0)))
                        ingresos_mensuales[m] += neto_val * 1.19
                    egresos_mensuales[m] += limpiar_monto(item.get('gastos_op', 0) or 0) + limpiar_monto(item.get('viaticos', 0) or 0)
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
            egresos_mensuales[m_idx] += limpiar_monto(gasto.get('monto', 0))

    chart_config = {
        "type": "bar",
        "data": {
            "labels": meses_nombres,
            "datasets": [
                {"label": "Ingresos (Pagados)", "data": ingresos_mensuales, "backgroundColor": "#28a745"},
                {"label": "Egresos Totales", "data": egresos_mensuales, "backgroundColor": "#dc3545"}
            ]
        },
        "options": {
            "title": {"display": True, "text": "Resumen Financiero Mensual (2026)"}
        }
    }

    try:
        chart_url = f"https://quickchart.io/chart?w=500&h=180&c={urllib.parse.quote(json.dumps(chart_config))}"
        chart_img_data = urllib.request.urlopen(chart_url).read()
        elements.append(Paragraph("<b>Gráfico Resumen Financiero Mensual</b>", subtitle_style))
        elements.append(Image(io.BytesIO(chart_img_data), width=500, height=180))
        elements.append(Spacer(1, 10))
    except Exception as e:
        print(f"Error gráfico PDF: {e}")

    elements.append(Paragraph("<b>Historial de Trabajos y Servicios</b>", subtitle_style))
    t_data = [["Factura", "Fecha", "Cliente", "Equipo", "Neto", "G. Op.", "Viáticos", "Estado"]]
    for item in datos_trabajos:
        neto_val = limpiar_monto(item.get('neto') or item.get('monto_neto', 0))
        t_data.append([
            str(item.get('n_factura', '')),
            str(item.get('fecha', '')),
            str(item.get('cliente', '')),
            str(item.get('equipo', '')),
            f"${int(neto_val):,}".replace(",", "."),
            f"${int(limpiar_monto(item.get('gastos_op', 0))):,}".replace(",", "."),
            f"${int(limpiar_monto(item.get('viaticos', 0))):,}".replace(",", "."),
            str(item.get('estado', ''))
        ])

    t_table = Table(t_data, colWidths=[45, 60, 95, 100, 75, 55, 55, 55])
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

    elements.append(Paragraph("<b>Historial de Gastos Fijos / Materiales</b>", subtitle_style))
    g_data = [["Concepto", "Periodo / Mes", "Monto"]]
    for gasto in datos_gastos:
        g_data.append([
            str(gasto.get('concepto', '')),
            str(gasto.get('mes', '') or gasto.get('periodo', '')),
            f"${int(limpiar_monto(gasto.get('monto', 0))):,}".replace(",", ".")
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
        neto_val = limpiar_monto(request.form.get('monto_neto') or request.form.get('neto') or 0)
        nuevo_trabajo = {
            "n_factura": str(request.form.get('factura', '')).strip(),
            "fecha": str(request.form.get('fecha', '')).strip(),
            "cliente": str(request.form.get('cliente', '')).strip(),
            "equipo": str(request.form.get('equipo', '')).strip(),
            "servicio": str(request.form.get('servicio', '')).strip(),
            "neto": neto_val,
            "gastos_op": limpiar_monto(request.form.get('gastos_op') or 0),
            "viaticos": limpiar_monto(request.form.get('viaticos') or 0),
            "estado": str(request.form.get('estado', 'Pendiente')).strip(),
            "created_at": datetime.now().isoformat()
        }
        try:
            supabase.table("trabajos").insert(nuevo_trabajo).execute()
        except Exception:
            nuevo_trabajo.pop("created_at", None)
            supabase.table("trabajos").insert(nuevo_trabajo).execute()
    except Exception as e:
        print(f"❌ Error al guardar trabajo: {e}")

    return redirect(url_for('index'))


@app.route('/editar_trabajo/<int:id>', methods=['GET', 'POST'])
def editar_trabajo(id):
    try:
        resp = supabase.table("trabajos").select("*").eq("id", id).execute()
        trabajo = resp.data[0] if resp.data else None

        if trabajo and not es_editable_trabajo(trabajo):
            return "Acceso denegado: El periodo permitido de 30 días para editar este trabajo ha expirado.", 403

        if request.method == 'POST':
            neto_val = limpiar_monto(request.form.get('monto_neto') or request.form.get('neto') or 0)
            datos_actualizados = {
                "n_factura": str(request.form.get('factura', '')).strip(),
                "fecha": str(request.form.get('fecha', '')).strip(),
                "cliente": str(request.form.get('cliente', '')).strip(),
                "equipo": str(request.form.get('equipo', '')).strip(),
                "servicio": str(request.form.get('servicio', '')).strip(),
                "neto": neto_val,
                "gastos_op": limpiar_monto(request.form.get('gastos_op') or 0),
                "viaticos": limpiar_monto(request.form.get('viaticos') or 0),
                "estado": str(request.form.get('estado', 'Pendiente')).strip()
            }
            supabase.table("trabajos").update(datos_actualizados).eq("id", id).execute()
            return redirect(url_for('index'))

        if trabajo:
            neto_val = trabajo.get('neto') if trabajo.get('neto') is not None else trabajo.get('monto_neto', 0)
            trabajo['monto_neto'] = limpiar_monto(neto_val)
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
        concepto_val = str(request.form.get('concepto') or '').strip()
        monto_val = limpiar_monto(request.form.get('monto') or 0)
        periodo_val = str(request.form.get('periodo') or request.form.get('mes') or 'Sin Especificar').strip()

        payload_con_fecha = {
            "concepto": concepto_val,
            "monto": monto_val,
            "mes": periodo_val,
            "created_at": datetime.now().isoformat()
        }
        try:
            res = supabase.table("gastos_fijos").insert(payload_con_fecha).execute()
            if not res.data:
                raise Exception("Inserción sin datos devueltos con created_at")
        except Exception as e_fecha:
            print(f"Reintentando insertar gasto sin created_at ({e_fecha})")
            payload_sin_fecha = {
                "concepto": concepto_val,
                "monto": monto_val,
                "mes": periodo_val
            }
            supabase.table("gastos_fijos").insert(payload_sin_fecha).execute()

    except Exception as e:
        print(f"❌ Error crítico al guardar gasto fijo: {e}")

    return redirect(url_for('index'))


@app.route('/editar_gasto/<int:id>', methods=['GET', 'POST'])
def editar_gasto(id):
    try:
        resp = supabase.table("gastos_fijos").select("*").eq("id", id).execute()
        gasto = resp.data[0] if resp.data else None

        if gasto and not es_editable_gasto(gasto):
            return "Acceso denegado: El periodo permitido de 30 días para editar este gasto ha expirado.", 403

        if request.method == 'POST':
            periodo_val = str(request.form.get('periodo') or request.form.get('mes') or 'Sin Especificar').strip()
            datos_actualizados = {
                "concepto": str(request.form.get('concepto', '')).strip(),
                "monto": limpiar_monto(request.form.get('monto') or 0),
                "mes": periodo_val
            }
            supabase.table("gastos_fijos").update(datos_actualizados).eq("id", id).execute()
            return redirect(url_for('index'))

        if gasto:
            gasto['periodo'] = gasto.get('mes') or gasto.get('periodo', '')
            gasto['monto'] = limpiar_monto(gasto.get('monto', 0))
    except Exception as e:
        print(f"Error al obtener gasto fijo para editar: {e}")
        gasto = None

    return render_template('editar_gasto.html', gasto=gasto)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
