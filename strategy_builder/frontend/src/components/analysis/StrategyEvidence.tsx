import type { ReactNode } from "react";

export type ConditionEvidence = {
  left_label?: string;
  left?: number;
  operator: string;
  right_label?: string;
  right?: number;
  satisfied: boolean;
  previous?: { left: number; right: number } | null;
  children?: ConditionEvidence[];
};

export function ConditionReason({ evidence }: { evidence: ConditionEvidence | null }) {
  if (!evidence) return <p className="text-sm text-slate-500">조건 없음 또는 판단 데이터 부족</p>;
  return (
    <div className="my-2 border-l-2 border-slate-200 pl-3 dark:border-slate-700">
      {evidence.children ? (
        <>
          <p className="text-sm font-medium">{evidence.operator} · {evidence.satisfied ? "충족" : "미충족"}</p>
          {evidence.children.map((child, index) => <ConditionReason key={index} evidence={child} />)}
        </>
      ) : (
        <>
          <p className="text-sm break-words">
            {evidence.left_label ?? "좌변"} {evidence.left} {evidence.operator} {evidence.right_label ?? "우변"} {evidence.right}
            {" → "}{evidence.satisfied ? "충족" : "미충족"}
          </p>
          {evidence.previous && <p className="mt-1 text-xs text-slate-500">이전 봉: 좌변 {evidence.previous.left}, 우변 {evidence.previous.right}</p>}
        </>
      )}
    </div>
  );
}

export function StrategyEvidence({ indicators, buy, sell, children }: {
  indicators: Record<string, number | null>;
  buy: ConditionEvidence | null;
  sell: ConditionEvidence | null;
  children?: ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div><h3 className="text-sm font-semibold">매수 조건</h3><ConditionReason evidence={buy} /></div>
        <div><h3 className="text-sm font-semibold">매도 조건</h3><ConditionReason evidence={sell} /></div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="mb-2 text-left font-semibold">판단에 사용한 지표 값</caption>
          <thead><tr className="border-b text-left"><th className="px-3 py-2">지표</th><th className="px-3 py-2">값</th></tr></thead>
          <tbody>{Object.entries(indicators).map(([name, value]) => (
            <tr key={name} className="border-b border-slate-100 dark:border-slate-800"><td className="px-3 py-2">{name}</td><td className="px-3 py-2 font-mono">{value ?? "데이터 부족"}</td></tr>
          ))}</tbody>
        </table>
      </div>
      {children}
    </div>
  );
}
