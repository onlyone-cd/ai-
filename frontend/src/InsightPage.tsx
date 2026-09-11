import { useEffect, useRef, useState, type ReactNode } from "react";
import { Activity, BarChart3, Clock3, RefreshCw, Sparkles, Target, TrendingDown, TrendingUp, UserCheck, Users } from "lucide-react";
import { api, type InsightChannels, type InsightFunnel, type InsightInterviewerBias, type InsightOfferConversion, type InsightReport, type InsightTimeToHire } from "./lib/api";

type InsightTab = "report" | "funnel" | "channels" | "time" | "bias" | "offer";

const STAGE_LABELS: Record<string, string> = {
  pending: "待处理", ai_screen: "AI 初筛", business_review: "业务复核", interview_first: "一面",
  interview_second: "二面", interview_final: "终面", offer: "Offer", onboarded: "已入职", rejected: "已淘汰",
};

const TABS: { key: InsightTab; label: string; icon: ReactNode }[] = [
  { key: "report", label: "总览", icon: <Sparkles size={15} /> },
  { key: "funnel", label: "招聘漏斗", icon: <TrendingUp size={15} /> },
  { key: "channels", label: "渠道效果", icon: <Users size={15} /> },
  { key: "time", label: "招聘周期", icon: <Clock3 size={15} /> },
  { key: "bias", label: "评分偏差", icon: <UserCheck size={15} /> },
  { key: "offer", label: "Offer 转化", icon: <BarChart3 size={15} /> },
];

export default function InsightPage() {
  const [tab, setTab] = useState<InsightTab>("report");
  const [report, setReport] = useState<InsightReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [days, setDays] = useState(90);
  const cacheRef = useRef(new Map<number, InsightReport>());
  const requestIdRef = useRef(0);

  async function load(targetDays: number, force = false) {
    const cached = cacheRef.current.get(targetDays);
    if (cached && !force) {
      setReport(cached); setLoading(false); setError(""); return;
    }
    const requestId = ++requestIdRef.current;
    if (force) setRefreshing(true); else setLoading(true);
    setError("");
    try {
      const nextReport = await api.insightReport(targetDays, force);
      if (requestId !== requestIdRef.current) return;
      cacheRef.current.set(targetDays, nextReport);
      setReport(nextReport);
    } catch (requestError) {
      if (requestId !== requestIdRef.current) return;
      setError(requestError instanceof Error ? requestError.message : "洞察数据加载失败，请稍后重试。");
    } finally {
      if (requestId === requestIdRef.current) { setLoading(false); setRefreshing(false); }
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void load(days), 120);
    return () => window.clearTimeout(timer);
  }, [days]);

  const generatedAt = report?.generated_at
    ? new Date(report.generated_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "等待数据";

  return (
    <section className="insight-page space-y-3" data-testid="insight-page">
      <header className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_12px_36px_rgba(15,23,42,0.06)]">
        <div className="flex flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div className="min-w-0">
            <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold tracking-wide text-blue-600">
              <span className="grid h-6 w-6 place-items-center rounded-lg bg-blue-600 text-white shadow-[0_5px_14px_rgba(37,99,235,0.28)]"><Sparkles size={13} /></span>
              招聘数据洞察
            </div>
            <h1 className="text-xl font-bold tracking-tight text-slate-950">深度洞察</h1>
            <p className="mt-1 text-xs leading-5 text-slate-500">聚合漏斗、渠道与转化数据，快速定位招聘流程中的异常。</p>
          </div>
          <div className="flex shrink-0 items-center gap-2 self-start rounded-full bg-emerald-50 px-2.5 py-1.5 text-[10px] font-medium text-emerald-700 sm:self-center">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />数据更新于 {generatedAt}
          </div>
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/70 px-3 py-2.5 sm:px-5">
          <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm" aria-label="统计周期">
            {[30, 90, 180].map((period) => (
              <button key={period} className={`min-w-[64px] rounded-lg px-2.5 py-1.5 text-[11px] font-semibold transition ${days === period ? "bg-slate-900 text-white shadow-sm" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"}`} onClick={() => setDays(period)} aria-pressed={days === period}>
                {period} 天
              </button>
            ))}
          </div>
          <button className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3 text-[11px] font-semibold text-blue-700 transition hover:bg-blue-100 disabled:cursor-wait disabled:opacity-60" onClick={() => void load(days, true)} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} /><span>{refreshing ? "更新中" : "刷新"}</span>
          </button>
        </div>
      </header>

      <nav className="overflow-x-auto rounded-2xl border border-slate-200/80 bg-white p-1.5 shadow-[0_8px_24px_rgba(15,23,42,0.04)] [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" aria-label="洞察维度">
        <div className="flex min-w-max gap-1">
          {TABS.map((item) => (
            <button key={item.key} className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-[11px] font-semibold transition ${tab === item.key ? "bg-blue-600 text-white shadow-[0_5px_14px_rgba(37,99,235,0.22)]" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"}`} onClick={() => setTab(item.key)} aria-current={tab === item.key ? "page" : undefined}>
              {item.icon}<span>{item.label}</span>
            </button>
          ))}
        </div>
      </nav>

      {error && <div className="flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-700" role="alert"><span>{error}</span><button className="shrink-0 font-semibold underline" onClick={() => void load(days, true)}>重试</button></div>}
      {loading && !report && <InsightSkeleton />}
      {report && <div className={loading ? "pointer-events-none opacity-60" : ""} aria-busy={loading}>
        {tab === "report" && <ReportView report={report} />}
        {tab === "funnel" && <FunnelView funnel={report.funnel} />}
        {tab === "channels" && <ChannelsView channels={report.channels} />}
        {tab === "time" && <TimeView data={report.time_to_hire} />}
        {tab === "bias" && <BiasView data={report.interviewer_bias} />}
        {tab === "offer" && <OfferView data={report.offer_conversion} />}
      </div>}
    </section>
  );
}

