"""The `gui` marker, enforced rather than remembered.

`pytest -m "not gui"` is the fast lane for work in `core/` and `audio/` (08,
*Checks*), and the fixtures that tidy up after Qt run only for tests that
carry the mark. Both are exactly as trustworthy as the marking, which was
done by hand - and the first run of this module found a test that built a
`QApplication` and showed a widget without it.

So every test that reaches Qt is marked `gui`, on its module or on itself.
*Reaches* is read off the source. A package module reaches Qt if importing it
imports PySide6, directly or through another package module; an import
inside a function is not followed, because it runs only when called - which
is how `theme.py` stays usable headless (D-81). A test reaches Qt if it, or
a helper, class or fixture it uses, names something imported from such a
module or imports one itself. Annotations are not uses: with postponed
evaluation they never run.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import cache
from pathlib import Path

import immersive

PACKAGE_ROOT = Path(immersive.__file__).parent
TESTS = Path(__file__).parent

Scope = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
Imports = ast.Import | ast.ImportFrom


def is_qt(module: str) -> bool:
    return module == "PySide6" or module.startswith("PySide6.")


def parents(module: str) -> list[str]:
    """The packages whose `__init__` runs before `module` does."""
    parts = module.split(".")
    return [".".join(parts[:n]) for n in range(1, len(parts))]


def is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def imports_that_run(node: ast.AST) -> Iterator[Imports]:
    """Import statements that run when `node` runs - not those inside a
    function or lambda it defines, nor under `if TYPE_CHECKING`."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(child, ast.If) and is_type_checking(child.test):
            for branch in child.orelse:
                yield from imports_that_run(ast.Module(body=[branch], type_ignores=[]))
            continue
        if isinstance(child, Imports):
            yield child
        else:
            yield from imports_that_run(child)


def loaded(node: Imports, known: set[str] | frozenset[str]) -> list[str]:
    """The modules one import statement loads, packages included."""
    if isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    elif node.level or not node.module:
        return []
    else:
        names = [node.module] + [
            f"{node.module}.{alias.name}"
            for alias in node.names
            if f"{node.module}.{alias.name}" in known
        ]
    return [every for name in names for every in (*parents(name), name)]


def module_name(path: Path) -> str:
    parts = path.relative_to(PACKAGE_ROOT.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


@cache
def package_sources() -> dict[str, ast.Module]:
    return {
        module_name(path): ast.parse(path.read_text(encoding="utf-8"))
        for path in PACKAGE_ROOT.rglob("*.py")
    }


@cache
def qt_modules() -> frozenset[str]:
    """Every package module that imports PySide6 when it is imported."""
    return qt_among(package_sources())


def qt_among(trees: dict[str, ast.Module]) -> frozenset[str]:
    known = frozenset(trees)
    loads = {
        name: set(parents(name))
        | {m for node in imports_that_run(tree) for m in loaded(node, known)}
        for name, tree in trees.items()
    }
    found = {name for name, modules in loads.items() if any(map(is_qt, modules))}
    while grown := {
        name for name, modules in loads.items() if name not in found and modules & found
    }:
        found |= grown
    return frozenset(found)


def reaches_qt(module: str) -> bool:
    return is_qt(module) or module in qt_modules()


def is_gui_mark(node: ast.expr) -> bool:
    """`pytest.mark.gui`, called or not."""
    if isinstance(node, ast.Call):
        node = node.func
    return ast.unparse(node) == "pytest.mark.gui"


def module_is_marked(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        ):
            value = node.value
            marks = value.elts if isinstance(value, ast.List | ast.Tuple) else [value]
            return any(is_gui_mark(mark) for mark in marks)
    return False


def is_fixture(node: Scope) -> bool:
    return any(
        ast.unparse(d.func if isinstance(d, ast.Call) else d) == "pytest.fixture"
        for d in node.decorator_list
    )


def is_autouse(node: Scope) -> bool:
    return any(
        isinstance(d, ast.Call)
        and any(
            k.arg == "autouse" and ast.unparse(k.value) == "True" for k in d.keywords
        )
        for d in node.decorator_list
    )


def scan(node: ast.AST) -> tuple[set[str], list[Imports]]:
    """The names `node` looks up and the imports it makes, anywhere inside
    it. Annotations are skipped. One walk, since this is most of the rule's
    cost."""
    names: set[str] = set()
    imports: list[Imports] = []
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Name):
            names.add(current.id)
        elif isinstance(current, Imports):
            imports.append(current)
        for field, value in ast.iter_fields(current):
            if field in ("annotation", "returns"):
                continue
            if isinstance(value, list):
                stack.extend(child for child in value if isinstance(child, ast.AST))
            elif isinstance(value, ast.AST):
                stack.append(value)
    return names, imports


def parameters(node: Scope) -> list[str]:
    if isinstance(node, ast.ClassDef):
        return []
    args = node.args
    return [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]


