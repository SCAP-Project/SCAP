"""Calibracao por validacao e metricas de deteccao, sem ajuste no teste."""

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score,
                             precision_recall_curve, precision_score, recall_score, roc_auc_score)


def choose_threshold(y, scores):
    y, scores = np.asarray(y, dtype=int), np.asarray(scores, dtype=float)
    if set(np.unique(y)) != {0, 1} or not np.isfinite(scores).all():
        raise ValueError("Validacao deve conter as duas classes e scores finitos")
    precision, recall, thresholds = precision_recall_curve(y, scores)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    best = np.flatnonzero(np.isclose(f1, f1.max(), rtol=0, atol=1e-12))[-1]
    return float(thresholds[best])


def compute_metrics(y, scores, threshold):
    y, scores = np.asarray(y, dtype=int), np.asarray(scores, dtype=float)
    predicted = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()
    k = max(1, int(np.ceil(len(y) * 0.05)))
    top = np.argsort(-scores, kind="stable")[:k]
    return dict(
        average_precision=float(average_precision_score(y, scores)),
        roc_auc=float(roc_auc_score(y, scores)), precision=float(precision_score(y, predicted, zero_division=0)),
        recall=float(recall_score(y, predicted, zero_division=0)), f1=float(f1_score(y, predicted, zero_division=0)),
        precision_top_5pct=float(y[top].mean()), recall_top_5pct=float(y[top].sum() / max(y.sum(), 1)),
        alertas=int(predicted.sum()), taxa_alerta=float(predicted.mean()), tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp),
        limiar=float(threshold), n=len(y), anomalias=int(y.sum()), prevalencia=float(y.mean()),
    )
