"""Renders app.py headlessly (no button click, so no model needed) and checks the layout."""
from streamlit.testing.v1 import AppTest


def test_app_renders_and_selects_product():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Retail Product Demand Forecasting"
    assert len(at.selectbox[0].options) == 75
    assert at.number_input[0].value == 28
    assert at.button[0].label == "Generate Forecast"
    at.selectbox[0].select("FOODS_2_019 | Wisconsin - WI_1").run()
    assert not at.exception
    assert "1178 zero-sales days kept" in at.caption[1].value
