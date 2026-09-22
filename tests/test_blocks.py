"""Block delimitation -- the pure part of `vi{`.

A pure function, testable without a window, and not by chance the only piece
of visual mode that worked the first time.
"""

import unittest

from serifa.blocks import block_bounds, quote_bounds, target


class TestTarget(unittest.TestCase):
    def check(self, text, mark, sign, inside, expected):
        position = text.index(mark) if isinstance(mark, str) else mark
        span = target(text, position, sign, inside)
        got = text[span[0]:span[1]] if span else None
        label = f"{'i' if inside else 'a'}{sign} em {text!r}"
        self.assertEqual(got, expected, label)

    def test_braces_inside(self):
        self.check(r"\textbf{palavra aqui} depois", "palavra", "{", True,
                   "palavra aqui")

    def test_braces_around(self):
        self.check(r"\textbf{palavra aqui} depois", "palavra", "{", False,
                   "{palavra aqui}")

    def test_nesting_picks_the_inner_one(self):
        self.check(r"{a {b} c}", "b", "{", True, "b")

    def test_nesting_picks_the_outer_one(self):
        self.check(r"{a {b} c}", "a", "{", True, "a {b} c")

    def test_cursor_on_the_opener(self):
        self.check(r"{a {b} c}", 0, "{", True, "a {b} c")

    def test_latex_escaped_brace_is_ignored(self):
        # \{ is a literal brace; matching it would give the wrong block in any
        # \newcommand -- that was the case that prompted the escape check.
        self.check(r"\newcommand{\x}[2]{\{literal\} real}", "real", "{", True,
                   r"\{literal\} real")

    def test_escaped_braces_alone_make_no_block(self):
        self.check(r"\{so escapadas\}", "so", "{", True, None)

    def test_parentheses(self):
        self.check(r"f(x, g(y)) fim", "y", "(", True, "y")

    def test_lowercase_b_means_parenthesis(self):
        self.check(r"f(x, g(y)) fim", "x", "b", True, "x, g(y)")

    def test_brackets(self):
        self.check(r"arr[i+1] fim", "i+1", "[", True, "i+1")

    def test_quotes_inside(self):
        self.check(r'diz "uma coisa" e para', "uma", '"', True, "uma coisa")

    def test_quotes_around(self):
        self.check(r'diz "uma coisa" e para', "uma", '"', False, '"uma coisa"')

    def test_no_block_returns_nothing(self):
        self.check(r"sem nada aqui", "nada", "{", True, None)

    def test_unknown_sign(self):
        self.assertIsNone(target("texto qualquer", 3, "@", True))

    def test_empty_text(self):
        self.assertIsNone(block_bounds("", 0, "{", "}"))

    def test_quotes_do_not_cross_lines(self):
        # Quotes do not nest: parity is counted per line, or a stray quote on
        # one line would match another three paragraphs below.
        self.assertIsNone(quote_bounds('diz "aberta\noutra linha"', 5, '"'))


if __name__ == "__main__":
    unittest.main()
