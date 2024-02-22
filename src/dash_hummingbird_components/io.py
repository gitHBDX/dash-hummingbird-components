import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Output, dash_table, no_update

from . import (discrete_background_color_bins, list_to_id_dict,
               list_to_label_dict)

logger = logging.getLogger("dhc")


def OptionsOutput(name: str) -> Tuple[Output, Output]:
    """`value` and `options` outputs for a element with id `name`, as a macro.

    Use as:

    ```py3
    @app.callback(
        *OptionsOutput("some-dropdown"),
        Input("some-input")
    )
    def callback_function(var):
        list_of_options = ["option1", "option2", …]
        return options_output(list_of_options)
    ```

    Parameters
    ----------
    name : str
        Name of the element

    Returns
    -------
    Tuple[Output, Output]
        The two outputs in a tuple
    """
    return (Output(name, "value"), Output(name, "options"))


def options_output(listable: List[str], all: bool = False, value: str = None) -> Tuple[str, Dict[str, str]]:
    """Return tuple for a `OptionsOutput`

    Use as:

    ```py3
    @app.callback(
        *OptionsOutput("some-dropdown"),
        Input("some-input")
    )
    def callback_function(var):
        list_of_options = ["option1", "option2", …]
        return options_output(list_of_options)
    ```

    Parameters
    ----------
    listable : List[str]
        The list of options
    all : bool, optional
        Whether all options should be pre-selected (for multi-select), by
        default False

    Returns
    -------
    Tuple[str, Dict[str, str]]
        The outputs for the value and the options
    """
    if len(listable) == 0:
        value = None
    elif value is None:
        if all is True:
            value = list(map(str, listable))
        else:
            value = str(listable[0])
    else:
        if isinstance(value, list):
            value = list(map(str, value))
        else:
            value = str(value)
            if value not in listable:
                value = str(listable[0])
    return value, list_to_label_dict(listable)


def TableOutput(name: str) -> Tuple[Output, Output]:
    """`columns` and `data` outputs for a element with id `name`, as a macro.

    Use as:

    ```py3
    @app.callback(
        *TableOutput("some-table"),
        Input("some-input")
    )
    def callback_function(var):
        table = pd.DataFrame(…)
        return table_output(table, round=True)
    ```

    Parameters
    ----------
    name : str
        Name of the element

    Returns
    -------
    Tuple[Output, Output]
        The outputs in a tuple
    """
    return (Output(name, "columns"), Output(name, "data"), Output(name, "style_data_conditional"))


