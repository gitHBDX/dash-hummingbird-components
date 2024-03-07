import base64
import io
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import dash_daq
import dash_mantine_components as dmc
import pandas as pd
import plotly.io as pio
import dash_mantine_components as dmc
from dash import (ALL, MATCH, Input, Output, State, callback, ctx, dash_table,
                  dcc, get_asset_url, html, no_update)
from dash_iconify import DashIconify

from . import DATA_PATH, DATASETS, exec

__all__ = ["DataSetPicker", "HTMLTable", "NotebookStarter", "PueueLog", "TagList", "PathSelector", "PlotDownloadButton"]
logger = logging.getLogger("dhc")


def titelize(s: str) -> str:
    return s.replace("_", " ").replace("-", " ").title()


__old_datatable_init = dash_table.DataTable.__init__
__data_table_defaults = dict(
    style_cell={
        "whiteSpace": "normal",
        "height": "auto",
    },
)


def __new_datatable_init(self, *args, **kwargs):
    __old_datatable_init(self, *args, **{**__data_table_defaults, **kwargs})


dash_table.DataTable.__init__ = __new_datatable_init


class NotebookStarter:
    def __new__(_, name, parameters={}):
        param_string = json.dumps(parameters)
        id_ = f"{name}__{param_string}"

        return html.A(
            dmc.Button(
                "Generate notebook",
                leftIcon=DashIconify(icon="logos:jupyter"),
            ),
            id={"module": "notebookstarter", "id": id_},
            n_clicks=0,
            target="_blank",
        )


@callback(
    Output({"module": "notebookstarter", "id": MATCH}, "children"),
    Output({"module": "notebookstarter", "id": MATCH}, "href"),
    Input({"module": "notebookstarter", "id": MATCH}, "n_clicks"),
    State({"module": "notebookstarter", "id": MATCH}, "id"),
    State({"module": "notebookstarter", "id": MATCH}, "className"),
)
def __create_notebook(n_clicks, id_, className):
    if ctx.triggered_id is None or n_clicks == 0 or "activated" in className:
        return no_update
    id_ = id_["id"]
    name = id_.split("__")[0]
    parameters = json.loads(id_[len(name) + 2 :])
    link = exec.start_notebook(name, parameters)

    return (
        dmc.Button("Open notebook", leftIcon=DashIconify(icon="logos:jupyter"), color="lime"),
        link,
    )


class DataSetPicker:
    @staticmethod
    def _absolute_layout(id_, value=None):
        return [
            dmc.Button(
                "From list",
                id={"module": "datasetpicker", "attr": "switch", "id": id_},
                variant="subtle"
            ),
            dmc.TextInput(id={"module": "datasetpicker", "attr": "file", "id": id_}, value=value,
                            label="Path", description="Enter an absolute path to the AnnData", placeholder="Enter a path"
                          ),
        ]

    @staticmethod
    def _list_layout(id_, folder=None, file=None):
        options, value = [], None
        if folder is not None and folder in DATASETS:
            options = [{"label": f, "value": f"{folder}/{f}"} for f in DATASETS[folder]]
            if file is not None:
                value = f"{folder}/{file}"

        return [
            dmc.Button(
                "From path",
                id={"module": "datasetpicker", "attr": "switch", "id": id_},
                variant="subtle"
            ),
            dmc.Group(
                [
                            dmc.Select(
                                id={"module": "datasetpicker", "attr": "folder", "id": id_},
                                data=[{"label": value, "value": value} for value in DATASETS.keys()],
                                value=folder,
                                label="Folder",
                                description="Select a folder", 
                                placeholder="Select a folder",
                            ),
                            dmc.Select(
                                id={"module": "datasetpicker", "attr": "file", "id": id_},
                                value=value,
                                data=options,
                                label="File",
                                description="Select a file",
                                placeholder="Select a file",
                            ),
                ],
            ),
        ]

    def __new__(_, id_, value=None, style=None):
        if value is None or value == "" or value == "None":
            form = DataSetPicker._list_layout(id_)
        else:
            import anndata_cache

            key = anndata_cache.Key(value)
            if key.location == anndata_cache.CacheLocation.CACHED:
                folder, file = key.name.split("/")
                form = DataSetPicker._list_layout(id_, folder, file)
            else:
                form = DataSetPicker._absolute_layout(id_, key.name)
        return html.Fieldset(
            [
                html.Legend(titelize(id_)),
                dmc.Stack(form, id={"module": "datasetpicker", "attr": "container", "id": id_}, align="end", spacing="0"),
                html.Span(className="errorbox", id={"module": "datasetpicker", "attr": "error", "id": id_}),
                dcc.Input(id={"module": "datasetpicker", "id": id_}, type="hidden", value=value),
            ],
            style=style,
        )


