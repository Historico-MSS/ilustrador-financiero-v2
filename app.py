import streamlit as st
import pandas as pd
import io
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from modules.fund_loader import cargar_todos_los_fondos
from modules.utils import LISTA_MESES, mes_numero
from modules.portfolio_builder import construir_portafolio
from modules.simulator import simular_mis, simular_mss, construir_resumen_anual
from modules.reporting import construir_estado_cuenta_final

st.set_page_config(layout="wide")
st.title("💼 Ilustrador Financiero")

# =========================
# FORMATOS
# =========================
def color_valores(val):
    try:
        v = float(str(val).replace("USD", "").replace("%", "").replace(",", ""))
        if v < 0:
            return "color:red;font-weight:bold"
        elif v > 0:
            return "color:green;font-weight:bold"
    except:
        return ""

def format_estado(df):
    df_fmt = df.copy()
    for col in ["Capital inicial asignado","Valor actual","Ganancia / pérdida no realizada"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")
    for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:.2f}%")
    return df_fmt.style.map(color_valores)

def format_resumen(df):
    df_fmt = df.copy()
    for col in ["Aporte_Acum","Retiro","Valor_Cuenta","Valor_Rescate"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")
    for col in ["Rendimiento","Rendimiento_Acumulado"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:.2f}%")
    return df_fmt.style.map(color_valores)

# =========================
# PORTAFOLIO CON CAMBIOS (CONTINUIDAD REAL)
# =========================
def portafolio_con_cambios(fondos, asignacion_inicial, cambios, anio_inicio, mes_inicio):
    fecha_actual = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)+pd.offsets.MonthEnd(0)
    df_total = pd.DataFrame()
    asignacion_actual = asignacion_inicial.copy()

    cambios = sorted(cambios, key=lambda x: (x["anio"], x["mes"]))

    for cambio in cambios:
        fecha_cambio = pd.Timestamp(year=cambio["anio"], month=cambio["mes"], day=1)+pd.offsets.MonthEnd(0)

        asignacion_filtrada = {k:v for k,v in asignacion_actual.items() if v > 0}
        if not asignacion_filtrada:
            continue

        df_tramo = construir_portafolio(fondos, asignacion_filtrada)
        df_tramo = df_tramo[(df_tramo["Date"] >= fecha_actual) & (df_tramo["Date"] < fecha_cambio)]

        # continuidad
        if not df_total.empty and not df_tramo.empty:
            ultimo = df_total["Price"].iloc[-1]
            df_tramo["Price"] = df_tramo["Price"] / df_tramo["Price"].iloc[0] * ultimo

        df_total = pd.concat([df_total, df_tramo])

        asignacion_actual = cambio["asig"]
        fecha_actual = fecha_cambio

    # último tramo
    asignacion_filtrada = {k:v for k,v in asignacion_actual.items() if v > 0}
    if asignacion_filtrada:
        df_tramo = construir_portafolio(fondos, asignacion_filtrada)
        df_tramo = df_tramo[df_tramo["Date"] >= fecha_actual]

        if not df_total.empty and not df_tramo.empty:
            ultimo = df_total["Price"].iloc[-1]
            df_tramo["Price"] = df_tramo["Price"] / df_tramo["Price"].iloc[0] * ultimo

        df_total = pd.concat([df_total, df_tramo])

    return df_total.reset_index(drop=True)

# =========================
# PDF LIMPIO (usa df_res, NO df_port)
# =========================
def generar_pdf(df_resultado, estado, cambios, cliente):
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:

        # Página 1
        fig = plt.figure(figsize=(11,8))
        plt.figtext(0.1, 0.92, "Ilustración Financiera", fontsize=18, weight="bold")
        plt.figtext(0.1, 0.88, f"Cliente: {cliente}", fontsize=11)

        valor = df_resultado["Valor_Cuenta"].iloc[-1]
        aporte = df_resultado["Aporte_Acum"].iloc[-1]

        plt.figtext(0.1, 0.80, f"Aporte: USD {aporte:,.0f}")
        plt.figtext(0.1, 0.76, f"Valor: USD {valor:,.0f}")

        ax = fig.add_axes([0.1,0.1,0.8,0.6])
        df_resultado.set_index("Date")["Valor_Cuenta"].plot(ax=ax, linewidth=2)

        # líneas de cambio
        for c in cambios:
            fecha = pd.Timestamp(year=c["anio"], month=c["mes"], day=1)+pd.offsets.MonthEnd(0)
            ax.axvline(fecha, linestyle="--", alpha=0.6)

        ax.set_title("Evolución del portafolio")
        ax.grid(True, alpha=0.2)

        pdf.savefig(fig)
        plt.close()

        # Página 2 (tabla)
        fig2 = plt.figure(figsize=(11,6))
        ax2 = fig2.add_axes([0,0,1,1])
        ax2.axis("off")

        df = estado.copy()
        for col in ["Capital inicial asignado","Valor actual","Ganancia / pérdida no realizada"]:
            if col in df:
                df[col] = df[col].apply(lambda x: f"USD {x:,.2f}")
        for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
            if col in df:
                df[col] = df[col].apply(lambda x: f"{x:.2f}%")

        tabla = ax2.table(
            cellText=df.values,
            colLabels=df.columns,
            loc="center",
            bbox=[0.05,0.1,0.9,0.7]
        )
        tabla.auto_set_font_size(False)
        tabla.set_fontsize(10)

        pdf.savefig(fig2)
        plt.close()

    buffer.seek(0)
    return buffer

