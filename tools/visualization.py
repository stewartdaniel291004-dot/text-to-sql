from __future__ import annotations

import pandas as pd
import plotly.express as px


def make_chart(frame: pd.DataFrame, chart_type: str, x: str, y: str):
    if frame.empty or x not in frame.columns or y not in frame.columns:
        raise ValueError("Choose columns from a non-empty query result.")
    if not pd.api.types.is_numeric_dtype(frame[y]):
        raise ValueError("The chart value column must be numeric.")
    if chart_type == "Pie":
        return px.pie(frame, names=x, values=y, title=f"{y} by {x}")
    if chart_type == "Line":
        return px.line(frame, x=x, y=y, title=f"{y} by {x}", markers=True)
    if chart_type == "Bar":
        return px.bar(frame, x=x, y=y, title=f"{y} by {x}")
    raise ValueError("Select Bar, Line, or Pie.")