def reaching(tree: ast.Module, fixtures_elsewhere: set[str]) -> set[str]:
    """The module-level functions and classes in `tree` that reach Qt.

    `fixtures_elsewhere` names fixtures from `conftest.py` that do, which a
    test or fixture here reaches by asking for one by name. A fixture of this
    module that is autouse is used by every test in it, asked for or not.
    """
    qt_names: set[str] = set()
    for statement in imports_that_run(tree):
        for alias in statement.names:
            if isinstance(statement, ast.Import):
                modules = [alias.name]
            elif statement.module and not statement.level:
                modules = [statement.module, f"{statement.module}.{alias.name}"]
            else:
                modules = []
            if any(reaches_qt(m) for m in modules):
                qt_names.add(alias.asname or alias.name.split(".")[0])

    scopes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    fixtures = {name for name, node in scopes.items() if is_fixture(node)}
    autouse = {name for name in fixtures if is_autouse(scopes[name])}

    known = frozenset(package_sources())
    found: set[str] = set()
    uses: dict[str, set[str]] = {}
    for name, node in scopes.items():
        names, imports = scan(node)
        imported = [m for i in imports for m in loaded(i, known)]
        if names & qt_names or any(map(reaches_qt, imported)):
            found.add(name)
        if name.startswith("test") or name in fixtures:
            asked = set(parameters(node))
            if asked & (fixtures_elsewhere - fixtures):
                found.add(name)
            names |= asked & fixtures
        if name.startswith("test"):
            names |= autouse
        uses[name] = (names & scopes.keys()) - {name}

    while grown := {n for n, used in uses.items() if n not in found and used & found}:
        found |= grown
    return found


def unmarked_tests_that_reach_qt(
    source: str, fixtures_elsewhere: set[str] | None = None
) -> list[str]:
    tree = ast.parse(source)
    if module_is_marked(tree):
        return []
    found = reaching(tree, fixtures_elsewhere or set())
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test")
        and node.name in found
        and not any(is_gui_mark(d) for d in node.decorator_list)
    ]


def conftest_fixtures_that_reach_qt() -> set[str]:
    """Autouse fixtures are left out: they run for every test, marked or not,
    so asking for one by name would change nothing."""
    tree = ast.parse((TESTS / "conftest.py").read_text(encoding="utf-8"))
    requestable = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and is_fixture(node)
        and not is_autouse(node)
    }
    return reaching(tree, set()) & requestable


# --------------------------------------------------------------------------- #
# the rule
# --------------------------------------------------------------------------- #


def test_every_test_that_reaches_qt_is_marked_gui() -> None:
    elsewhere = conftest_fixtures_that_reach_qt()
    offenders = [
        f"{path.name}::{name}"
        for path in sorted(TESTS.glob("test_*.py"))
        for name in unmarked_tests_that_reach_qt(
            path.read_text(encoding="utf-8"), elsewhere
        )
    ]
    assert not offenders, (
        'these reach Qt without the gui mark, so `pytest -m "not gui"` runs them '
        "and the Qt clean-up fixtures skip them - add @pytest.mark.gui:\n"
        + "\n".join(offenders)
    )


# --------------------------------------------------------------------------- #
# the detector, checked - so the rule cannot pass by seeing nothing
# --------------------------------------------------------------------------- #


def test_the_package_modules_that_reach_qt_are_found() -> None:
    qt = qt_modules()

    assert "immersive.ui.widgets.waveform" in qt, "imports PySide6 itself"
    assert "immersive.app" in qt
    assert "immersive.ui.main_window" in qt
    # Headless on purpose (N-5, D-81), and a deferred import does not count.
    for headless in (
        "immersive.core.model",
        "immersive.audio.device",
        "immersive.ui.theme",
    ):
        assert headless not in qt, headless


def test_a_module_reaches_qt_through_another_and_through_its_package() -> None:
    sources = {
        "pkg": "",
        "pkg.widgets": "from PySide6.QtWidgets import QWidget",
        "pkg.window": "from pkg.widgets import QWidget",
        "pkg.app": "from pkg import window",
        "pkg.late": "def build():\n    from pkg import window",
        "pkg.typed": "if TYPE_CHECKING:\n    from pkg import window",
        "pkg.views": "from PySide6 import QtCore",
        "pkg.views.top": "x = 1",
    }
    trees = {name: ast.parse(text) for name, text in sources.items()}

    assert qt_among(trees) == {
        "pkg.widgets",
        "pkg.window",
        "pkg.app",
        "pkg.views",
        "pkg.views.top",
    }


SAMPLE = """
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from immersive.ui import theme
from immersive.ui.main_window import MainWindow


def helper():
    return QWidget()


@pytest.fixture
def window():
    return MainWindow()


def test_names_qt_itself():
    QWidget()

def test_through_a_helper():
    helper()

def test_through_a_fixture(window):
    pass

def test_through_a_local_import():
    from PySide6.QtGui import QImage

def test_through_a_conftest_fixture(qt_thing):
    pass

@pytest.mark.gui
def test_marked(window):
    pass

def test_headless():
    theme.stylesheet()

def test_only_annotates(x: MainWindow = None) -> MainWindow | None:
    return x
"""


def test_the_detector_finds_each_way_of_reaching_qt() -> None:
    found = unmarked_tests_that_reach_qt(SAMPLE, {"qt_thing"})

    assert found == [
        "test_names_qt_itself",
        "test_through_a_helper",
        "test_through_a_fixture",
        "test_through_a_local_import",
        "test_through_a_conftest_fixture",
    ]


def test_an_autouse_fixture_reaches_every_test_in_its_module() -> None:
    source = (
        "import pytest\n"
        "from immersive.app import build_application\n"
        "@pytest.fixture(autouse=True)\n"
        "def _app():\n"
        "    build_application([])\n"
        "def test_one():\n"
        "    pass\n"
        "def test_two():\n"
        "    pass\n"
    )

    assert unmarked_tests_that_reach_qt(source) == ["test_one", "test_two"]
    assert unmarked_tests_that_reach_qt(source.replace("autouse=True", "")) == []


def test_a_module_mark_covers_every_test() -> None:
    marked = SAMPLE.replace(
        "\n\ndef helper", "\npytestmark = pytest.mark.gui\n\ndef helper", 1
    )
    assert marked != SAMPLE

    assert unmarked_tests_that_reach_qt(marked, {"qt_thing"}) == []
