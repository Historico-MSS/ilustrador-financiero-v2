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

st.set_page_config(page_title="Ilustrador Financiero V2", layout="wide")

# =========================================================
# FORMATO Y COLORES
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

def format_resumen(df):
    df_fmt = df.copy()

    for col in ["Aporte_Acum","Retiro","Valor_Cuenta","Valor_Rescate"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")

    for col in ["Rendimiento","Rendimiento_Acumulado"]:
        if col in df_fmt:
            df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:.2f}%")

    return df_fmt.style.map(color_valores)

def format_estado(df):
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
def generar_pdf(df_resultado, estado, cliente, anio, mes):
    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:

        fig, ax = plt.subplots(figsize=(10,6))
        df_resultado.set_index("Date")[["Valor_Cuenta","Valor_Rescate"]].plot(ax=ax)
        ax.set_title(f"Ilustración financiera — {cliente}")
        ax.set_ylabel("USD")
        ax.grid(True)
        pdf.savefig(fig)
        plt.close()

        fig2, ax2 = plt.subplots(figsize=(12,5))
        ax2.axis("off")

        df = estado.copy()

        for col in ["Capital inicial asignado","Valor actual","Ganancia / pérdida no realizada"]:
            df[col] = df[col].apply(lambda x: f"USD {x:,.2f}")

        for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
            df[col] = df[col].apply(lambda x: f"{x:.2f}%")

        tabla = ax2.table(cellText=df.values, colLabels=df.columns, loc="center")
        tabla.auto_set_font_size(False)
        tabla.set_fontsize(8)
        tabla.scale(1.2,1.5)

        ax2.set_title("Estado de cuenta final")

        pdf.savefig(fig2)
        plt.close()

    buffer.seek(0)
    return buffer

# =========================================================
# APP
# =========================================================
st.title("🚀 Ilustrador Financiero V2")

fondos = cargar_todos_los_fondos("data")

col1, col2 = st.columns(2)
producto = col1.selectbox("Producto", ["MIS","MSS"])
plazo = col2.selectbox("Plazo", list(range(5,21))) if producto=="MSS" else None

col3, col4 = st.columns(2)
mes_txt = col3.selectbox("Mes", LISTA_MESES)
mes_inicio = mes_numero(mes_txt)
anio_inicio = col4.selectbox("Año", list(range(2018,2027)))

cliente = st.text_input("Cliente","Cliente")

fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)+pd.offsets.MonthEnd(0)

fondos_disp = {}
for k,v in fondos.items():
    f = pd.Timestamp(v["start_date"])
    f = pd.Timestamp(year=f.year, month=f.month, day=1)+pd.offsets.MonthEnd(0)
    if f <= fecha_inicio:
        fondos_disp[k]=v

fondos_sel = st.multiselect("Fondos", list(fondos_disp.keys()), max_selections=8)

if fondos_sel:

    asignaciones={}
    total=0

    for f in fondos_sel:
        p=st.selectbox(f, list(range(0,101,10)), key=f)
        asignaciones[f]=p
        total+=p

    st.write("Total:", total)

    if total==100:

        if producto=="MIS":
            monto=st.number_input("Monto inicial",min_value=10000,value=10000)
            df_port=construir_portafolio(fondos_disp,asignaciones)
            df_res=simular_mis(df_port,monto,anio_inicio,mes_inicio,[],[])
        else:
            freq=st.selectbox("Frecuencia",["Mensual","Trimestral","Semestral","Anual"])
            aporte=st.number_input("Aporte",min_value=150,value=150)
            df_port=construir_portafolio(fondos_disp,asignaciones)
            df_res=simular_mss(df_port,plazo,aporte,freq,anio_inicio,mes_inicio,[])

        st.line_chart(df_res.set_index("Date")[["Valor_Cuenta","Valor_Rescate"]])

        resumen=construir_resumen_anual(df_res,anio_inicio,mes_inicio)
        st.subheader("Resumen anual")
        st.dataframe(format_resumen(resumen))

        estado=construir_estado_cuenta_final(
            fondos_disp,asignaciones,anio_inicio,mes_inicio,
            df_res["Aporte_Acum"].iloc[-1]
        )

        st.subheader("Estado final por fondo")
        st.dataframe(format_estado(estado))

        st.subheader("Estado en fecha específica")
        mes_s=mes_numero(st.selectbox("Mes snapshot",LISTA_MESES))
        anio_s=st.selectbox("Año snapshot",sorted(df_res["Date"].dt.year.unique()))

        fecha_s=pd.Timestamp(year=anio_s,month=mes_s,day=1)+pd.offsets.MonthEnd(0)
        df_s=df_res[df_res["Date"]<=fecha_s]

        if not df_s.empty:
            fila=df_s.iloc[-1]
            st.write("Valor:",f"USD {fila['Valor_Cuenta']:,.2f}")

        st.subheader("Descargar PDF")

        pdf=generar_pdf(df_res,estado,cliente,anio_inicio,mes_inicio)

        nombre=f"Ilustracion_{cliente.replace(' ','_')}_{anio_inicio}_{mes_inicio}.pdf"

        st.download_button("Descargar PDF",pdf,file_name=nombre)