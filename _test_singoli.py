"""Smoke test temporaneo: la sezione 'Singoli asset' non solleva eccezioni."""
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=180)
at.run()
assert not at.exception, f"Eccezione al primo run: {at.exception}"

# Passa alla sezione 'Singoli asset' (presente anche in modalita Base).
at.selectbox(key="sezione_builder").set_value("\U0001F4C8 Singoli asset").run()
assert not at.exception, f"Eccezione in Singoli asset: {at.exception}"

print("OK - sezione attiva:", at.session_state["sezione_val"])
print("OK - subheader:", [s.value for s in at.subheader])
print("OK - n. dataframe presenti:", len(at.dataframe))
print("OK - n. caption presenti:", len(at.caption))