# =========================
# INPUTS
# =========================
fondos = cargar_todos_los_fondos("data")

col1, col2 = st.columns(2)
producto = col1.selectbox("Producto", ["MIS","MSS"])
plazo = col2.selectbox("Plazo", list(range(5,21))) if producto=="MSS" else None

col3, col4 = st.columns(2)
mes_txt = col3.selectbox("Mes inicio", LISTA_MESES)
mes_inicio = mes_numero(mes_txt)
anio_inicio = col4.selectbox("Año inicio", list(range(2018,2027)))

cliente = st.text_input("Cliente","Cliente")

fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)+pd.offsets.MonthEnd(0)

fondos_disp = {k:v for k,v in fondos.items() if pd.Timestamp(v["start_date"])<=fecha_inicio}

# =========================
# SELECCIÓN FONDOS
# =========================
fondos_sel = st.multiselect("Fondos", list(fondos_disp.keys()), max_selections=8)

if fondos_sel:

    asignaciones = {}
    total = 0

    st.subheader("Asignación inicial")
    for f in fondos_sel:
        p = st.number_input(f, min_value=0, max_value=100, step=10, key=f"init_{f}")
        asignaciones[f] = p
        total += p

    st.write("Total:", total)

    # =========================
    # CAMBIOS DE ESTRATEGIA
    # =========================
    cambios = []

    if st.checkbox("Modificar composición del portafolio en fechas específicas"):

        n = st.number_input("Número de cambios", 1, 5, 1)

        for i in range(n):
            st.markdown(f"### Cambio {i+1}")

            c1, c2 = st.columns(2)
            with c1:
                mes_c = mes_numero(st.selectbox("Mes", LISTA_MESES, key=f"mes_{i}"))
            with c2:
                anio_c = st.selectbox("Año", list(range(2018,2027)), key=f"anio_{i}")

            fecha_cambio = pd.Timestamp(year=anio_c, month=mes_c, day=1)+pd.offsets.MonthEnd(0)

            fondos_disp_fecha = {
                k:v for k,v in fondos.items()
                if pd.Timestamp(v["start_date"]) <= fecha_cambio
            }

            st.write("Selecciona fondos para este cambio:")
            fondos_cambio = st.multiselect(
                "Fondos",
                list(fondos_disp_fecha.keys()),
                key=f"fondos_cambio_{i}"
            )

            nueva = {}
            total2 = 0

            for f in fondos_cambio:
                p = st.number_input(f"{f}", min_value=0, max_value=100, step=10, key=f"{f}_{i}")
                if p > 0:
                    nueva[f] = p
                total2 += p

            st.write("Total cambio:", total2)
            if total2 != 100:
                st.error("Debe sumar 100%")

            cambios.append({
                "anio": anio_c,
                "mes": mes_c,
                "asig": nueva
            })

    # =========================
    # EJECUCIÓN
    # =========================
    if total == 100:

        df_port = portafolio_con_cambios(fondos_disp, asignaciones, cambios, anio_inicio, mes_inicio)

        st.subheader("Evolución del portafolio")
        st.line_chart(df_port.set_index("Date")["Price"])

        # timeline
        if cambios:
            st.subheader("Timeline estrategia")
            for c in cambios:
                st.write(f"{c['mes']}/{c['anio']} → cambio de portafolio")

        # SIMULACIÓN PRODUCTO
        if producto == "MIS":
            monto = st.number_input("Monto inicial", min_value=10000, value=10000)
            df_res = simular_mis(df_port, monto, anio_inicio, mes_inicio, [], [])
        else:
            freq = st.selectbox("Frecuencia",["Mensual","Trimestral","Semestral","Anual"])
            aporte = st.number_input("Aporte", min_value=150, value=150)
            df_res = simular_mss(df_port, plazo, aporte, freq, anio_inicio, mes_inicio, [])

        # RESULTADOS
        estado = construir_estado_cuenta_final(
            fondos_disp, asignaciones, anio_inicio, mes_inicio,
            df_res["Aporte_Acum"].iloc[-1]
        )

        st.subheader("Estado final por fondo")
        st.dataframe(format_estado(estado), use_container_width=True, hide_index=True)

        # SNAPSHOT SIMPLE
        st.subheader("Estado en fecha")
        mes_s = mes_numero(st.selectbox("Mes snapshot", LISTA_MESES, key="snap_mes"))
        anio_s = st.selectbox("Año snapshot", sorted(df_res["Date"].dt.year.unique()), key="snap_anio")

        fecha_s = pd.Timestamp(year=anio_s, month=mes_s, day=1)+pd.offsets.MonthEnd(0)
        df_s = df_res[df_res["Date"] <= fecha_s]

        if not df_s.empty:
            fila = df_s.iloc[-1]
            st.write("Valor en cuenta:", f"USD {fila['Valor_Cuenta']:,.2f}")

        # PDF (usa df_res)
        pdf = generar_pdf(df_res, estado, cambios, cliente)

        st.download_button(
            "📄 Descargar PDF",
            pdf,
            file_name=f"Reporte_{cliente}.pdf"
        )