@callback(
    Output({"module": "datasetpicker", "attr": "container", "id": MATCH}, "children"),
    Input({"module": "datasetpicker", "attr": "switch", "id": MATCH}, "n_clicks"),
    State({"module": "datasetpicker", "attr": "switch", "id": MATCH}, "id"),
    State({"module": "datasetpicker", "attr": "switch", "id": MATCH}, "children"),
)
def __datasetpicker_switch_layout_callback(n_clicks, id_, button_text):
    if n_clicks is None:
        return no_update
    if button_text == "From list":
        return DataSetPicker._list_layout(id_["id"])
    else:
        return DataSetPicker._absolute_layout(id_["id"])


@callback(
    Output({"module": "datasetpicker", "attr": "file", "id": MATCH}, "data"),
    Input({"module": "datasetpicker", "attr": "folder", "id": MATCH}, "value"),
    prevent_initial_call=True,
)
def __datasetpicker_folder_file_dropdown_callback(folder):
    if folder is None:
        return no_update
    return [{"label": f, "value": f"{folder}/{f}"} for f in DATASETS[folder]]


@callback(
    Output({"module": "datasetpicker", "attr": "error", "id": MATCH}, "children"),
    Output({"module": "datasetpicker", "id": MATCH}, "value"),
    Input({"module": "datasetpicker", "attr": "file", "id": MATCH}, "value"),
)
def __datasetpicker_file_not_exists_error_callback(file):
    if file is None:
        return "", no_update
    if not Path(file).exists() and not (Path(DATA_PATH) / (file + ".h5ad")).exists():
        return f"does not exist", no_update
    return "", file


class HTMLTable:
    def __new__(_, data, **kwargs):
        if data is None:
            return html.Div()
        elif isinstance(data, dict):
            return HTMLTable.from_dict(data, **kwargs)
        elif isinstance(data, pd.DataFrame):
            return HTMLTable.from_dataframe(data, **kwargs)
        else:
            raise NotImplementedError(f"Cannot create HTML table from {type(data)}")

    @staticmethod
    def _value(value: Any):
        if isinstance(value, float):
            return f"{value:.4f}"
        else:
            return value

    @staticmethod
    def from_dict(data: dict, titelized: bool = False, columns: List[str] = None, tr_kwargs: dict = None):
        data = pd.DataFrame({"index": list(data.keys()), "value": list(data.values())})
        if columns is not None:
            data = data.set_axis(columns, axis=1)

        return HTMLTable.from_dataframe(data, titelized, header=columns is not None, tr_kwargs=tr_kwargs)

    @staticmethod
    def from_dataframe(data: pd.DataFrame, titelized: bool = False, header: bool = True, tr_kwargs: dict = None, style=None):
        if tr_kwargs is None:
            tr_kwargs = {}
        table = []
        if header:
            table.append(html.Thead(html.Tr([html.Th(c) for c in data.columns])))
        tbody = []
        for row_values in data.values:
            idx = row_values[0]
            row = [html.Td(titelize(idx) if titelized else idx)]
            for value in row_values[1:]:
                row.append(html.Td(HTMLTable._value(value)))
            tbody.append(html.Tr(row, **tr_kwargs.get(idx, {})))
        table.append(html.Tbody(tbody))
        return dmc.Table(table, style=style)