function ReportView({ report }: { report: InsightReport }) {
  const { funnel, channels, time_to_hire, interviewer_bias, offer_conversion } = report;
  const bottleneck = funnel.bottlenecks[0];
  return <div className="space-y-3" data-testid="insight-report">
    <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
      <MetricCard label="候选人" value={channels.total} note={`近 ${report.period_days} 天`} icon={<Users size={16} />} tone="blue" />
      <MetricCard label="招聘周期" value={time_to_hire.samples ? `${time_to_hire.avg_days}天` : "—"} note={time_to_hire.samples ? `${time_to_hire.samples} 个样本` : "暂无入职样本"} icon={<Clock3 size={16} />} tone="emerald" />
      <MetricCard label="Offer 接受率" value={offer_conversion.total ? `${offer_conversion.acceptance_rate}%` : "—"} note={offer_conversion.total ? `${offer_conversion.accepted}/${offer_conversion.total} 接受` : "暂无 Offer 样本"} icon={<Target size={16} />} tone="violet" />
      <MetricCard label="高风险环节" value={funnel.bottlenecks.length} note={bottleneck ? stageLabel(bottleneck) : "流程稳定"} icon={<Activity size={16} />} tone="amber" />
    </div>

    <div className="grid gap-3 xl:grid-cols-[1.15fr_0.85fr]">
      <Panel title="本期重点" eyebrow="PRIORITY" icon={<TrendingDown size={15} />}>
        <div className={`rounded-xl border p-3.5 ${bottleneck ? "border-amber-200 bg-amber-50/80" : "border-emerald-200 bg-emerald-50/80"}`}>
          <div className="flex items-start gap-3">
            <div className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${bottleneck ? "bg-amber-500 text-white" : "bg-emerald-500 text-white"}`}>{bottleneck ? <Activity size={17} /> : <TrendingUp size={17} />}</div>
            <div className="min-w-0"><p className="text-sm font-bold text-slate-900">{bottleneck ? `${stageLabel(bottleneck)}是当前主要瓶颈` : "当前未发现高风险瓶颈"}</p><p className="mt-1 text-[11px] leading-5 text-slate-600">{funnel.bottleneck_analysis || (bottleneck ? "建议核对该阶段的评估标准、排期等待时间及候选人退出原因。" : "各阶段流失率处于正常范围，可继续观察趋势变化。")}</p></div>
          </div>
        </div>
      </Panel>
      <Panel title="Offer 转化" eyebrow="CONVERSION" icon={<Target size={15} />}><OfferSummary data={offer_conversion} /></Panel>
    </div>

    <div className="grid gap-3 xl:grid-cols-2">
      <Panel title="招聘漏斗" eyebrow="FUNNEL" icon={<TrendingUp size={15} />}><FunnelBars funnel={funnel} limit={6} /></Panel>
      <Panel title="渠道质量" eyebrow="SOURCE" icon={<Users size={15} />}><ChannelBars channels={channels} limit={5} /></Panel>
    </div>

    <Panel title="面试官评分偏差" eyebrow="CONSISTENCY" icon={<UserCheck size={15} />}>
      {interviewer_bias.interviewers.length ? <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{interviewer_bias.interviewers.slice(0, 6).map((item) =>
        <div key={item.interviewer_id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2.5"><div><p className="text-xs font-semibold text-slate-900">{item.interviewer_name}</p><p className="mt-0.5 text-[10px] text-slate-500">{item.count} 次评分 · 均值 {item.avg_rating}</p></div><span className={`rounded-lg px-2 py-1 text-[10px] font-semibold ${biasTone(item.bias_direction)}`}>{signed(item.bias)}</span></div>
      )}</div> : <EmptyNote>暂无足够的面试反馈数据</EmptyNote>}
    </Panel>
  </div>;
}

function FunnelView({ funnel }: { funnel: InsightFunnel }) {
  return <Panel title="招聘漏斗详情" eyebrow="FUNNEL ANALYSIS" icon={<TrendingUp size={15} />}>
    <p className="mb-3 text-[11px] leading-5 text-slate-500">统计期内新进入流程 {funnel.cohort_size} 组候选人-岗位，当前已淘汰 {funnel.rejected} 组；跳过的阶段按已完成计算。</p>
    <FunnelBars funnel={funnel} />
  </Panel>;
}
function ChannelsView({ channels }: { channels: InsightChannels }) { return <Panel title="渠道效果分析" eyebrow={`${channels.total} CANDIDATES`} icon={<Users size={15} />}><ChannelBars channels={channels} /></Panel>; }

function TimeView({ data }: { data: InsightTimeToHire }) {
  return <Panel title="招聘周期分析" eyebrow="TIME TO HIRE" icon={<Clock3 size={15} />}>
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4"><CompactMetric value={data.samples ? `${data.avg_days}天` : "—"} label="平均周期" tone="blue" /><CompactMetric value={data.samples ? `${data.median_days}天` : "—"} label="中位数" tone="slate" /><CompactMetric value={data.samples ? `${data.min_days}天` : "—"} label="最短周期" tone="emerald" /><CompactMetric value={data.samples ? `${data.max_days}天` : "—"} label="最长周期" tone="rose" /></div>
    <p className="mt-3 text-[11px] text-slate-500">{data.samples ? `统计样本：${data.samples} 位已入职候选人` : "统计期内暂无已入职样本，暂时无法计算招聘周期。"}</p>{data.ai_analysis && <AnalysisText>{data.ai_analysis}</AnalysisText>}
  </Panel>;
}

function BiasView({ data }: { data: InsightInterviewerBias }) {
  return <Panel title="面试官评分偏差" eyebrow={`${data.total_feedbacks} FEEDBACKS`} icon={<UserCheck size={15} />}>
    <div className="mb-3 flex items-center gap-2 rounded-xl bg-blue-50 px-3 py-2 text-[11px] text-blue-700">全局平均评分 <strong>{data.global_avg_rating}/5</strong><span className="text-blue-300">·</span>标准差 {data.global_std}</div>
    {data.interviewers.length ? <div className="space-y-2">{data.interviewers.map((item) => <div key={item.interviewer_id} className="flex items-center justify-between rounded-xl border border-slate-100 px-3 py-2.5"><div><p className="text-xs font-semibold">{item.interviewer_name}</p><p className="mt-0.5 text-[10px] text-slate-500">平均 {item.avg_rating}/5 · {item.count} 次评分</p></div><span className={`rounded-lg px-2 py-1 text-[10px] font-semibold ${biasTone(item.bias_direction)}`}>{item.bias_direction} {signed(item.bias)}</span></div>)}</div> : <EmptyNote>暂无足够的面试反馈数据</EmptyNote>}
  </Panel>;
}

function OfferView({ data }: { data: InsightOfferConversion }) {
  return <Panel title="Offer 转化分析" eyebrow="OFFER CONVERSION" icon={<Target size={15} />}><OfferSummary data={data} /><div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4"><CompactMetric value={data.total} label="Offer 总量" tone="blue" /><CompactMetric value={data.accepted} label="已接受" tone="emerald" /><CompactMetric value={data.declined} label="已拒绝" tone="rose" /><CompactMetric value={data.accepted ? `${data.avg_salary}K` : "—"} label="已接受平均薪资" tone="violet" /></div></Panel>;
}

function FunnelBars({ funnel, limit }: { funnel: InsightFunnel; limit?: number }) {
  const items = limit ? funnel.funnel.slice(0, limit) : funnel.funnel;
  const maximum = Math.max(...items.map((item) => item.entered), 1);
  if (!items.length) return <EmptyNote>暂无漏斗数据</EmptyNote>;
  return <div className="space-y-3">{items.map((stage) => <div key={stage.stage}><div className="mb-1.5 flex items-center justify-between gap-3 text-[11px]"><span className="flex items-center gap-1.5 font-semibold text-slate-700">{stageLabel(stage.stage)}{stage.is_bottleneck && <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[9px] text-amber-700">瓶颈</span>}</span><span className="text-slate-500">{stage.entered} 人 <span className="text-slate-300">/</span> 流失 {stage.drop_rate}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${stage.is_bottleneck ? "bg-gradient-to-r from-amber-400 to-orange-500" : "bg-gradient-to-r from-blue-500 to-cyan-400"}`} style={{ width: `${stage.entered ? Math.max(4, stage.entered / maximum * 100) : 0}%` }} /></div></div>)}</div>;
}

