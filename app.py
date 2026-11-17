"""Retail Product Demand Forecasting - Phase 1 dashboard. Run: streamlit run app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from rdf import config
from rdf.data_loader import get_series, list_series, load_sales, series_summary
from rdf.forecaster import ForecastError, forecast, load_pipeline
from rdf.plotting import combined_figure, history_figure

st.set_page_config(page_title="Retail Product Demand Forecasting", layout="wide")


@st.cache_data(show_spinner="Loading sales data...")
def cached_sales():
    return load_sales()


@st.cache_resource(show_spinner="Loading Amazon Chronos-2 (first run downloads weights)...")
def cached_model():
    return load_pipeline()


st.title("Retail Product Demand Forecasting")
st.caption("Zero-shot demand forecasts from Amazon Chronos-2")

try:
    sales = cached_sales()
except Exception as e:
    st.error(f"Could not load sales data: {e}")
    st.stop()

c1, c2 = st.columns([3, 1])
series_id = c1.selectbox("Product | Store", list_series(sales))
horizon = c2.number_input("Forecast horizon (days)", config.MIN_HORIZON, config.MAX_HORIZON,
                          config.DEFAULT_HORIZON, step=7)

history = get_series(sales, series_id)
info = series_summary(history)
st.caption(f"{info['days']} days ({info['start']} to {info['end']}) | "
           f"{info['zero_days']} zero-sales days kept | {info['missing_days']} missing days")
st.plotly_chart(history_figure(history), use_container_width=True)

if st.button("Generate Forecast", type="primary"):
    try:
        with st.spinner("Loading model..."):
            pipeline, device = cached_model()
        with st.spinner(f"Running Chronos-2 inference on {device.upper()}..."):
            result = forecast(pipeline, history, int(horizon), series_id)
        st.session_state["result"] = (series_id, int(horizon), device, result)
    except ForecastError as e:
        st.session_state.pop("result", None)
        st.error(str(e))

saved = st.session_state.get("result")
if saved and saved[0] == series_id:
    _, h, device, res = saved
    st.subheader("Forecast")
    st.plotly_chart(combined_figure(history, res), use_container_width=True)
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Total predicted demand ({h} days)", f"{res['mean'].sum():,.0f} units")
    m2.metric("Average daily predicted demand", f"{res['mean'].mean():,.1f} units")
    m3.metric("Forecast period", f"{res['date'].min():%d %b} - {res['date'].max():%d %b %Y}")
    with st.expander("Forecast table"):
        st.dataframe(res.round(2), use_container_width=True, hide_index=True)
    st.caption("Point forecast = Chronos-2 mean prediction. Negative values are clipped to 0.")

with st.expander("Model information", expanded=False):
    st.markdown(
        f"- **Model:** Amazon Chronos-2 (`{config.MODEL_ID}`), 120M parameters, pretrained, zero-shot\n"
        "- **Library:** `chronos-forecasting` (official), `Chronos2Pipeline.predict_df`\n"
        "- **Input:** this product's full daily sales history, no fine-tuning\n"
        + (f"- **Last run device:** {saved[2].upper()}" if saved else "- **Device:** chosen when the model loads")
    )