class PueueLog:
    __registered_callbacks = set()

    def __new__(_, id: str, task_id: str = None, is_live: bool = False, full: bool = False):
        if not id in PueueLog.__registered_callbacks:
            logger.warn("PueueLog callback not registered. Please, execute dhc.PueueLog.register_callbacks(id_) somewhere in the main app.")
        return html.Section(
            [
                html.H2(id=f"{id}_title"),
                dcc.Input(id=id, type="hidden", value=task_id),
                html.Aside(
                    [
                        dash_daq.BooleanSwitch(
                            id=f"{id}_live",
                            on=is_live,
                            label="Live update",
                            labelPosition="top",
                        ),
                        dash_daq.BooleanSwitch(
                            id=f"{id}_full",
                            on=full,
                            label="Display full log",
                            labelPosition="top",
                        ),
                        html.Div([html.Button("Kill", type="button", id=f"{id}_kill", disabled=False)]),
                        html.Div([html.Button("Queue again", type="button", id=f"{id}_queue", disabled=False)]),
                    ],
                    className="columns",
                ),
                html.Div("Loading...", id=f"{id}_log"),
            ],
            id=f"{id}_container",
        )

    @staticmethod
    def register_callbacks(id):
        logger.debug(f"Registering callbacks for PueueLog {id}")
        PueueLog.__registered_callbacks.add(id)

        callback(
            Output(f"{id}_queue", "disabled"),
            Input(f"{id}_queue", "n_clicks"),
            State(id, "value"),
        )(PueueLog.__pueue_queue_again_callback)

        callback(
            Output(f"{id}_kill", "disabled"),
            Input(f"{id}_kill", "n_clicks"),
            State(id, "value"),
        )(PueueLog.__pueue_kill_callback)

        callback(
            output=[
                Output(f"{id}_title", "children"),
                Output(f"{id}_log", "children"),
                Output(f"{id}_container", "className"),
            ],
            inputs=[
                Input(id, "value"),
                Input(f"{id}_live", "on"),
                Input(f"{id}_full", "on"),
            ],
            background=True,
            progress=[
                Output(f"{id}_title", "children"),
                Output(f"{id}_log", "children"),
            ],
            running=[(Output(f"{id}_container", "className"), "progressing", "hidden")],
            cancel=[Input(f"{id}_live", "on")],
            interval=1000,  # Time between each call to the function
        )(PueueLog.__pueue_status_callback)

    @staticmethod
    def __pueue_queue_again_callback(_, task_id: str):
        if ctx.triggered_id is None:
            return no_update
        status = exec.status(task_id)
        command = status["command"]
        group = status["group"]

        logger.info(f"Queuing task {task_id} again {group} : {command}.")
        exec.queue(command, group)
        return True

    @staticmethod
    def __pueue_kill_callback(_, task_id: str):
        if ctx.triggered_id is None:
            return no_update
        logger.info(f"Killing task {task_id}.")
        exec.execute(f"./pueue kill {task_id}")
        return True

    @staticmethod
    def __pueue_status(task_id: str, full: bool = False):
        status = exec.status(task_id, full=full)

        status["ui"] = [
            html.Div(
                [
                    html.Div([html.P("Status"), html.Span(status["status"], className=f"tag {status['status'].lower()}")]),
                    html.Div([html.P("Created at"), html.Span(status["created_at"])]),
                    html.Div([html.P("Started at"), html.Span(status["started_at"])]),
                    html.Div([html.P("Ended at"), html.Span(status["ended_at"])]),
                ],
                className="columns",
            ),
            html.A("Open in a new tab", href=f"http://192.168.0.93:8007/log/{task_id}", target="_blank"),
            dcc.Markdown(
                f"""
                The command below is queued for execution. You can follow the execution progress in the log below.

                ```bash
                {status["command"]}
                ```

                The logging output of this task:
            """
            ),
            dcc.Markdown(f"```csharp\n{status['log']}"),
        ]
        return status

    @staticmethod
    def __pueue_status_callback(set_progress, task_id: str, is_live: bool, full: bool):
        if task_id is None or task_id == "" or is_live is None or full is None:
            return no_update

        if not is_live:
            status_ = PueueLog.__pueue_status(task_id, full=full)
        else:
            while True:
                status_ = PueueLog.__pueue_status(task_id, full=full)
                if status_["status"] in {"Finished", "Failed", "Killed", "Success"}:
                    break
                set_progress((f"Task {status_['id']} @ {status_['group']}...", status_["ui"]))
                time.sleep(5)

        return f"Task {status_['id']} @{ status_['group']}", status_["ui"], ""


