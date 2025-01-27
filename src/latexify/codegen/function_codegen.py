"""Codegen for single function."""

from __future__ import annotations

import ast
from typing import Any, ClassVar

from latexify import analyzers
from latexify import constants
from latexify import math_symbols
from latexify import exceptions


class FunctionCodegen(ast.NodeVisitor):
    """Codegen for single functions.

    This codegen works for Module with single FunctionDef node to generate a single
    LaTeX expression of the given function.
    """

    _math_symbol_converter: math_symbols.MathSymbolConverter
    _use_raw_function_name: bool
    _use_signature: bool

    def __init__(
        self,
        *,
        use_math_symbols: bool = False,
        use_raw_function_name: bool = False,
        use_signature: bool = True,
    ) -> None:
        """Initializer.

        Args:
            use_math_symbols: Whether to convert identifiers with a math symbol surface
                (e.g., "alpha") to the LaTeX symbol (e.g., "\\alpha").
            use_raw_function_name: Whether to keep underscores "_" in the function name,
                or convert it to subscript.
            use_signature: Whether to add the function signature before the expression
                or not.
        """
        self._math_symbol_converter = math_symbols.MathSymbolConverter(
            enabled=use_math_symbols
        )
        self._use_raw_function_name = use_raw_function_name
        self._use_signature = use_signature

    def generic_visit(self, node: ast.AST) -> str:
        raise exceptions.LatexifyNotSupportedError(
            f"Unsupported AST: {type(node).__name__}"
        )

    def visit_Module(self, node: ast.Module) -> str:
        return self.visit(node.body[0])

    def visit_FunctionDef(self, node: ast.FunctionDef) -> str:
        # Function name
        name_str = str(node.name)
        if self._use_raw_function_name:
            name_str = name_str.replace(r"_", r"\_")
        name_str = r"\mathrm{" + name_str + "}"

        # Arguments
        arg_strs = [
            self._math_symbol_converter.convert(str(arg.arg)) for arg in node.args.args
        ]

        body_strs: list[str] = []

        # Assignment statements (if any): x = ...
        for child in node.body[:-1]:
            if not isinstance(child, ast.Assign):
                raise exceptions.LatexifyNotSupportedError(
                    "Codegen supports only Assign nodes in multiline functions, "
                    f"but got: {type(child).__name__}"
                )
            body_strs.append(self.visit(child))

        return_stmt = node.body[-1]

        if not isinstance(return_stmt, (ast.Return, ast.If)):
            raise exceptions.LatexifySyntaxError(
                f"Unsupported last statement: {type(return_stmt).__name__}"
            )

        # Function signature: f(x, ...)
        signature_str = name_str + "(" + ", ".join(arg_strs) + ")"

        # Function definition: f(x, ...) \triangleq ...
        return_str = self.visit(return_stmt)
        if self._use_signature:
            return_str = signature_str + " = " + return_str

        if not body_strs:
            # Only the definition.
            return return_str

        # Definition with several assignments. Wrap all statements with array.
        body_strs.append(return_str)
        return r"\begin{array}{l} " + r" \\ ".join(body_strs) + r" \end{array}"

    def visit_Assign(self, node: ast.Assign) -> str:
        operands: list[str] = [self.visit(t) for t in node.targets]
        operands.append(self.visit(node.value))
        return " = ".join(operands)

    def visit_Return(self, node: ast.Return) -> str:
        return self.visit(node.value)

    def visit_Tuple(self, node: ast.Tuple) -> str:
        elts = [self.visit(i) for i in node.elts]
        return r"\left( " + r"\space,\space ".join(elts) + r"\right) "

    def visit_List(self, node: ast.List) -> str:
        elts = [self.visit(i) for i in node.elts]
        return r"\left[ " + r"\space,\space ".join(elts) + r"\right] "

    def visit_Set(self, node: ast.Set) -> str:
        elts = [self.visit(i) for i in node.elts]
        return r"\left\{ " + r"\space,\space ".join(elts) + r"\right\} "

    def visit_Call(self, node: ast.Call) -> str:
        """Visit a call node."""
        # Function signature (possibly an expression).
        func_str = self.visit(node.func)

        # Removes common prefixes: math.sqrt -> sqrt
        # TODO(odashi): This process can be implemented as a NodeTransformer.
        for prefix in constants.PREFIXES:
            if func_str.startswith(f"{prefix}."):
                func_str = func_str[len(prefix) + 1 :]
                break

        # Obtains wrapper syntax: sqrt -> "\sqrt{" and "}"
        lstr, rstr = constants.BUILTIN_FUNCS.get(
            func_str,
            (r"\mathrm{" + func_str + r"}\left(", r"\right)"),
        )

        if func_str in ("sum", "prod") and isinstance(node.args[0], ast.GeneratorExp):
            elt, scripts = self._get_sum_prod_info(node.args[0])
            scripts_str = [rf"\{func_str}_{{{lo}}}^{{{up}}}" for lo, up in scripts]
            return " ".join(scripts_str) + rf" \left({{{elt}}}\right)"

        arg_strs = [self.visit(arg) for arg in node.args]
        return lstr + ", ".join(arg_strs) + rstr

    def visit_Attribute(self, node: ast.Attribute) -> str:
        vstr = self.visit(node.value)
        astr = str(node.attr)
        return vstr + "." + astr

    def visit_Name(self, node: ast.Name) -> str:
        return self._math_symbol_converter.convert(str(node.id))

    def _convert_constant(self, value: Any) -> str:
        """Helper to convert constant values to LaTeX.

        Args:
            value: A constant value.

        Returns:
            The LaTeX representation of `value`.
        """
        if value is None or isinstance(value, bool):
            return r"\mathrm{" + str(value) + "}"
        if isinstance(value, (int, float, complex)):
            # TODO(odashi): Support other symbols for the imaginary unit than j.
            return "{" + str(value) + "}"
        if isinstance(value, str):
            return r'\textrm{"' + value + '"}'
        if isinstance(value, bytes):
            return r"\textrm{" + str(value) + "}"
        if value is ...:
            return r"{\cdots}"
        raise exceptions.LatexifyNotSupportedError(
            f"Unrecognized constant: {type(value).__name__}"
        )

    # From Python 3.8
    def visit_Constant(self, node: ast.Constant) -> str:
        return self._convert_constant(node.value)

    # Until Python 3.7
    def visit_Num(self, node: ast.Num) -> str:
        return self._convert_constant(node.n)

    # Until Python 3.7
    def visit_Str(self, node: ast.Str) -> str:
        return self._convert_constant(node.s)

    # Until Python 3.7
    def visit_Bytes(self, node: ast.Bytes) -> str:
        return self._convert_constant(node.s)

    # Until Python 3.7
    def visit_NameConstant(self, node: ast.NameConstant) -> str:
        return self._convert_constant(node.value)

    # Until Python 3.7
    def visit_Ellipsis(self, node: ast.Ellipsis) -> str:
        return self._convert_constant(...)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> str:
        """Visit a unary op node."""

        def _wrap(child):
            latex = self.visit(child)
            if isinstance(child, ast.BinOp) and isinstance(
                child.op, (ast.Add, ast.Sub)
            ):
                return r"\left(" + latex + r"\right)"
            return latex

        reprs = {
            ast.UAdd: (lambda: _wrap(node.operand)),
            ast.USub: (lambda: "-" + _wrap(node.operand)),
            ast.Not: (lambda: r"\lnot\left(" + _wrap(node.operand) + r"\right)"),
        }

        if type(node.op) in reprs:
            return reprs[type(node.op)]()
        return r"\mathrm{unknown\_uniop}(" + self.visit(node.operand) + ")"

    def visit_BinOp(self, node: ast.BinOp) -> str:
        """Visit a binary op node."""
        priority = constants.BIN_OP_PRIORITY

        def _unwrap(child):
            return self.visit(child)

        def _wrap(child):
            latex = _unwrap(child)
            if isinstance(child, ast.BinOp):
                cp = priority[type(child.op)] if type(child.op) in priority else 100
                pp = priority[type(node.op)] if type(node.op) in priority else 100
                if cp < pp:
                    return "(" + latex + ")"
            return latex

        lhs = node.left
        rhs = node.right
        reprs = {
            ast.Add: (lambda: _wrap(lhs) + " + " + _wrap(rhs)),
            ast.Sub: (lambda: _wrap(lhs) + " - " + _wrap(rhs)),
            ast.Mult: (lambda: _wrap(lhs) + _wrap(rhs)),
            ast.MatMult: (lambda: _wrap(lhs) + _wrap(rhs)),
            ast.Div: (lambda: r"\frac{" + _unwrap(lhs) + "}{" + _unwrap(rhs) + "}"),
            ast.FloorDiv: (
                lambda: r"\left\lfloor\frac{"
                + _unwrap(lhs)
                + "}{"
                + _unwrap(rhs)
                + r"}\right\rfloor"
            ),
            ast.Mod: (lambda: _wrap(lhs) + r" \bmod " + _wrap(rhs)),
            ast.Pow: (lambda: _wrap(lhs) + "^{" + _unwrap(rhs) + "}"),
        }

        if type(node.op) in reprs:
            return reprs[type(node.op)]()
        return r"\mathrm{unknown\_binop}(" + _unwrap(lhs) + ", " + _unwrap(rhs) + ")"

    _compare_ops: ClassVar[dict[type[ast.cmpop], str]] = {
        ast.Eq: "=",
        ast.Gt: ">",
        ast.GtE: r"\ge",
        ast.In: r"\in",
        ast.Is: r"\equiv",
        ast.IsNot: r"\not\equiv",
        ast.Lt: "<",
        ast.LtE: r"\le",
        ast.NotEq: r"\ne",
        ast.NotIn: r"\notin",
    }

    def visit_Compare(self, node: ast.Compare) -> str:
        """Visit a compare node."""
        lhs = self.visit(node.left)
        ops = [self._compare_ops[type(x)] for x in node.ops]
        rhs = [self.visit(x) for x in node.comparators]
        ops_rhs = [f" {o} {r}" for o, r in zip(ops, rhs)]
        return "{" + lhs + "".join(ops_rhs) + "}"

    _bool_ops: ClassVar[dict[type[ast.boolop], str]] = {
        ast.And: r"\land",
        ast.Or: r"\lor",
    }

    def visit_BoolOp(self, node: ast.BoolOp) -> str:
        """Visit a BoolOp node."""
        values = [rf"\left( {self.visit(x)} \right)" for x in node.values]
        op = f" {self._bool_ops[type(node.op)]} "
        return "{" + op.join(values) + "}"

    def visit_If(self, node: ast.If) -> str:
        """Visit an if node."""
        latex = r"\left\{ \begin{array}{ll} "

        while isinstance(node, ast.If):
            if len(node.body) != 1 or len(node.orelse) != 1:
                raise exceptions.LatexifySyntaxError(
                    "Multiple statements are not supported in If nodes."
                )

            cond_latex = self.visit(node.test)
            true_latex = self.visit(node.body[0])
            latex += true_latex + r", & \mathrm{if} \ " + cond_latex + r" \\ "
            node = node.orelse[0]

        latex += self.visit(node)
        return latex + r", & \mathrm{otherwise} \end{array} \right."

    def _get_sum_prod_range(self, node: ast.comprehension) -> tuple[str, str] | None:
        """Helper to process range(...) for sum and prod functions.

        Args:
            node: comprehension node to be analyzed.

        Returns:
            Tuple of following strings:
                - lower_rhs
                - upper
            which are used in _get_sum_prod_info, or None if the analysis failed.
        """
        if not (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
        ):
            return None

        try:
            range_info = analyzers.analyze_range(node.iter)
        except exceptions.LatexifyError:
            return None

        if (
            # Only accepts ascending order with step size 1.
            range_info.step_int != 1
            or (
                range_info.start_int is not None
                and range_info.stop_int is not None
                and range_info.start_int >= range_info.stop_int
            )
        ):
            return None

        if range_info.start_int is None:
            lower_rhs = self.visit(range_info.start)
        else:
            lower_rhs = f"{{{range_info.start_int}}}"

        if range_info.stop_int is None:
            upper = "{" + self.visit(range_info.stop) + " - 1}"
        else:
            upper = f"{{{range_info.stop_int - 1}}}"

        return lower_rhs, upper

    def _get_sum_prod_info(
        self, node: ast.GeneratorExp
    ) -> tuple[str, list[tuple[str, str]]]:
        r"""Process GeneratorExp for sum and prod functions.

        Args:
            node: GeneratorExp node to be analyzed.

        Returns:
            Tuple of following strings:
                - elt
                - scripts
            which are used to represent sum/prod operators as follows:
                \sum_{scripts[0][0]}^{scripts[0][1]}
                    \sum_{scripts[1][0]}^{scripts[1][1]}
                    ...
                    {elt}

        Raises:
            LateixfyError: Unsupported AST is given.
        """
        elt = self.visit(node.elt)

        scripts: list[tuple[str, str]] = []

        for comp in node.generators:
            target = self.visit(comp.target)
            range_args = self._get_sum_prod_range(comp)

            if range_args is not None and not comp.ifs:
                lower_rhs, upper = range_args
                lower = f"{target} = {lower_rhs}"
            else:
                lower_rhs = self.visit(comp.iter)
                lower_in = rf"{target} \in {lower_rhs}"
                upper = ""

                if comp.ifs:
                    conds = [lower_in] + [self.visit(cond) for cond in comp.ifs]
                    conds_wrapped = [r"\left(" + cond + r"\right)" for cond in conds]
                    lower = r" \land ".join(conds_wrapped)
                    # TODO(odashi):
                    # Following form may be prettier, but requires amsmath.
                    # It would be good if we have an option to switch the behavior.
                    # lower = r"\substack{" + r" \\ ".join(lowers) + "}"
                else:
                    lower = lower_in

            scripts.append((lower, upper))

        return elt, scripts

    # Until 3.8
    def visit_Index(self, node: ast.Index) -> str:
        """Visitor for the Index nodes."""
        return self.visit(node.value)

    def _convert_nested_subscripts(self, node: ast.Subscript) -> tuple[str, list[str]]:
        """Helper function to convert nested subscription.

        This function converts x[i][j][...] to "x" and ["i", "j", ...]

        Args:
            node: ast.Subscript node to be converted.

        Returns:
            Tuple of following strings:
                - The root value of the subscription.
                - Sequence of incices.
        """
        if isinstance(node.value, ast.Subscript):
            value, indices = self._convert_nested_subscripts(node.value)
        else:
            value = self.visit(node.value)
            indices = []

        indices.append(self.visit(node.slice))
        return value, indices

    def visit_Subscript(self, node: ast.Subscript) -> str:
        """Visitor of the Subscript nodes."""
        value, indices = self._convert_nested_subscripts(node)

        # TODO(odashi):
        # "[i][j][...]" may be a possible representation as well as "i, j. ..."
        indices_str = "{" + ", ".join(indices) + "}"

        return f"{{{value}_{indices_str}}}"
