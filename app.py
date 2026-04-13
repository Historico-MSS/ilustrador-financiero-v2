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

def format_estado(df):
    df_fmt = df.copy()

    for col in ["Capital inicial asignado","Valor actual","Ganancia / pérdida no realizada"]:
        df_fmt[col] = df_fmt[col].apply(lambda x: f"USD {x:,.2f}")

    for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
        df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:.2f}%")

    return df_fmt.style.map(color_valores)

# =========================================================
# PDF LIMPIO
# =========================================================
def generar_pdf(df_resultado, estado, cliente):

    buffer = io.BytesIO()

    with PdfPages(buffer) as pdf:

        fig = plt.figure(figsize=(11,8))

        plt.figtext(0.1, 0.92, "Ilustración Financiera", fontsize=18, weight="bold")
        plt.figtext(0.1, 0.88, f"Cliente: {cliente}", fontsize=11)

        valor = df_resultado["Valor_Cuenta"].iloc[-1]
        aporte = df_resultado["Aporte_Acum"].iloc[-1]

        plt.figtext(0.1, 0.80, f"Aporte: USD {aporte:,.0f}")
        plt.figtext(0.1, 0.76, f"Valor: USD {valor:,.0f}")

        ax = fig.add_axes([0.1, 0.1, 0.8, 0.5])
        df_resultado.set_index("Date")[["Valor_Cuenta","Valor_Rescate"]].plot(ax=ax)

        pdf.savefig(fig)
        plt.close()

        fig2 = plt.figure(figsize=(11,6))
        ax2 = fig2.add_axes([0,0,1,1])
        ax2.axis("off")

        df = estado.copy()

        for col in ["Capital inicial asignado","Valor actual","Ganancia / pérdida no realizada"]:
            df[col] = df[col].apply(lambda x: f"USD {x:,.2f}")

        for col in ["Asignación inicial","Participación actual","Rentabilidad acumulada"]:
            df[col] = df[col].apply(lambda x: f"{x:.2f}%")

        tabla = ax2.table(
            cellText=df.values,
            colLabels=df.columns,
            loc="center",
            bbox=[0.05,0.1,0.9,0.7]
        )

        pdf.savefig(fig2)
        plt.close()

    buffer.seek(0)
    return buffer

# =========================================================
# PORTAFOLIO CON CAMBIOS
# =========================================================
def portafolio_con_cambios(fondos, asignacion, cambios, anio_inicio, mes_inicio):

    fecha_inicio = pd.Timestamp(year=anio_inicio, month=mes_inicio, day=1)+pd.offsets.MonthEnd(0)

    if not cambios:
        return construir_portafolio(fondos, asignacion)

    df_total = pd.DataFrame()
    asignacion_actual = asignacion

    cambios = sorted(cambios, key=lambda x: (x["anio"], x["mes"]))

    for cambio in cambios:
        fecha_cambio = pd.Timestamp(year=cambio["anio"], month=cambio["mes"], day=1)+pd.offsets.MonthEnd(0)

        df_temp = construir_portafolio(fondos, asignacion_actual)
        df_temp = df_temp[(df_temp["Date"] >= fecha_inicio) & (df_temp["Date"] < fecha_cambio)]

        df_total = pd.concat([df_total, df_temp])

        asignacion_actual = cambio["asig"]
        fecha_inicio = fecha_cambio

    df_temp = construir_portafolio(fondos, asignacion_actual)
    df_temp = df_temp[df_temp["Date"] >= fecha_inicio]

    df_total = pd.concat([df_total, df_temp])

    return df_total.reset_index(drop=True)

# =========================================================
# CARGA
# =========================================================
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

fondos_disp = {k:v for k,v in fondos.items() if pd.Timestamp(v["start_date"])<=fecha_inicio}

fondos_sel = st.multiselect("Fondos", list(fondos_disp.keys()), max_selections=8)

# =========================================================
# COMPARADOR
# =========================================================
comparar = st.checkbox("Comparar estrategias")

if fondos_sel:

    asignaciones={}
    total=0

    for f in fondos_sel:
        p = st.slider(f,0,100,0,step=10)
        asignaciones[f]=p
        total+=p

    st.write("Total:", total)

    # CAMBIOS
    cambios=[]
    if st.checkbox("Modificar composición del portafolio en fechas específicas"):
        for i in range(2):
            st.write(f"Cambio {i+1}")
            m = mes_numero(st.selectbox("Mes cambio", LISTA_MESES, key=f"m{i}"))
            a = st.selectbox("Año cambio", list(range(2018,2027)), key=f"a{i}")

            nueva={}
            for f in fondos_sel:
                p = st.slider(f+" cambio",0,100,0,step=10,key=f"{f}_{i}")
                nueva[f]=p

            cambios.append({"anio":a,"mes":m,"asig":nueva})

    if total==100:

        df_port = portafolio_con_cambios(fondos_disp,asignaciones,cambios,anio_inicio,mes_inicio)

        if producto=="MIS":
            monto = st.number_input("Monto",min_value=10000,value=10000)
            df_res = simular_mis(df_port,monto,anio_inicio,mes_inicio,[],[])
        else:
            freq = st.selectbox("Frecuencia",["Mensual","Trimestral","Semestral","Anual"])
            aporte = st.number_input("Aporte",min_value=150,value=150)
            df_res = simular_mss(df_port,plazo,aporte,freq,anio_inicio,mes_inicio,[])

        st.line_chart(df_res.set_index("Date")["Valor_Cuenta"])

        estado = construir_estado_cuenta_final(
            fondos_disp,asignaciones,anio_inicio,mes_inicio,
            df_res["Aporte_Acum"].iloc[-1]
        )

        st.subheader("Estado final")
        st.dataframe(format_estado(estado))

        # COMPARADOR
        if comparar:
            st.subheader("Comparación")
            df_base = construir_portafolio(fondos_disp, asignaciones)
            st.line_chart({
                "Estrategia base": df_base.set_index("Date")["Price"],
                "Estrategia con cambios": df_port.set_index("Date")["Price"]
            })

        pdf = generar_pdf(df_res,estado,cliente)

        st.download_button(
            "📄 Descargar reporte",
            pdf,
            file_name=f"Reporte_{cliente}.pdf"
        )