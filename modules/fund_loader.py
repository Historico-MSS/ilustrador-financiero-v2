import os
import pandas as pd


def normalizar_nombre_fondo(nombre_archivo: str) -> str:
    nombre = os.path.splitext(nombre_archivo)[0]
    nombre = nombre.replace("_", " ").replace("-", " ").strip()
    return nombre


def leer_fondo_excel(ruta_archivo: str) -> dict:
    df = pd.read_excel(ruta_archivo)

    columnas_originales = list(df.columns)
    columnas_limpias = {c: str(c).strip() for c in columnas_originales}
    df = df.rename(columns=columnas_limpias)

    required_cols = ["Fund Name", "Fund Date", "Fund Price"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(
                f"El archivo '{os.path.basename(ruta_archivo)}' no tiene la columna requerida: {col}"
            )

    df["Fund Date"] = pd.to_datetime(df["Fund Date"], errors="coerce")
    df["Fund Price"] = pd.to_numeric(df["Fund Price"], errors="coerce")

    df = df.dropna(subset=["Fund Date", "Fund Price"]).copy()
    df = df.sort_values("Fund Date").reset_index(drop=True)

    if df.empty:
        raise ValueError(f"El archivo '{os.path.basename(ruta_archivo)}' no tiene datos válidos.")

    nombre_fondo = str(df["Fund Name"].dropna().iloc[0]).strip()
    fecha_inicio = df["Fund Date"].min()
    fecha_fin = df["Fund Date"].max()

    return {
        "name": nombre_fondo,
        "start_date": fecha_inicio,
        "end_date": fecha_fin,
        "df_daily": df[["Fund Date", "Fund Price"]].copy()
    }


def convertir_a_mensual(df_daily: pd.DataFrame) -> pd.DataFrame:
    df = df_daily.copy()
    df = df.rename(columns={"Fund Date": "Date", "Fund Price": "Price"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Price"] = pd.to_numeric(df["Price"], errors="coerce")
    df = df.dropna(subset=["Date", "Price"]).sort_values("Date").reset_index(drop=True)

    df["Month"] = df["Date"].dt.to_period("M")
    df = df.groupby("Month", as_index=False).last()
    df["Date"] = df["Month"].dt.to_timestamp("M")
    df = df[["Date", "Price"]].copy()

    df["Return"] = df["Price"].pct_change().fillna(0.0)

    return df


def cargar_todos_los_fondos(data_path: str = "data") -> dict:
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"No existe la carpeta '{data_path}'.")

    archivos = [
        f for f in os.listdir(data_path)
        if f.lower().endswith(".xlsx")
    ]

    if not archivos:
        return {}

    fondos = {}

    for archivo in sorted(archivos):
        ruta = os.path.join(data_path, archivo)

        info = leer_fondo_excel(ruta)
        df_monthly = convertir_a_mensual(info["df_daily"])

        nombre = info["name"] if info["name"] else normalizar_nombre_fondo(archivo)

        fondos[nombre] = {
            "file_name": archivo,
            "start_date": info["start_date"],
            "end_date": info["end_date"],
            "df_daily": info["df_daily"],
            "df_monthly": df_monthly,
        }

    return fondos