"""Shared result contract for display-only scale standardization curves.

This module deliberately contains no image-processing or reading logic.  It
only normalizes curve arrays and records observed tick evidence so the main
scale and vernier scale diagnostics expose the same shape of result.
"""

from __future__ import annotations

import numpy as np


def _curve(signal, width: int) -> np.ndarray:
    """Return a finite, width-aligned float curve."""
    out = np.zeros(max(0, int(width)), dtype=float)
    if out.size == 0 or signal is None:
        return out
    values = np.asarray(signal, dtype=float).reshape(-1)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    out[:min(out.size, values.size)] = values[:out.size]
    return out


def empty_standardization(width: int, x_offset: int = 0) -> dict:
    """Create an empty diagnostic result for missing or invalid evidence."""
    width = max(0, int(width))
    return {
        'version': 1,
        'width': width,
        'x_offset': int(x_offset),
        'curves': {
            'raw_projection': np.zeros(width, dtype=float),
            'support': np.zeros(width, dtype=float),
            'normalized_response': np.zeros(width, dtype=float),
        },
        'ticks': [],
        'classification': {
            'mode': 'unknown',
            'centers': [],
            'counts': [],
            'separation': 0.0,
            'threshold': None,
        },
    }


def build_standardization_result(
    width: int,
    x_offset: int,
    raw_projection,
    support,
    normalized_response,
    tick_records: list[dict] | None,
    classification: dict | None,
) -> dict:
    """Build a width-aligned display-only standardization result.

    Tick records are copied shallowly so callers can continue to own and
    mutate their formal detection dictionaries without changing this snapshot.
    """
    result = empty_standardization(width, x_offset)
    result['curves'] = {
        'raw_projection': _curve(raw_projection, result['width']),
        'support': _curve(support, result['width']),
        'normalized_response': _curve(
            normalized_response, result['width']
        ),
    }
    result['ticks'] = [dict(record) for record in (tick_records or [])]
    if classification:
        result['classification'].update(dict(classification))
    return result
