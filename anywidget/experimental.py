from __future__ import annotations

import contextlib
import dataclasses
import pathlib
import typing

import psygnal

from ._descriptor import MimeBundleDescriptor

if typing.TYPE_CHECKING:  # pragma: no cover
    from ._protocols import WidgetBase

__all__ = ["dataclass", "widget", "MimeBundleDescriptor"]

_T = typing.TypeVar("_T")
T = typing.TypeVar("T")


def widget(
    *,
    esm: str | pathlib.Path,
    css: None | str | pathlib.Path = None,
    **kwargs: typing.Any,
) -> typing.Callable[[T], T]:
    """Decorator to register a widget class as a mimebundle.

    Parameters
    ----------
    esm : str | pathlib.Path
        The path or contents of an ES Module for the widget.
    css : None | str | pathlib.Path, optional
        The path or contents of a CSS file for the widget.
    **kwargs
        Additional keyword arguments to pass to the

    Returns
    -------
    Callable
        A decorator that registers the widget class as a mimebundle.
    """
    kwargs["_esm"] = esm
    if css is not None:
        kwargs["_css"] = css

    def _decorator(cls: _T) -> _T:
        setattr(cls, "_repr_mimebundle_", MimeBundleDescriptor(**kwargs))
        return cls

    return _decorator


# To preserve the signature of the decorated class.
# see: https://github.com/pyapp-kit/magicgui/blob/5e068f31eaeeb130f43c38727b25423cc3ea4de3/src/magicgui/schema/_guiclass.py#L145-L162
def __dataclass_transform__(
    *,
    eq_default: bool = True,
    order_default: bool = False,
    kw_only_default: bool = False,
    field_specifiers: tuple[type | typing.Callable[..., typing.Any], ...] = (()),
) -> typing.Callable[[_T], _T]:
    return lambda a: a


@__dataclass_transform__(field_specifiers=(dataclasses.Field, dataclasses.field))
def dataclass(
    cls: T | None = None,
    *,
    esm: str | pathlib.Path,
    css: None | str | pathlib.Path = None,
    **dataclass_kwargs: typing.Any,
) -> typing.Callable[[T], T]:
    """Turns class into a dataclass, makes it evented, and registers it as a widget.

    Parameters
    ----------
    cls : T | None
        The class to decorate.
    esm : str | pathlib.Path
        The path or contents of an ES Module for the widget.
    css : None | str | pathlib.Path, optional
        The path or contents of a CSS file for the widget.
    dataclass_kwargs : typing.Any
        Additional keyword arguments to pass to the dataclass decorator.

    Returns
    -------
    type
        The evented dataclass.

    Examples
    --------
    >>> @dataclass(esm="index.js")
    ... class Counter:
    ...     value: int = 0
    ...
    >>> counter = Counter()
    >>> counter.value = 1
    >>> counter
    """

    def _decorator(cls: T) -> T:
        cls = dataclasses.dataclass(cls, **dataclass_kwargs)  # type: ignore
        cls = psygnal.evented(cls)  # type: ignore
        cls = widget(esm=esm, css=css)(cls)
        return cls

    return _decorator(cls) if cls is not None else _decorator  # type: ignore


_ANYWIDGET_COMMAND = "_anywidget_command"

_AnyWidgetCommand = typing.Callable[
    [typing.Any, typing.Any, typing.List[bytes]],
    typing.Tuple[typing.Any, typing.List[bytes]],
]


def command(cmd: _AnyWidgetCommand) -> _AnyWidgetCommand:
    """Mark a function as a command for anywidget."""
    setattr(cmd, _ANYWIDGET_COMMAND, True)
    return cmd


_AnyWidgetCommandBound = typing.Callable[
    [typing.Any, typing.List[bytes]], typing.Tuple[typing.Any, typing.List[bytes]]
]


def _collect_commands(widget: WidgetBase) -> dict[str, _AnyWidgetCommandBound]:
    cmds: dict[str, _AnyWidgetCommandBound] = {}
    for attr_name in dir(widget):
        # suppressing silly assertion erro from ipywidgets _staticproperty
        # ref: https://github.com/jupyter-widgets/ipywidgets/blob/b78de43e12ff26e4aa16e6e4c6844a7c82a8ee1c/python/ipywidgets/ipywidgets/widgets/widget.py#L291-L297
        with contextlib.suppress(AssertionError):
            attr = getattr(widget, attr_name)
            if callable(attr) and getattr(attr, _ANYWIDGET_COMMAND, False):
                cmds[attr_name] = attr
    return cmds


def _register_anywidget_commands(
    widget: WidgetBase,
) -> None:
    """Register a custom message reducer for a widget if it implements the protocol."""
    # Only add the callback if the widget has any commands.
    cmds = _collect_commands(widget)
    if len(cmds) == 0:
        return None

    def handle_anywidget_command(
        self: WidgetBase, msg: str | list | dict, buffers: list[bytes]
    ) -> None:
        if not isinstance(msg, dict) or msg.get("kind") != "anywidget-command":
            return
        cmd = cmds[msg["name"]]
        response, buffers = cmd(msg["msg"], buffers)
        self.send(
            {
                "id": msg["id"],
                "kind": "anywidget-command-response",
                "response": response,
            },
            buffers,
        )

    widget.on_msg(handle_anywidget_command)
