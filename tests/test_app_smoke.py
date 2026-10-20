"""Executes app.py against a stub of Streamlit (no browser needed) to catch pandas/runtime errors.
Usage:  python -m tests.test_app_smoke"""
import runpy
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def metric(self, *a, **k): return None
    def __getattr__(self, n): return lambda *a, **k: None


class Side:
    def radio(self, label, options, index=0, **k): return options[index]
    def multiselect(self, label, options, default=None, **k): return list(default or [])
    def date_input(self, label, value=None, **k): return value
    def button(self, *a, **k): return False
    def __getattr__(self, n): return lambda *a, **k: None


class CacheData:
    cleared = 0
    def __call__(self, *a, **k):
        if a and callable(a[0]): return a[0]
        return lambda fn: fn
    def clear(self): CacheData.cleared += 1


class ST(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.sidebar, self.cache_data, self.rendered = Side(), CacheData(), 0
        self.session_state = {}

    def fragment(self, *a, **k):
        if a and callable(a[0]): return a[0]
        return lambda fn: fn

    def rerun(self): raise SystemExit("st.rerun() called")

    def tabs(self, names): return [Ctx() for _ in names]
    def columns(self, n, **k): return [Ctx() for _ in range(n if isinstance(n, int) else len(n))]
    def selectbox(self, label, options, **k): return list(options)[0]
    def radio(self, label, options, **k): return options[0]
    def multiselect(self, label, options, default=None, **k): return list(default or [])
    def stop(self): raise SystemExit("st.stop() called")
    def dataframe(self, obj, **k):
        self.rendered += 1
        if hasattr(obj, "to_html"): obj.to_html()
    def button(self, *a, **k): return False
    def __getattr__(self, n): return lambda *a, **k: None


st = ST()
sys.modules["streamlit"] = st
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
print(f"app.py ran without errors; {st.rendered} tables rendered")
