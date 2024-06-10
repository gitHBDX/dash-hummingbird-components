import base64
import datetime
import json
import logging
import os
import string
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple, Union

import paramiko
import yaml

ENV = {
    "KNOWN_HOSTS": "~/.ssh/known_hosts",
    "PUBKEY": "~/.ssh/id_ed25519.pub",
    "JUPYTER_TEMPLATE_FOLDER": "~/notebooks/templates",
    "JUPYTER_NOTEBOOK_FOLDER": "~/notebooks",
    "JUPYTER_USER": "task_runner",
    "JUPYTER_HOST": "192.168.0.94",
    "JUPYTER_PORT": "10123",
    "JUPYTER_KERNEL_NAME": "python3",
    "WORKER_HOST": "192.168.0.94",
    "WORKER_USER": "task_runner",
}

for key, value in ENV.items():
    if f"DHC_{key}" in os.environ:
        ENV[key] = os.environ[f"DHC_{key}"]

logger = logging.getLogger(__name__)
if Path(ENV["KNOWN_HOSTS"]).expanduser().is_file():
    SSH = paramiko.SSHClient()
    SSH.load_host_keys(str(Path(ENV["KNOWN_HOSTS"]).expanduser()))


CMDType = Union[str, List[str], Tuple[str, Dict[str, Any]]]


def shell_escape(value: Any) -> str:
    """Escapes a string for use in a shell command

    Parameters
    ----------
    value : Any
        A string to be escaped, or any object that can be converted to a string

    Returns
    -------
    str
        The escaped string
    """
    return "'" + str(value).replace(r"'", r"\''") + "'"


def resolve_cmd(cmd: CMDType) -> str:
    """Resolves a command to a string

    Parameters
    ----------
    cmd : CMDType
        A command to be executed. Can be a string, a list of strings, or a tuple

    Returns
    -------
    str
        The command as a string
    """
    if isinstance(cmd, str):
        return cmd
    elif isinstance(cmd, list):
        return " ".join(cmd)
    elif isinstance(cmd, tuple):
        assert len(cmd) == 2
        cmdStr = [cmd[0]]
        for k, v in cmd[1].items():
            if isinstance(v, bool):
                if v:
                    cmdStr.append(f"--{k}")
            elif v is not None:
                cmdStr.append(f"--{k}={shell_escape(v)}")
        return " ".join(cmdStr)
    else:
        raise TypeError(f"Command must be of type str, list or dict, not {type(cmd)}")


def cp(file: Path, dest: str, user: str = None, host: str = None) -> None:
    """Copies a file to a remote host

    Parameters
    ----------
    file : Path
        The file to be copied
    dest : str
        The destination path on the remote host (including the filename)
    user : str, optional
        The username to use for the remote host, by default ws4 from the settings
    host : str, optional
        The hostname of the remote host, by default ws4 from the settings
    """
    assert file.is_file()
    host = host or ENV["WORKER_HOST"]
    user = user or ENV["WORKER_USER"]
    SSH.connect(
        host,
        username=user,
        key_filename=str(Path(ENV["PUBKEY"]).expanduser()),
    )
    sftp = SSH.open_sftp()
    try:
        sftp.stat("/tmp/classifynder_conf")
    except:
        sftp.mkdir("/tmp/classifynder_conf")
    sftp.put(file, dest)
    sftp.close()
    SSH.close()


def execute(cmd: CMDType, user: str = None, host: str = None, progress: Callable = False, local: bool = False) -> str:
    """Executes a command on a remote host

    Parameters
    ----------
    cmd : CMDType
        The command to be executed, either as a string, a list of strings, or a tuple
    user : str, optional
        The username to use for the remote host, by default ws4 from the settings
    host : str, optional
        The hostname of the remote host, by default ws4 from the settings
    progress : Callable, optional
        A function to be called with the stdout of the command as it is executed, by default False
    local : bool, optional
        Whether to execute the command locally, by default False
    """
    if local:
        logger.info(f"Executing {cmd} on local machine")
        stdout = ""
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True) as process:
            for line in process.stdout:
                stdout += line.decode("utf8")
                if progress:
                    progress(stdout)
        return stdout
    else:
        host = host or ENV["WORKER_HOST"]
        user = user or ENV["WORKER_USER"]
        if len(cmd) > 4000:
            logger.info(f'Executing long command {cmd[:500]}" on {user}@{host}')
        else:
            logger.info(f"Executing {cmd} on {user}@{host}")
        SSH.connect(
            host,
            username=user,
            key_filename=str(Path(ENV["PUBKEY"]).expanduser()),
        )
        cmd = resolve_cmd(cmd)
        _, stdout, _ = SSH.exec_command(cmd)
        stdout = stdout.read().decode("utf-8")
        SSH.close()
        return stdout


