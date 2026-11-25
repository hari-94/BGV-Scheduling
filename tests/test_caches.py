"""Streamlit leaves a cached function's arguments that start with "_" out of
its cache key. That is how a big object is passed without hashing it -- and a
trap for a change token: on 25 Nov My Home, My Rooms' duties, Property's
looks and three Roster Import readers all passed their "has it changed?"
token as `_token` / `_tick` / `_gen` / `_before`, so a change was missed
until the ttl ran out (and Roster Import's daily-service shape ignored which
week it was asked about). A token must be in the key: name it without "_"."""
import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOKENISH = ("token", "tick", "gen", "stamp", "version", "sig", "before", "day", "date", "iso", "key")


def _cached(fn):
    for d in fn.decorator_list:
        target = d.func if isinstance(d, ast.Call) else d
        if isinstance(target, ast.Attribute) and target.attr in ("cache_data", "cache_resource"):
            return True
    return False


class CacheKeys(unittest.TestCase):
    def test_no_change_token_is_left_out_of_a_cache_key(self):
        bad = []
        files = [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "tests" not in p.parts]
        for path in files:
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _cached(node):
                    for a in node.args.args + node.args.kwonlyargs:
                        name = a.arg.lstrip("_")
                        if a.arg.startswith("_") and any(t in name.lower() for t in TOKENISH):
                            bad.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}({a.arg})")
        self.assertEqual(bad, [], "a change token left out of the cache key")


if __name__ == "__main__":
    unittest.main()
