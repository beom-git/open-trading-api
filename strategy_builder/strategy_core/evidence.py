"""Evaluate the existing DSL generated expressions against a history prefix, with evidence."""
import math
from core import indicators, candlestick
from strategy_core.dsl.codegen import StrategyCodeGenerator
from strategy_core.dsl.parser import Condition, CompositeCondition, Indicator, ArithmeticExpr, Operator


class EvidenceEvaluator:
    def __init__(self, definition):
        self.definition = definition
        self.generator = StrategyCodeGenerator()
        self.indicator_nodes = {}
        def collect(node):
            if isinstance(node, Indicator):
                if self.generator._node_to_code(node) == '0':
                    raise ValueError(f'Unsupported indicator: {node}')
                self.indicator_nodes[str(node)] = node
            elif isinstance(node, (Condition, CompositeCondition, ArithmeticExpr)):
                collect(node.left)
                collect(node.right)
        collect(definition.buy_condition)
        collect(definition.sell_condition)

    def value(self, node, df):
        # Only expressions produced from the parsed DSL AST enter evaluation.
        return eval(self.generator._node_to_code(node), {'__builtins__': {}},
                    {'df': df, 'indicators': indicators, 'candlestick': candlestick})

    def evaluate(self, df):
        if len(df) < self.definition.get_required_days():
            return dict(action="INSUFFICIENT_DATA", indicators={}, buy=None, sell=None)
        values = {}
        for label, node in self.indicator_nodes.items():
            value = float(self.value(node, df))
            values[label] = value if math.isfinite(value) else None
        def trace(node):
            if node is None:
                return None
            if isinstance(node, CompositeCondition):
                children = [trace(node.left), trace(node.right)]
                return dict(operator=node.operator.value, children=children, satisfied=bool(self.value(node, df)))
            left, right = float(self.value(node.left, df)), float(self.value(node.right, df))
            previous = None
            if node.operator in (Operator.CROSSES_ABOVE, Operator.CROSSES_BELOW):
                previous = dict(left=float(self.value(node.left, df.iloc[:-1])), right=float(self.value(node.right, df.iloc[:-1])))
            return dict(left_label=str(node.left), left=left, operator=node.operator.value,
                        right_label=str(node.right), right=right, previous=previous,
                        satisfied=bool(self.value(node, df)))
        if len(df) < self.definition.get_required_days() or any(v is None for v in values.values()):
            return dict(action='INSUFFICIENT_DATA', indicators=values, buy=None, sell=None)
        buy, sell = trace(self.definition.buy_condition), trace(self.definition.sell_condition)
        return dict(action='BUY' if buy and buy['satisfied'] else 'SELL' if sell and sell['satisfied'] else 'HOLD',
                    indicators=values, buy=buy, sell=sell)
