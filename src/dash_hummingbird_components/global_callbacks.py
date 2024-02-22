import urllib.parse
import logging

from dash import Input, Output, callback, no_update

logger = logging.getLogger("dhc")


_url_param_registry = []
_url_inputs_registry = []


def url_parameter(*input_params):
    global _url_param_registry, _url_inputs_registry

    for id_, param in input_params:
        logger.debug(f"Registering URL param {param} for {id_}")
        _url_param_registry.append(param)
        _url_inputs_registry.append(id_)


def make_url_params_callback():
    def update_url(**values):
        if not values or len(values) == 0:
            return no_update
        logger.debug(f"update_url({values}")

        search = []
        for idx, value in values.items():
            if value is None or value == "":
                continue
            idx = int(idx.replace("param", ""))
            # encode value for url using urllib.parse.quote_plus
            # https://docs.python.org/3/library/urllib.parse.html#urllib.parse.quote_plus
            #if value not an str then convert to str
            if not isinstance(value, str):
                value = str(value)

            value = urllib.parse.quote_plus(value)

            search.append(f"{_url_param_registry[idx]}={value}")
        return "?" + "&".join(search)

    inputs = {f"param{i}": Input(id_, "value") for i, id_ in enumerate(_url_inputs_registry)}
    logger.debug(f"URL parameter relationships: {inputs}")
    if len(inputs) > 0:
        callback(Output("url-params", "search"), inputs=inputs)(update_url)
