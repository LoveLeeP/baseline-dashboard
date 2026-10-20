#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 check_kobo.py
streamlit run app.py