def table_output(
    df: pd.DataFrame,
    round: bool = True,
    markdown: List[str] = None,
    editable: List[str] = None,
    hideable: bool = False,
    precision: int = 4,
    color: List[str] = None,
    color_lim: Tuple[float] = None,
    format_dict: Dict[str, str] = None,
    styles: List[dict] = [],
    as_kwargs: bool = False,
) -> Tuple[Dict[str, str], Dict, Dict]:
    """Return tuple for a `TableOutput`

    Use as:

    ```py3
    @app.callback(
        *TableOutput("some-table"),
        Input("some-input")
    )
    def callback_function(var):
        table = pd.DataFrame(…)
        return table_output(table, round=True)
    ```

    Parameters
    ----------
    df : pd.DataFrame
        The data to put into the table.
    round : bool, optional
        Whether to round the numerical data in it, by default True
    markdown : List[str], optional
        List of columns which contain markdown data, by default None
    hideable : bool, optional
        Whether the columns shall be hideable, by default False
    precision : int, optional
        Precision to round the numerical columns to, by default 4
    color : List[str], optional
        List of columns that should be colored, by default None
    color_lim : Tuple[float], optional
        Optional manual limit for the colormapping, by default None
    format_dict : Dict[str, str], optional
        Optional formatting of columns, by default None

    Returns
    -------
    Tuple[Dict[str, str], Dict, Dict]
        Outputs as a tuple
    """
    if df is None:
        return (no_update,) * 3

    if not isinstance(df, pd.DataFrame):
        return df

    if round:
        float_df = df.select_dtypes(float).round(precision)
        df[float_df.columns] = float_df

    levels = df.columns.nlevels
    columns = []
    data = []
    # check for hierarchical columns or normal columns
    if levels == 1:
        if len(df.columns) > 0:
            df.columns = df.columns.str.replace("_", " ")
            columns = list_to_id_dict(df.columns, hideable=hideable)
            data = df.to_dict("records")
    else:
        ids = ["".join([col for col in multi_col if col]) for multi_col in list(df.columns)]
        # build columns list from ids and columns of the dataframe
        columns = [{"name": list(col), "id": id_} for col, id_ in zip(list(df.columns), ids)]
        # build data list from ids and rows of the dataframe
        data = [{k: v for k, v in zip(ids, row)} for row in df.values]

    if markdown is not None:
        markdown = [c.replace("_", " ") for c in markdown]
        _columns = []
        for c in columns:
            if c["id"] in markdown:
                _columns.append({**c, "presentation": "markdown"})
            else:
                _columns.append(c)
        columns = _columns

    if editable is not None:
        editable = [c.replace("_", " ") for c in editable]
        _columns = []
        for c in columns:
            if c["id"] in editable:
                _columns.append({**c, "editable": True})
            else:
                _columns.append(c)
        columns = _columns

    if format_dict is not None:
        format_dict = {k.replace("_", " "): v for k, v in format_dict.items()}
        _columns = []
        for c in columns:
            if c["id"] in format_dict.keys():
                if format_dict[c["id"]] == "money":
                    column_format = dash_table.FormatTemplate.money(2)
                    column_type = "numeric"
                elif format_dict[c["id"]] == "percentage":
                    column_format = dash_table.FormatTemplate.percentage(2)
                    column_type = "numeric"
                else:
                    print(f"{format_dict[c['id']]} Not found in formats!")
                    _columns.append(c)
                    continue

                _columns.append({**c, "format": column_format, "type": column_type})
            else:
                _columns.append(c)
        columns = _columns

    if color is not None and styles is not None and styles is not False:
        numerical_columns = df.select_dtypes("number").columns.tolist()
        if color is True:
            color = numerical_columns
        else:
            if isinstance(color, str):
                color = [color]
            color = list({c.replace("_", " ") for c in color} & set(numerical_columns))

        for column in color:
            styles.extend(discrete_background_color_bins(df[[column]], lim=color_lim))

    if as_kwargs:
        return {"columns": columns, "data": data, "style_data_conditional": styles}
    else:
        return columns, data, styles


def GraphOutput(name: str) -> Tuple[Output, Output]:
    """`figure` and `config` outputs for a element with id `name`, as a macro.

    Use as:

    ```py3
    @app.callback(
        *GraphOutput("some-graph-id"),
        Input("some-input")
    )
    def callback_function(var):
        figure = go.Figure
        return graph_output(figure, "figure-title")
    ```

    Parameters
    ----------
    name : str
        The Name of the element

    Returns
    -------
    Tuple[Output, Output]
        Tuple of the two outputs
    """
    return (Output(name, "figure"), Output(name, "config"))


def graph_output(fig: go.Figure, name: str = "classifynder") -> Tuple[go.Figure, Dict]:
    """Return tuple for a `GraphOutput`

    Use as:

    ```py3
    @app.callback(
        *GraphOutput("some-graph-id"),
        Input("some-input")
    )
    def callback_function(var):
        figure = go.Figure
        return graph_output(figure, "figure-title")
    ```

    Parameters
    ----------
    fig : go.Figure
        The plotly figure to plot
    name : str
        Name of the graph, used for the saving images on the UI, default
        "classifynder"

    Returns
    -------
    Tuple[go.Figure, Dict]
        the two things for the outputs
    """
    try:
        fig.update_layout(margin=dict(l=0, r=0, pad=0, b=20, t=30))
    except:
        pass
    return fig, {
        "displaylogo": False,
        "scrollZoom": False,
        "modeBarButtonsToRemove": ["autoScale", "lasso2d", "zoomIn", "zoomOut"],
        "toImageButtonOptions": {
            "format": "png",  # one of png, svg, jpeg, webp
            "filename": name.replace("/", "__"),
            "height": None,
            "width": None,
            "scale": 2,
        },
    }
