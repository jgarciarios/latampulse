"""
dashboard/app.py — Dashboard interactivo de LatamPulse.
Corré con: streamlit run dashboard/app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="LatamPulse — Costo de vida en LATAM",
    page_icon="🌎",
    layout="wide",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

COUNTRY_NAMES = {"AR": "Argentina", "BR": "Brasil", "UY": "Uruguay", "CO": "Colombia"}
COUNTRY_COLORS = {"AR": "#75AADB", "BR": "#009C3B", "UY": "#0038A8", "CO": "#FCD116"}


@st.cache_data
def load_data():
    prices = pd.read_csv(PROCESSED_DIR / "prices.csv")
    ppp_factors = pd.read_csv(PROCESSED_DIR / "ppp_factors.csv")
    inflation = pd.read_csv(PROCESSED_DIR / "inflation_indices.csv")
    inflation["period"] = pd.to_datetime(inflation["period"])
    return prices, ppp_factors, inflation


def compute_monthly_pct(country_code: str, config: dict, df: pd.DataFrame) -> pd.DataFrame:
    ind_name, ind_type = config["name"], config["type"]
    sub = df[(df["country_code"] == country_code) & (df["indicator"] == ind_name)].copy()
    sub = sub.sort_values("period").reset_index(drop=True)

    if ind_type == "direct_pct":
        return sub[["country_code", "period", "value"]].dropna()

    sub["value"] = sub["value"].pct_change() * 100
    period_m = sub["period"].dt.to_period("M").astype("int64")
    gap = period_m.diff()
    sub.loc[gap != 1, "value"] = pd.NA
    return sub[["country_code", "period", "value"]].dropna()


INDICATOR_MAP = {
    "BR": {"name": "ipca_variacao_mensal", "type": "direct_pct"},
    "AR": {"name": "indec_0_variacion_mensual", "type": "direct_pct"},
    "CO": {"name": "ipc_indice", "type": "level"},
    "UY": {"name": "ipc_indice", "type": "level"},
}

try:
    prices, ppp_factors, inflation = load_data()
except FileNotFoundError as e:
    st.error(
        f"No encontré los archivos de datos ({e}). "
        f"Corré `python -m src.run_pipeline` primero para generar "
        f"data/processed/."
    )
    st.stop()

st.title("🌎 LatamPulse")
st.markdown(
    "**Costo de vida y poder adquisitivo en Argentina, Brasil, Uruguay y Colombia.** "
    "Comparación en USD nominal (tipo de cambio del día) vs. USD PPP "
    "(ajustado por poder de compra real) — la brecha entre ambos es la historia."
)

tab1, tab2, tab3, tab4 = st.tabs([
    "💵 Precios comparables", "⚖️ Nominal vs PPP", "📈 Inflación", "🌍 Poder adquisitivo"
])

with tab1:
    st.subheader("Precio en USD PPP por ítem y país")

    items_por_pais = prices.groupby("item_name")["country"].nunique()
    items_comparables = sorted(items_por_pais[items_por_pais >= 2].index.tolist())

    if not items_comparables:
        st.warning("No hay ítems presentes en 2 o más países todavía.")
    else:
        seleccion = st.multiselect(
            "Filtrar ítems (vacío = todos)",
            options=items_comparables,
            default=items_comparables,
        )
        seleccion = seleccion or items_comparables

        comparables_df = prices[prices["item_name"].isin(seleccion)].copy()
        comparables_df["País"] = comparables_df["country"].map(COUNTRY_NAMES)

        fig = px.bar(
            comparables_df,
            x="item_name",
            y="price_usd_ppp",
            color="País",
            barmode="group",
            color_discrete_map={COUNTRY_NAMES[k]: v for k, v in COUNTRY_COLORS.items()},
            labels={"item_name": "", "price_usd_ppp": "USD (PPP)"},
        )
        fig.update_layout(xaxis_tickangle=-30, height=550)
        st.plotly_chart(fig, width='stretch')

    with st.expander("Ver tabla completa"):
        st.dataframe(
            prices[["country", "category", "item_name", "price_local", "currency", "price_usd_ppp", "source"]]
            .sort_values(["item_name", "country"]),
            width='stretch',
        )

with tab2:
    st.subheader("USD nominal vs USD PPP")
    st.caption(
        "⚠️ Gap conocido: solo hay tipo de cambio nominal extraído para Argentina. "
        "Para Brasil/Uruguay/Colombia, esta comparación no está disponible todavía."
    )

    ar_con_nominal = prices[(prices["country"] == "AR") & (prices["price_usd_nominal"].notna())].copy()

    if ar_con_nominal.empty:
        st.info("No hay filas de Argentina con USD nominal calculado todavía.")
    else:
        ar_con_nominal = ar_con_nominal.sort_values("price_usd_ppp", ascending=False)

        fig = go.Figure()
        fig.add_bar(name="USD nominal", x=ar_con_nominal["item_name"], y=ar_con_nominal["price_usd_nominal"])
        fig.add_bar(name="USD PPP", x=ar_con_nominal["item_name"], y=ar_con_nominal["price_usd_ppp"])
        fig.update_layout(barmode="group", xaxis_tickangle=-30, height=550, yaxis_title="USD")
        st.plotly_chart(fig, width='stretch')

        gap_promedio = (ar_con_nominal["price_usd_ppp"] / ar_con_nominal["price_usd_nominal"]).mean()
        st.metric(
            "Brecha promedio (PPP / nominal)",
            f"{gap_promedio:.1f}x",
            help="Cuántas veces más 'caro' se ve un ítem en PPP respecto al nominal.",
        )

with tab3:
    st.subheader("Inflación mensual comparada (%)")
    st.caption(
        "Normalizado a la misma unidad entre las 4 fuentes. Los huecos de meses "
        "faltantes se detectan y se excluyen en vez de mostrarse como variación mensual real."
    )

    meses_a_mostrar = st.slider("Meses a mostrar", min_value=6, max_value=48, value=24, step=6)

    series = [compute_monthly_pct(c, cfg, inflation) for c, cfg in INDICATOR_MAP.items()]
    unified_inflation = pd.concat(series, ignore_index=True)
    unified_inflation["País"] = unified_inflation["country_code"].map(COUNTRY_NAMES)

    fig = go.Figure()
    for country_code in INDICATOR_MAP:
        sub = unified_inflation[unified_inflation["country_code"] == country_code].sort_values("period")
        sub = sub.tail(meses_a_mostrar)
        fig.add_scatter(
            x=sub["period"], y=sub["value"], mode="lines+markers",
            name=COUNTRY_NAMES[country_code],
            line=dict(color=COUNTRY_COLORS[country_code]),
        )
    fig.add_hline(y=0, line_color="gray", line_width=0.8)
    fig.update_layout(height=550, yaxis_title="Variación mensual (%)", xaxis_title="")
    st.plotly_chart(fig, width='stretch')

with tab4:
    st.subheader("GDP per cápita, PPP (World Bank)")

    ppp_sorted = ppp_factors.sort_values("gdp_per_capita_ppp_current", ascending=False).copy()
    ppp_sorted["País"] = ppp_sorted["country_code"].map(COUNTRY_NAMES)

    fig = px.bar(
        ppp_sorted, x="País", y="gdp_per_capita_ppp_current",
        text=ppp_sorted["year"].astype(int).astype(str),
        color="country_code",
        color_discrete_map=COUNTRY_COLORS,
        labels={"gdp_per_capita_ppp_current": "USD (PPP)"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=500, showlegend=False)
    st.plotly_chart(fig, width='stretch')

st.divider()
st.caption(
    "Fuentes: dolarapi.com, World Bank, IBGE/SIDRA, DANE, INE Uruguay (vía DGI), INDEC, "
    "y research manual verificado con fuente y fecha por precio. "
    "Metodología completa en AGENTS.md del repositorio."
)
