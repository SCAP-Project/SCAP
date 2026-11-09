"""Identidade visual: azul, fundo branco, sem grades e com unidades explicitas."""

from pathlib import Path
import textwrap

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd

from .config import REPORTS

BLUE = "#2166AC"
NAVY = "#123B63"
LIGHT = "#A9CAE8"
PALETTE = [NAVY, BLUE, "#5B98CC", LIGHT, "#DBEAF6"]


def configure_style():
    plt.rcParams.update({
        "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
        "axes.grid": False, "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#CBD5E1", "axes.labelcolor": "#42566B", "text.color": NAVY,
        "xtick.color": "#536578", "ytick.color": "#536578", "font.family": "DejaVu Sans",
        "font.size": 10, "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "figure.dpi": 110, "savefig.dpi": 180, "axes.prop_cycle": plt.cycler(color=PALETTE),
    })


def compact(value, _=None):
    if abs(value) >= 1e6:
        return f"{value / 1e6:.1f} mi".replace(".", ",")
    if abs(value) >= 1e3:
        return f"{value / 1e3:.1f} mil".replace(".", ",")
    return f"{value:.0f}"


def canvas(title, subtitle="", size=(11, 4.8)):
    configure_style()
    fig, ax = plt.subplots(figsize=size)
    ax.set_title(title, pad=35)
    ax.text(0, 1.035, subtitle, transform=ax.transAxes, fontsize=9, color="#64788D", va="bottom")
    ax.grid(False)
    ax.tick_params(axis="both", length=0, pad=8)
    fig.subplots_adjust(left=0.10, right=0.94, top=0.79, bottom=0.18)
    return fig, ax


def barh(series, title, subtitle="", xlabel="Registros", top=12):
    series = series.sort_values(ascending=False).head(top).iloc[::-1]
    fig, ax = canvas(title, subtitle, size=(11, max(4.3, len(series) * 0.32 + 2)))
    positions = np.arange(len(series))
    ax.barh(positions, series.to_numpy(), color=[BLUE] * max(len(series) - 1, 0) + [NAVY], height=0.65)
    ax.set_yticks(positions, [textwrap.fill(str(s), width=28) for s in series.index], fontsize=9)
    upper = max(float(series.max()), 1)
    ax.set_xlim(0, upper * 1.22)
    for position, value in zip(positions, series):
        ax.text(float(value) + upper * 0.015, position, compact(value), va="center", fontsize=9, color=NAVY)
    ax.xaxis.set_major_formatter(FuncFormatter(compact))
    ax.set_xlabel(xlabel)
    ax.spines["left"].set_visible(False)
    fig.subplots_adjust(left=0.27)
    return fig


def line(frame, title, subtitle="", ylabel="Valor (R$)", fill=False):
    if isinstance(frame, pd.Series):
        frame = frame.to_frame()
    fig, ax = canvas(title, subtitle)
    for index, column in enumerate(frame.columns):
        ax.plot(frame.index, frame[column], label=str(column), linewidth=2.1, color=PALETTE[index % len(PALETTE)])
        if fill and len(frame.columns) == 1:
            ax.fill_between(frame.index, frame[column].to_numpy(dtype=float), alpha=0.12, color=BLUE)
    ax.set_ylabel(ylabel)
    ax.yaxis.set_major_formatter(FuncFormatter(compact))
    if isinstance(frame.index, pd.DatetimeIndex):
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    if len(frame.columns) > 1:
        ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.margins(x=0.02)
    return fig


def histogram(values, title, subtitle="", xlabel="Valor (R$)", log=False):
    values = pd.Series(values).dropna().to_numpy(dtype=float)
    fig, ax = canvas(title, subtitle)
    bins = np.geomspace(max(values.min(), 0.01), values.max(), 38) if log and values.max() > values.min() else 30
    ax.hist(values, bins=bins, color=BLUE, edgecolor="white", linewidth=0.6)
    if log:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Registros")
    ax.xaxis.set_major_formatter(FuncFormatter(compact))
    ax.yaxis.set_major_formatter(FuncFormatter(compact))
    return fig


def save_figure(fig, name, folder="eda"):
    destination = REPORTS / "figures" / folder
    destination.mkdir(parents=True, exist_ok=True)
    for suffix in ["png", "svg"]:
        fig.savefig(destination / f"{name}.{suffix}", bbox_inches="tight")


def style_table(frame):
    return frame.style.hide(axis="index").set_properties(**{"font-size": "12px", "padding": "8px 12px", "text-align": "left"}).set_table_styles([
        {"selector": "th", "props": [("background", NAVY), ("color", "white"), ("padding", "9px 12px"), ("text-align", "left")]},
        {"selector": "tbody tr:nth-child(even)", "props": [("background", "#F0F6FC")]},
        {"selector": "table", "props": [("border-collapse", "collapse"), ("width", "100%")]},
    ])
