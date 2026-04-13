import streamlit as st
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import io

from modules.fund_loader import cargar_todos_los_fondos
from modules.utils import LISTA_MESES, mes_numero
from modules.portfolio_builder import construir_portafolio
from modules.simulator import simular_mis, simular_mss, construir_resumen_anual
from modules.reporting import construir_estado_cuenta_final


st.set_page_config(page_title="Ilustrador Financiero V2", layout="wide")

# =========================================================
# FORMATO
# =========================================================
def color_valores(val):
    try:
        v = float(str(val).replace("USD", "").replace("%", "").replace(",", ""))
        if v < 0:
            return "color:red;font-weight:bold"
        elif v > 0:
            return "color:green;font-weight:bold"
    except:
        return ""

def format_table(df):
    df_fmt = df.copy()

    for col in ["Capital inicial asignado","Valor actual","Ganancia / pérdida no realizada"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")

    for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:.2f}%")

    return df_fmt.style.map(color_valores)

# =========================================================
# PDF
# =========================================================
def generar_pdf(df_resultado, estado_final):
    buffer = io.BytesIO()
    with PdfPages(buffer) as pdf:

        # Gráfico
        fig, ax = plt.subplots()
        df_resultado.set_index("Date")[["Valor_Cuenta","Valor_Rescate"]].plot(ax=ax)
        pdf.savefig(fig)
        plt.close()

        # Tabla estado
        fig2, ax2 = plt.subplots()
        ax2.axis('off')
        tabla = ax2.table(cellText=estado_final.values,
                          colLabels=estado_final.columns,
                          loc='center')
        tabla.auto_set_font_size(False)
        tabla.set_fontsize(8)
        pdf.savefig(fig2)
        plt.close()

    buffer.seek(0)
    return buffer

# =========================================================
# CARGA
# =========================================================
fondos = cargar_todos_los_fondos("data")

st.title("🚀 Ilustrador Financiero V2")

# =========================================================
# CONFIG
# =========================================================
col1, col2 = st.columns(2)
producto = col1.selectbox("Producto", ["MIS","MSS"])
plazo = col2.selectbox("Plazo", list(range(5,21))) if producto=="MSS" else None

col3, col4 = st.columns(2)
mes_txt = col3.selectbox("Mes", LISTA_MESES)
mes_inicio = mes_numero(mes_txt)
anio_inicio = col4.selectbox("Año", list(range(2018,2027)))

fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)+pd.offsets.MonthEnd(0)

# =========================================================
# FILTRO
# =========================================================
fondos_disp = {}
for k,v in fondos.items():
    f = pd.Timestamp(v["start_date"])
    f = pd.Timestamp(year=f.year, month=f.month, day=1)+pd.offsets.MonthEnd(0)
    if f <= fecha_inicio:
        fondos_disp[k]=v

# =========================================================
# SELECCION
# =========================================================
fondos_sel = st.multiselect("Fondos (máx 8)", list(fondos_disp.keys()), max_selections=8)

if fondos_sel:

    asignaciones = {}
    total=0

    for f in fondos_sel:
        p = st.selectbox(f, list(range(0,101,10)), key=f)
        asignaciones[f]=p
        total+=p

    st.write("Total:", total)

    if total==100:

        # =================================================
        # CAMBIOS DE PORTAFOLIO
        # =================================================
        cambios=[]
        if st.checkbox("Cambios de portafolio"):
            for i in range(2):
                st.write(f"Cambio {i+1}")
                m = mes_numero(st.selectbox("Mes cambio", LISTA_MESES, key=f"m{i}"))
                a = st.selectbox("Año cambio", list(range(2018,2027)), key=f"a{i}")

                asign2={}
                for f in fondos_sel:
                    p = st.selectbox(f+" cambio", list(range(0,101,10)), key=f"{f}_{i}")
                    asign2[f]=p

                cambios.append({"anio":a,"mes":m,"asig":asign2})

        # =================================================
        # PORTAFOLIO BASE
        # =================================================
        df_port = construir_portafolio(fondos_disp, asignaciones)

        # =================================================
        # FINANCIERO
        # =================================================
        if producto=="MIS":
            monto = st.number_input("Monto inicial", min_value=10000, value=10000)
            df_res = simular_mis(df_port, monto, anio_inicio, mes_inicio, [], [])
        else:
            freq = st.selectbox("Frecuencia", ["Mensual","Trimestral","Semestral","Anual"])
            aporte = st.number_input("Aporte", min_value=150, value=150)
            df_res = simular_mss(df_port, plazo, aporte, freq, anio_inicio, mes_inicio, [])

        st.line_chart(df_res.set_index("Date")[["Valor_Cuenta","Valor_Rescate"]])

        # =================================================
        # RESUMEN
        # =================================================
        resumen = construir_resumen_anual(df_res, anio_inicio, mes_inicio)
        st.subheader("Resumen anual")
        st.dataframe(resumen.style.map(color_valores))

        # =================================================
        # ESTADO FINAL
        # =================================================
        estado = construir_estado_cuenta_final(
            fondos_disp, asignaciones,
            anio_inicio, mes_inicio,
            df_res["Aporte_Acum"].iloc[-1]
        )

        st.subheader("Estado final por fondo")
        st.dataframe(format_table(estado))

        # =================================================
        # SNAPSHOT
        # =================================================
        st.subheader("Estado en fecha específica")
        mes_s = mes_numero(st.selectbox("Mes snapshot", LISTA_MESES))
        anio_s = st.selectbox("Año snapshot", sorted(df_res["Date"].dt.year.unique()))

        fecha_s = pd.Timestamp(year=anio_s, month=mes_s, day=1)+pd.offsets.MonthEnd(0)
        df_s = df_res[df_res["Date"]<=fecha_s]

        if not df_s.empty:
            fila = df_s.iloc[-1]
            st.write("Valor:", f"USD {fila['Valor_Cuenta']:,.2f}")

            estado_s = construir_estado_cuenta_final(
                fondos_disp, asignaciones,
                anio_inicio, mes_inicio,
                fila["Aporte_Acum"]
            )

            st.dataframe(format_table(estado_s))

        # =================================================
        # PDF
        # =================================================
        st.subheader("Descargar PDF")

        pdf = generar_pdf(df_res, estado)
        st.download_button("Descargar PDF", pdf, "reporte.pdf")