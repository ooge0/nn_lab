import ast
import pandas as pd
import os


class PlotlyAuditParser(ast.NodeVisitor):
    def __init__(self):
        self.results = []
        self.current_tab = "root"
        self.order = 1

        # Mapping Plotly methods to their specific coordinate parameters
        self.param_map = {
            'scatter': ('x', 'y', None),
            'line': ('x', 'y', None),
            'bar': ('x', 'y', None),
            'box': ('x', 'y', None),
            'pie': ('names', 'values', None),
            'scatter_ternary': ('a', 'b', 'c'),
        }

    def visit_With(self, node):
        # Context tracking for Streamlit tabs
        for item in node.items:
            if isinstance(item.context_expr, ast.Name):
                old_tab = self.current_tab
                self.current_tab = item.context_expr.id
                self.generic_visit(node)
                self.current_tab = old_tab
                return
        self.generic_visit(node)

    def visit_Call(self, node):
        # Detect px. calls
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'px':
                method_name = node.func.attr
                keywords = {kw.arg: self._get_val(kw.value) for kw in node.keywords}

                # Identify parameters based on chart type
                mapping = self.param_map.get(method_name, ('x', 'y', None))

                p1 = keywords.get(mapping[0], "")
                p2 = keywords.get(mapping[1], "")
                # If it's ternary, we might need a 3rd param, but we'll stick to the X/Y columns as base
                p3 = keywords.get(mapping[2], "") if mapping[2] else ""

                # Combine p2 and p3 if ternary for the 'Y param' column or keep it clean
                y_display = f"{p2}, {p3}".strip(", ") if p3 else p2

                row = {
                    "order number": self.order,
                    "X param": p1,
                    "Y param": y_display,
                    "Analytics": "",
                    "NLP Science": "",
                    "other": "calculate_advanced_linguistic_metrics , neuro_metrics, nlp_science",
                    "context_tab": self.current_tab  # Extra column for your internal control
                }
                self.results.append(row)
                self.order += 1

        self.generic_visit(node)

    def _get_val(self, node):
        if isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        return "dynamic_expression"


def run_audit(target_filename="streamlit_app.py"):
    # Resolve path relative to THIS file (utils/plotly_parser.py)
    # Moving up one level to reach the project root
    base_path = os.path.dirname(__file__)
    target_path = os.path.join(base_path, "..", target_filename)

    if not os.path.exists(target_path):
        print(f"❌ Error: Target file not found at {os.path.abspath(target_path)}")
        return

    with open(target_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    parser = PlotlyAuditParser()
    parser.visit(tree)

    df = pd.DataFrame(parser.results)

    # Ensure exact 6-column structure for the CSV as requested
    output_columns = ["order number", "X param", "Y param", "Analytics", "NLP Science", "other"]

    # If no charts found, create empty df with headers
    if df.empty:
        df = pd.DataFrame(columns=output_columns)
    else:
        df = df[output_columns]

    output_name = "plotly_methods_audit.csv"
    df.to_csv(output_name, index=False)

    print(f"✅ Audit complete. Found {len(df)} visualization methods.")
    print(f"📊 Results saved to: {output_name}")


if __name__ == "__main__":
    run_audit("streamlit_app.py")