function ChannelBars({ channels, limit }: { channels: InsightChannels; limit?: number }) {
  const items = limit ? channels.channels.slice(0, limit) : channels.channels;
  const maximum = Math.max(...items.map((item) => item.total), 1);
  if (!items.length) return <EmptyNote>暂无渠道数据</EmptyNote>;
  return <div className="space-y-3">{items.map((channel) => <div key={channel.source}><div className="mb-1.5 flex items-center justify-between gap-3 text-[11px]"><span className="font-semibold text-slate-700">{sourceLabel(channel.source)}</span><span className="text-slate-500">{channel.total} 人 · 入职率 {channel.onboard_rate}%</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-gradient-to-r from-violet-500 to-blue-500" style={{ width: `${Math.max(4, channel.total / maximum * 100)}%` }} /></div></div>)}</div>;
}

function OfferSummary({ data }: { data: InsightOfferConversion }) {
  if (!data.total) return <EmptyNote>统计期内暂无 Offer，暂时无法计算接受率</EmptyNote>;
  const rate = Math.max(0, Math.min(100, data.acceptance_rate));
  return <div className="flex items-center gap-5"><div className="relative grid h-24 w-24 shrink-0 place-items-center rounded-full" style={{ background: `conic-gradient(#2563eb ${rate}%, #e2e8f0 0)` }}><div className="grid h-[72px] w-[72px] place-items-center rounded-full bg-white text-center"><div><strong className="text-xl text-slate-950">{rate}%</strong><p className="text-[9px] text-slate-400">接受率</p></div></div></div><div className="min-w-0 flex-1 space-y-2 text-[11px]"><LegendRow color="bg-emerald-500" label="已接受" value={data.accepted} /><LegendRow color="bg-rose-500" label="已拒绝" value={data.declined} /><LegendRow color="bg-slate-300" label="待处理/其他" value={data.sent + data.draft + data.cancelled} /></div></div>;
}

function Panel({ title, eyebrow, icon, children }: { title: string; eyebrow: string; icon: ReactNode; children: ReactNode }) { return <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-[0_8px_28px_rgba(15,23,42,0.045)]"><header className="mb-3 flex items-center justify-between"><div><p className="text-[9px] font-bold tracking-[0.15em] text-blue-500">{eyebrow}</p><h2 className="mt-0.5 text-sm font-bold text-slate-900">{title}</h2></div><span className="grid h-8 w-8 place-items-center rounded-xl bg-slate-100 text-slate-600">{icon}</span></header>{children}</section>; }

function MetricCard({ label, value, note, icon, tone }: { label: string; value: string | number; note: string; icon: ReactNode; tone: "blue" | "emerald" | "violet" | "amber" }) {
  const tones = { blue: "bg-blue-50 text-blue-600", emerald: "bg-emerald-50 text-emerald-600", violet: "bg-violet-50 text-violet-600", amber: "bg-amber-50 text-amber-600" };
  return <div className="rounded-2xl border border-slate-200/80 bg-white p-3.5 shadow-[0_7px_24px_rgba(15,23,42,0.04)]"><div className={`mb-3 grid h-8 w-8 place-items-center rounded-xl ${tones[tone]}`}>{icon}</div><div className="text-[10px] font-medium text-slate-500">{label}</div><div className="mt-0.5 truncate text-xl font-bold tracking-tight text-slate-950">{value}</div><div className="mt-1 truncate text-[9px] text-slate-400">{note}</div></div>;
}

function CompactMetric({ value, label, tone }: { value: string | number; label: string; tone: "blue" | "slate" | "emerald" | "rose" | "violet" }) {
  const tones = { blue: "bg-blue-50 text-blue-700", slate: "bg-slate-100 text-slate-800", emerald: "bg-emerald-50 text-emerald-700", rose: "bg-rose-50 text-rose-700", violet: "bg-violet-50 text-violet-700" };
  return <div className={`rounded-xl p-3 text-center ${tones[tone]}`}><div className="text-lg font-bold">{value}</div><div className="mt-0.5 text-[10px] opacity-70">{label}</div></div>;
}

function LegendRow({ color, label, value }: { color: string; label: string; value: number }) { return <div className="flex items-center justify-between"><span className="flex items-center gap-2 text-slate-500"><span className={`h-2 w-2 rounded-full ${color}`} />{label}</span><strong className="text-slate-900">{value}</strong></div>; }
function AnalysisText({ children }: { children: ReactNode }) { return <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 p-3 text-[11px] leading-5 text-blue-800">{children}</div>; }
function EmptyNote({ children }: { children: ReactNode }) { return <div className="grid min-h-24 place-items-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-[11px] text-slate-400">{children}</div>; }
function InsightSkeleton() { return <div className="space-y-3" aria-label="正在加载洞察数据"><div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">{[0, 1, 2, 3].map((item) => <div key={item} className="h-32 animate-pulse rounded-2xl bg-slate-200/70" />)}</div><div className="h-64 animate-pulse rounded-2xl bg-slate-200/70" /></div>; }
function stageLabel(stage: string): string { return STAGE_LABELS[stage] || stage; }
function sourceLabel(source: string): string { return source === "upload" ? "简历上传" : source === "boss" ? "BOSS 直聘" : source || "未知渠道"; }
function biasTone(direction: string): string { if (direction === "偏高") return "bg-rose-50 text-rose-700"; if (direction === "偏低") return "bg-blue-50 text-blue-700"; return "bg-emerald-50 text-emerald-700"; }
function signed(value: number): string { return `${value >= 0 ? "+" : ""}${value}`; }
