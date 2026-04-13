import io
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from modules.fund_loader import cargar_todos_los_fondos
from modules.portfolio_builder import construir_portafolio
from modules.simulator import construir_resumen_anual, simular_mis, simular_mss
from modules.utils import LISTA_MESES, mes_numero

APP_PASSWORD = "test"

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.set_page_config(page_title="Acceso", page_icon="🔒", layout="centered")
    st.title("🔒 Acceso a la aplicación")
    st.write("Introduce la contraseña para continuar.")

    password = st.text_input("Contraseña", type="password")

    if st.button("Entrar", use_container_width=True):
        if password == APP_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")

    return False

if not check_password():
    st.stop()

# ... aquí sigue el resto de tu app ...