class TagList:
    def __new__(_, id: str, tags: List[str] = None, options: List[str] = None, style=None, **kwargs):
        if tags is None:
            tags = []
        if options is None:
            options = []

        options = [t for t in tags if t not in options] + options
        options = [{"label": t, "value": t} for t in options]

        return html.Div(
            [
                dcc.Dropdown(id={"module": "taglist", "id": id}, options=options, value=tags, multi=True),
                dcc.Input(id={"module": "taglist", "attr": "input", "id": id}, type="text", placeholder="Add a new tag", debounce=True),
            ],
            className="columns gapless",
            style=style,
            id={"module": "taglist", "attr": "container", "id": id},
            **kwargs,
        )


@callback(
    Output({"module": "taglist", "id": MATCH}, "options"),
    Output({"module": "taglist", "id": MATCH}, "value"),
    Input({"module": "taglist", "attr": "input", "id": MATCH}, "value"),
    State({"module": "taglist", "id": MATCH}, "options"),
    State({"module": "taglist", "id": MATCH}, "value"),
)
def taglist_add_tag(value: str, tags: List[Dict[str, str]], value_: List[str]):
    if ctx.triggered_id is None or value is None or value == "":
        return no_update
    if value in [t["value"] for t in tags]:
        return no_update
    if value_ is None:
        value_ = []
    return tags + [{"label": value, "value": value}], value_ + [value]


class PathSelector:
    def __new__(_, id_: str, root_folder: Path, only_folders: bool = False, show_hidden: bool = False):
        # mode contains only_folders and show_hidden
        mode = ("D" if only_folders else "F") + ("H" if show_hidden else "V")
        return html.Div(
            [
                dcc.Input(id={"module": "pathselector", "id": f"{id_}"}, style={"margin-bottom": "0"}),
                html.A("Pick folder", className="button", id={"module": "pathselector", "id": f"{id_}", "attr": "open-button"}),
                html.Div(
                    [
                        html.Div(mode, id={"module": "pathselector", "id": f"{id_}", "attr": "mode"}, style={"display": "none"}),
                        html.Ul(id={"module": "pathselector", "id": f"{id_}", "attr": "list"}),
                        html.Div(
                            [
                                html.Div(
                                    str(root_folder),
                                    id={"module": "pathselector", "id": f"{id_}", "attr": "current_folder"},
                                    className="breadcrumb",
                                ),
                                html.A("Select", className="button", id={"module": "pathselector", "id": f"{id_}", "attr": "close-button"}),
                            ],
                            style={"padding": "0 1rem", "margin-top": "1em"},
                        ),
                    ],
                    className="pathselector-modal",
                    hidden=True,
                    id={"module": "pathselector", "id": f"{id_}", "attr": "modal"},
                ),
            ]
        )


@callback(
    Output({"module": "pathselector", "id": MATCH, "attr": "modal"}, "hidden"),
    Output({"module": "pathselector", "id": MATCH}, "value"),
    Input({"module": "pathselector", "id": MATCH, "attr": "open-button"}, "n_clicks"),
    Input({"module": "pathselector", "id": MATCH, "attr": "close-button"}, "n_clicks"),
    State({"module": "pathselector", "id": MATCH, "attr": "current_folder"}, "children"),
)
def __pathselector_open_close_callback(_, __, current_folder):
    if ctx.triggered_id:
        if ctx.triggered_id["attr"] == "open-button":
            return False, no_update
        else:
            return True, current_folder
    return no_update, no_update


