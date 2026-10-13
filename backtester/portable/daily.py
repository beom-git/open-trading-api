"""Long-only whole-share daily engine. Decisions at close, execution at next open."""
from decimal import Decimal, ROUND_FLOOR


def simulate(bars, decide, initial_cash=10000, fee_rate=0.001, slippage=0.001):
    D = lambda x: Decimal(str(x))
    cash, fee, slip = D(initial_cash), D(fee_rate), D(slippage)
    if cash <= 0 or not 0 <= fee < 1 or not 0 <= slip < 1:
        raise ValueError('Invalid cash, fee or slippage')
    if len(bars) < 2:
        raise ValueError('At least two bars are required')
    quantity, peak, realized = 0, cash, D(0)
    pending = entry = None
    points, decisions, fills, trades = [], [], [], []
    benchmark_qty = int((cash / D(bars[0]['open'])).to_integral_value(rounding=ROUND_FLOOR))
    benchmark_cash = cash - benchmark_qty * D(bars[0]['open'])
    for i, bar in enumerate(bars):
        if pending:
            action = pending['action']
            price = D(bar['open']) * (1 + slip if action == 'BUY' else 1 - slip)
            qty = int((cash / (price * (1 + fee))).to_integral_value(rounding=ROUND_FLOOR)) if action == 'BUY' else quantity
            if qty > 0 and ((action == 'BUY' and quantity == 0) or (action == 'SELL' and quantity > 0)):
                cost = price * qty * fee
                fill = dict(action=action, signal_date=pending['date'], execution_date=bar['date'],
                            price=float(price), quantity=qty, cost=float(cost), decision_index=i-1)
                fills.append(fill)
                if action == 'BUY':
                    cash -= price * qty + cost
                    quantity = qty
                    entry = fill
                else:
                    pnl = (price - D(entry['price'])) * qty - cost - D(entry['cost'])
                    cash += price * qty - cost
                    realized += pnl
                    trades.append(dict(entry=entry, exit=fill, profit_loss=float(pnl)))
                    quantity, entry = 0, None
        decision = decide(i)
        decision.update(date=bar['date'])
        decisions.append(decision)
        pending = decision if decision['action'] in ('BUY', 'SELL') else None
        equity = cash + quantity * D(bar['close'])
        peak = max(peak, equity)
        points.append(dict(date=bar['date'], close=float(bar['close']), cash=float(cash), quantity=quantity,
                           equity=float(equity), realized_pnl=float(realized), drawdown=float(equity/peak-1),
                           benchmark=float(benchmark_cash + benchmark_qty*D(bar['close']))))
    return dict(points=points, decisions=decisions, fills=fills, trades=trades,
                total_return_pct=float(D(points[-1]['equity'])/D(initial_cash)-1),
                max_drawdown=-min(p['drawdown'] for p in points), total_trades=len(trades),
                win_rate=sum(t['profit_loss'] > 0 for t in trades)/len(trades) if trades else None,
                final_equity=points[-1]['equity'], open_position=entry,
                execution_rule='Daily close signal; next available daily open; no forced final liquidation')
