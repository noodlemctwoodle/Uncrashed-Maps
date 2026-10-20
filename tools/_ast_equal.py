"""Check that two Python files have identical behaviour-relevant ASTs (docstrings and comments ignored).
usage: python3 tools/_ast_equal.py old.py new.py"""

import ast, sys


def strip(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(getattr(first, 'value', None), ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree, include_attributes=False)


a, b = (strip(ast.parse(open(p).read())) for p in sys.argv[1:3])
print('SAME' if a == b else 'DIFFERENT')
sys.exit(0 if a == b else 1)
