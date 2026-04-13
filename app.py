import streamlit as st
import pandas as pd
import io
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from modules.fund_loader import cargar_todos_los_fondos
from modules.utils import LISTA_MESES, mes_numero
from modules.portfolio_builder import construir_portafolio
from modules.simulator import simular_mis, simular_mss
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
        df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")

    for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
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

        if not df_total.empty:
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

        if not df_total.empty:
            ultimo = df_total["Price"].iloc[-1]
            df_tramo["Price"] = df_tramo["Price"] / df_tramo["Price"].iloc[0] * ultimo

        df_total = pd.concat([df_total, df_tramo])

    return df_total.reset_index(drop=True)

# =========================
# PDF PREMIUM
# =========================
def generar_pdf(df_resultado, estado, cambios):

    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:

        fig = plt.figure(figsize=(11,8))

        ax = fig.add_axes([0.1,0.2,0.8,0.6])
        df_resultado.set_index("Date")["Valor_Cuenta"].plot(ax=ax)

        # líneas de cambio
        for c in cambios:
            fecha = pd.Timestamp(year=c["anio"], month=c["mes"], day=1)+pd.offsets.MonthEnd(0)
            ax.axvline(fecha, linestyle="--", alpha=0.5)

        ax.set_title("Evolución del portafolio")
        ax.grid(True)

        pdf.savefig(fig)
        plt.close()

        # donuts
        fig2 = plt.figure(figsize=(11,6))

        dfc = estado[estado["Fondo"]!="Total"]

        ax1 = fig2.add_axes([0.1,0.2,0.35,0.6])
        ax2 = fig2.add_axes([0.55,0.2,0.35,0.6])

        ax1.pie(dfc["Asignación inicial"], autopct='%1.1f%%', wedgeprops={'width':0.4})
        ax1.set_title("Inicial")

        ax2.pie(dfc["Participación actual"], autopct='%1.1f%%', wedgeprops={'width':0.4})
        ax2.set_title("Actual")

        pdf.savefig(fig2)
        plt.close()

    buffer.seek(0)
    return buffer

# =========================
# INPUTS
# =========================
fondos = cargar_todos_los_fondos("data")

mes_txt = st.selectbox("Mes inicio", LISTA_MESES)
mes_inicio = mes_numero(mes_txt)
anio_inicio = st.selectbox("Año inicio", list(range(2018,2027)))

fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)+pd.offsets.MonthEnd(0)

fondos_disp = {k:v for k,v in fondos.items() if pd.Timestamp(v["start_date"])<=fecha_inicio}

fondos_sel = st.multiselect("Fondos", list(fondos_disp.keys()))

# =========================
# ASIGNACIÓN INICIAL
# =========================
if fondos_sel:

    asignaciones={}
    total=0

    for f in fondos_sel:
        p = st.slider(f,0,100,0,step=10)
        asignaciones[f]=p
        total+=p

    st.write("Total:", total)

    cambios=[]

    # =========================
    # CAMBIOS DE ESTRATEGIA
    # =========================
    if st.checkbox("Modificar composición del portafolio en fechas específicas"):

        n = st.number_input("Número de cambios",1,5,1)

        for i in range(n):

            st.write(f"--- Cambio {i+1} ---")

            mes_c = mes_numero(st.selectbox("Mes", LISTA_MESES, key=f"m{i}"))
            anio_c = st.selectbox("Año", list(range(2018,2027)), key=f"a{i}")

            fecha_cambio = pd.Timestamp(year=anio_c, month=mes_c, day=1)+pd.offsets.MonthEnd(0)

            fondos_disp_fecha = {
                k:v for k,v in fondos.items()
                if pd.Timestamp(v["start_date"]) <= fecha_cambio
            }

            nueva={}
            total2=0

            for f in fondos_disp_fecha:
                p = st.slider(f,0,100,0,step=10,key=f"{f}_{i}")
                if p>0:
                    nueva[f]=p
                total2+=p

            st.write("Total cambio:", total2)

            cambios.append({
                "anio":anio_c,
                "mes":mes_c,
                "asig":nueva
            })

    # =========================
    # EJECUCIÓN
    # =========================
    if total==100:

        df_port = portafolio_con_cambios(fondos_disp, asignaciones, cambios, anio_inicio, mes_inicio)

        st.line_chart(df_port.set_index("Date")["Price"])

        estado = construir_estado_cuenta_final(
            fondos_disp, asignaciones, anio_inicio, mes_inicio, 10000
        )

        st.dataframe(format_estado(estado))

        # timeline
        st.subheader("Timeline estrategia")
        for c in cambios:
            st.write(f"{c['mes']}/{c['anio']} → cambio de portafolio")

        pdf = generar_pdf(df_port, estado, cambios)

        st.download_button("📄 Descargar PDF", pdf, "Reporte.pdf")