def queue(cmd: CMDType, task: str, user: str = None, host: str = None) -> int:
    """Queues a command on a remote host using pueue

    Parameters
    ----------
    cmd : CMDType
        The command to be executed, either as a string, a list of strings, or a tuple
    task : str
        The task group to queue the command under
    user : str, optional
        The username to use for the remote host, by default ws4 from the settings
    host : str, optional
        The hostname of the remote host, by default ws4 from the settings
    """
    available_tasks = {"train", "inference", "create"}
    if task not in available_tasks:
        raise ValueError(f"Task must be one of {available_tasks}")

    cmd = resolve_cmd(cmd)
    stdout = execute(f"./pueue add -g {task} -- {cmd}", user, host)
    if "New task added" in stdout:
        return int("".join(list(filter(lambda x: x in string.digits, stdout))))
    else:
        raise RuntimeError("Couldn't queue the task")


def simplify_pueue_status(status: Union[Dict[str, Any], str]) -> str:
    if isinstance(status, str):
        return status
    elif isinstance(status, dict):
        if "Done" in status:
            # For {'Done': {'Failed': 127}} case
            if isinstance(status["Done"], dict):
                return next(iter(status["Done"].keys()))
            # For {'Done': 'Success'} case
            else:
                return status["Done"]
        else:
            return next(iter(status.keys()))
    else:
        raise TypeError(f"status must be of type str or dict, not {type(status)}")


time_parser = lambda x: datetime.datetime.fromisoformat(x.split("+")[0][:10]) if x else None


def status(task_id: int, full: bool = False, user: str = None, host: str = None) -> Dict[str, str]:
    """Returns the status of a task.

    Parameters
    ----------
    task_id : int
        The id of the task
    full : bool, optional
        Whether to return the full log, by default False
    user : str, optional
        The username to use for the remote host, by default ws4 from the settings
    host : str, optional
        The hostname of the remote host, by default ws4 from the settings

    Returns
    -------
    Dict[str, str]
        A dictionary with the status of the task. Contains, id, command, group, status, started_at, ended_at, created_at, log.
    """
    task_id = str(task_id)
    flags = " -f" if full else " -l 100"
    logj = execute(f"./pueue log -j {task_id} {flags}", user, host)
    logj = json.loads(logj)[task_id]

    status_ = {
        "id": logj["task"]["id"],
        "command": logj["task"]["command"],
        "group": logj["task"]["group"],
        "status": simplify_pueue_status(logj["task"]["status"]),
        "started_at": time_parser(logj["task"]["start"]),
        "ended_at": time_parser(logj["task"]["end"]),
        "created_at": time_parser(logj["task"]["created_at"]),
        "log": logj["output"],
    }
    return status_


def start_notebook(name: str, parameters: Dict[str, Any] = None) -> str:
    """Starts a notebook on the remote jupyter server.

    Parameters
    ----------
    name : str
        The name of the notebook template to start, without the .ipynb extension.
    parameters : Dict[str, Any], optional
        A dictionary of parameters to pass to the notebook, by default None

    Returns
    -------
    str
        The url of the notebook
    """
    if parameters is None:
        parameters = {}

    name = name.replace(".ipynb", "").replace("template_", "")
    template = f"{ENV['JUPYTER_TEMPLATE_FOLDER']}/template_{name}.ipynb"
    notebook_name = f"{name}_{datetime.datetime.now():%Y-%m-%d_%H-%M-%S-%f}.ipynb"
    notebook = f"{ENV['JUPYTER_NOTEBOOK_FOLDER']}/generated/{notebook_name}"
    parameters_encoded = base64.b64encode(yaml.dump(parameters).encode("utf-8")).decode("utf-8")

    logger.info(f"Starting Notebook {template} with {parameters}")
    stdout = execute(
        f"/home/task_runner/miniforge3/envs/hbdx/bin/papermill --prepare-only {template} {notebook} -b {parameters_encoded}",
        user=ENV["JUPYTER_USER"],
        host=ENV["JUPYTER_HOST"],
    )
    return (
        f"http://{ENV['JUPYTER_HOST']}:{ENV['JUPYTER_PORT']}/notebooks/generated/{notebook_name}?kernel_name={ENV['JUPYTER_KERNEL_NAME']}"
    )