@callback(
    Output({"module": "pathselector", "id": MATCH, "attr": "current_folder"}, "children"),
    Output({"module": "pathselector", "id": MATCH, "attr": "list"}, "children"),
    Input({"module": "pathselector", "id": MATCH, "goto": ALL}, "n_clicks"),
    State({"module": "pathselector", "id": MATCH, "attr": "current_folder"}, "children"),
    State({"module": "pathselector", "id": MATCH, "attr": "mode"}, "children"),
)
def __pathselector_click_callback(_, current_folder, mode):
    only_folders = mode[0] == "D"
    show_hidden = mode[1] == "H"
    current_folder = Path(current_folder)

    if ctx.triggered_id:
        clicked_elem = ctx.triggered_id["goto"]

        if clicked_elem == "..":
            target = current_folder.parent
        else:
            target = current_folder / clicked_elem
    else:
        target = current_folder

    if target.is_dir():
        id_ = ctx.args_grouping[-1]["id"]["id"]

        list_elements = [html.Li("📁 ..", id={"module": "pathselector", "id": id_, "goto": ".."})]
        folders = sorted([f for f in target.iterdir() if f.is_dir()], key=lambda f: f.name)
        list_elements.extend(
            [
                html.Li(f"📁 {path.name}", id={"module": "pathselector", "id": id_, "goto": path.name})
                for path in folders
                if show_hidden or not path.stem.startswith(".")
            ]
        )
        files = sorted([f for f in target.iterdir() if f.is_file()], key=lambda f: f.name)
        if only_folders:
            list_elements.extend(
                [html.Li(f"📄 {path.name}", className="static") for path in files if show_hidden or not path.stem.startswith(".")]
            )
        else:
            list_elements.extend(
                [
                    html.Li(f"📄 {path.name}", id={"module": "pathselector", "id": id_, "goto": path.name})
                    for path in files
                    if show_hidden or not path.stem.startswith(".")
                ]
            )

        return str(target), list_elements

    return str(target), no_update


class PlotDownloadButton:
    def __new__(_, id: str, button_text: str = "Download plot", filename: str = "export.pdf", width: int = None, height: int = None):
        if isinstance(id, dict):
            graph_id = graph_id["name"]
            assert id["type"] == "plot"
        else:
            graph_id = id

        return html.A(
            [
                html.Img(src=get_asset_url("icon-file-type-pdf.svg")),
                button_text,
                dcc.Download(id={"module": "plotdownloadbutton", "id": graph_id, "attr": "download"}),
                dcc.Store(
                    id={"module": "plotdownloadbutton", "id": graph_id, "attr": "config"},
                    data={
                        "filename": filename,
                        "width": width,
                        "height": height,
                    },
                ),
            ],
            id={"module": "plotdownloadbutton", "id": graph_id},
            className="button icon",
            n_clicks=0,
            target="_blank",
        )


@callback(
    Output({"module": "plotdownloadbutton", "id": MATCH, "attr": "download"}, "data"),
    Input({"module": "plotdownloadbutton", "id": MATCH}, "n_clicks"),
    State({"type": "graph", "id": MATCH}, "figure"),
    State({"module": "plotdownloadbutton", "id": MATCH, "attr": "config"}, "data"),
    State({"module": "plotdownloadbutton", "id": MATCH}, "id"),
    prevent_initial_call=True,
)
def __plotdownloadbutton_callback(_, fig, config, id_):
    default_width, default_height = 700, 500
    width = config["width"] if "width" in config and config["width"] is not None else fig.get("layout", {}).get("width", default_width)
    height = (
        config["height"] if "height" in config and config["height"] is not None else fig.get("layout", {}).get("height", default_height)
    )

    # this is a bug-fix, otherwise there is watermark with mathjax on the pdf
    # ref: https://github.com/plotly/plotly.py/issues/3469#issuecomment-1081736804
    fig = pio.full_figure_for_development(fig, warn=False)
    time.sleep(2)

    # In-memory File
    temp_file = io.BytesIO()
    # Write PDF to in-memory file
    fig.write_image(temp_file, format="pdf", width=width, height=height, engine="kaleido")
    # Reset file pointer to start
    temp_file.seek(0)
    # Encode file to base64 (string)
    b64_data = base64.b64encode(temp_file.read()).decode()

    if "filename" in config and config["filename"] is not None:
        filename = config["filename"]
    else:
        filename = f"export_{id_['id']}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"

    # Download the binary data but tell the browser it's a PDF
    return dict(
        content=b64_data,
        filename=filename,
        type="application/pdf",
        base64=True,
    )
