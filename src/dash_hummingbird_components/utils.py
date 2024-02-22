import logging
from typing import Dict, List, Tuple

import colorlover
import pandas as pd

__all__ = ["list_to_id_dict", "list_to_label_dict", "discrete_background_color_bins"]

logger = logging.getLogger("dhc")


def list_to_id_dict(listable: List[str], **kwargs) -> List[Dict[str, str]]:
    """Generates a dash compliant ID dictionary from a list of strings.

    Parameters
    ----------
    listable : List[str]
        The strings/ids/names
    kwargs : dict, optional
        Additional options given to each element, by default {}

    Returns
    -------
    List[Dict[str, str]]
        List of dictionaries of the form
        ```py3
        {"name": "id", "id": "id"}
        ```
    """
    return [{"name": k, "id": k, **kwargs} for k in listable]


def list_to_label_dict(listable: List[str], **kwargs) -> List[Dict[str, str]]:
    """Generates a dash compliant label dictionary from a list of strings.

    Parameters
    ----------
    listable : List[str]
        The strings/labels/names

    Returns
    -------
    List[Dict[str, str]]
        List of dictionaries of the form
        ```py3
        {"label": "soemthing", "value": "somthing"}
        ```
    """
    return [{"label": str(k), "value": str(k), **kwargs} for k in listable]


def discrete_background_color_bins(df: pd.DataFrame, n_bins: int = 5, lim: Tuple[float] = None) -> List[Dict]:
    """Generates a color-grading background for this DataFrame. Note that the colormap is not per column but for
    all the columns in the DataFrame.

    Output to use to contain the these styles:

    ``py3
    Output("table-id", "style_data_conditional"),
    ```

    Parameters
    ----------
    df : pd.DataFrame
        The data to construct a combined color-grading for
    n_bins : int, optional
        Number of color steps, by default 5
    lim : Tuple[float], optional
        A manual limit range for the color, otherwise min and max from the data, by default None

    Returns
    -------
    List[Dict]
        The style queries as mandated by DASH.
    """
    bounds = [i * (1.0 / n_bins) for i in range(n_bins + 1)]
    c_max, c_min = (None, None) if lim is None or lim is False else lim
    if c_max is None:
        c_max = df.max(numeric_only=True).max()
    if c_min is None:
        c_min = df.min(numeric_only=True).min()
    ranges = [((c_max - c_min) * i) + c_min for i in bounds]
    styles = []
    for i in range(1, len(bounds)):
        min_bound = ranges[i - 1]
        max_bound = ranges[i]
        backgroundColor = colorlover.scales[str(n_bins)]["seq"]["Blues"][i - 1]
        color = "white" if i > len(bounds) / 2.0 else "inherit"

        for column in df:
            styles.append(
                {
                    "if": {
                        "filter_query": (
                            "{{{column}}} >= {min_bound}"
                            + (" && {{{column}}} < {max_bound}" if (i < len(bounds) - 1) else "")
                        ).format(column=column, min_bound=min_bound, max_bound=max_bound),
                        "column_id": column,
                    },
                    "backgroundColor": backgroundColor,
                    "color": color,
                }
            )
    return styles
