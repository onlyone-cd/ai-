import { useEffect, useState } from "react";
import { BarChart3, Clock3, MapPin, Sparkles, TrendingUp, UserCheck, Users, X } from "lucide-react";
import { api, InsightFunnel, InsightChannels, InsightTimeToHire, InsightInterviewerBias, InsightOfferConversion, InsightReport } from "./lib/api";

export default function InsightPage() {
  const [tab, setTab] = useState<"funnel" | "channels" | "time" | "bias" | "offer" | "report">("report");
  const [report, setReport] = useState<InsightReport | null>(null);
  const [funnel, setFunnel] = useState<InsightFunnel | null>(null);
  const [channels, setChannels] = useState<InsightChannels | null>(null);
  const [timeToHire, setTimeToHire] = useState<InsightTimeToHire | null>(null);
  const [bias, setBias] = useState<InsightInterviewerBias | null>(null);
  const [offer, setOffer] = useState<InsightOfferConversion | null>(null);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(90);

  const tabs = [
    { key: "report", label: "综合报告", icon: <Sparkles size={15} /> },
    { key: "funnel", label: "漏斗分析", icon: <TrendingUp size={15} /> },
    { key: "channels", label: "渠道效果", icon: <Users size={15} /> },
    { key: "time", label: "招聘周期", icon: <Clock3 size={15} /> },
    { key: "bias", label: "面试官偏差", icon: <UserCheck size={15} /> },
    { key: "offer", label: "Offer 转化", icon: <BarChart3 size={15} /> },
  ] as const;

  async function load() {
    setLoading(true);
    try {
      const [r, f, c, t, b, o] = await Promise.all([
        api.insightReport(days),
        api.insightFunnel(days),
        api.insightChannels(days),
        api.insightTimeToHire(days),
        api.insightInterviewerBias(days),
        api.insightOfferConversion(days),
      ]);
      setReport(r);
      setFunnel(f);
      setChannels(c);
      setTimeToHire(t);
      setBias(b);
      setOffer(o);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [days]);

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-ink">AI 深度洞察</h1>
          <p className="mt-1 text-sm text-steel">用 AI 分析招聘数据，发现瓶颈、预测趋势、优化策略。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {[30, 90, 180].map((d) => (
            <button key={d} className={days === d ? "active period-tab" : "period-tab"} onClick={() => setDays(d)}>
              近 {d} 天
            </button>
          ))}
          <button className="secondary-button" onClick={load} disabled={loading}>
            <Sparkles size={16} className={loading ? "animate-spin" : ""} />
            {loading ? "分析中..." : "刷新洞察"}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-line pb-2">
        {tabs.map((t) => (
          <button key={t.key} className={`insight-tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {tab === "report" && report && <ReportView report={report} />}
      {tab === "funnel" && funnel && <FunnelView funnel={funnel} />}
      {tab === "channels" && channels && <ChannelsView channels={channels} />}
      {tab === "time" && timeToHire && <TimeToHireView data={timeToHire} />}
      {tab === "bias" && bias && <BiasView data={bias} />}
      {tab === "offer" && offer && <OfferView data={offer} />}
    </section>
  );
}

function ReportView({ report }: { report: InsightReport }) {
  const b = report.funnel.bottlenecks;
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-3">
        <div className="design-card">
          <h3 className="font-semibold">漏斗瓶颈</h3>
          {b.length ? (
            <div className="mt-2 space-y-2">
              {b.map((s) => <div key={s} className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">瓶颈阶段：{stageLabel(s)}</div>)}
              {report.funnel.bottleneck_analysis && <p className="mt-2 text-xs text-steel">{report.funnel.bottleneck_analysis}</p>}
            </div>
          ) : <p className="mt-2 text-sm text-steel">当前漏斗无显著瓶颈。</p>}
        </div>
        <div className="design-card">
          <h3 className="font-semibold">渠道效果</h3>
          <p className="mt-2 text-sm text-steel">共 {report.channels.total} 位候选人</p>
          <div className="mt-2 space-y-1">
            {report.channels.channels.slice(0, 4).map((c) => (
              <div className="flex justify-between text-sm" key={c.source}>
                <span>{c.source}</span>
                <span className="text-steel">{c.total} 人 · {c.onboard_rate}% 入职率</span>
              </div>
            ))}
          </div>
        </div>
        <div className="design-card">
          <h3 className="font-semibold">招聘周期</h3>
          <p className="mt-2 text-2xl font-bold">{report.time_to_hire.avg_days} 天</p>
          <p className="text-sm text-steel">中位数 {report.time_to_hire.median_days} 天 · 样本 {report.time_to_hire.samples} 人</p>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="design-card">
          <h3 className="font-semibold">面试官评分偏差</h3>
          <p className="mt-2 text-sm text-steel">全局平均评分 {report.interviewer_bias.global_avg_rating} / 5</p>
          {report.interviewer_bias.interviewers.filter((i) => i.bias_direction !== "正常").slice(0, 3).map((i) => (
            <div key={i.interviewer_id} className="mt-1 rounded-md bg-amber-50 px-3 py-2 text-sm">
              {i.interviewer_name} · 偏差 {i.bias >= 0 ? "+" : ""}{i.bias} ({i.bias_direction})
            </div>
          ))}
        </div>
        <div className="design-card">
          <h3 className="font-semibold">Offer 转化</h3>
          <p className="mt-2 text-2xl font-bold">{report.offer_conversion.acceptance_rate}%</p>
          <p className="text-sm text-steel">{report.offer_conversion.accepted} 接受 / {report.offer_conversion.total} 总量</p>
        </div>
      </div>
    </div>
  );
}

function FunnelView({ funnel }: { funnel: InsightFunnel }) {
  return (
    <div className="design-card">
      <h2 className="font-semibold">招聘漏斗</h2>
      <p className="mt-1 text-sm text-steel">各阶段候选人进入数量、流失率和瓶颈识别。</p>
      <div className="mt-4 space-y-2">
        {funnel.funnel.map((s) => (
          <div key={s.stage} className={`rounded-md border px-4 py-3 ${s.is_bottleneck ? "border-red-300 bg-red-50" : "border-line"}`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{stageLabel(s.stage)}</span>
                {s.is_bottleneck && <span className="badge danger">瓶颈</span>}
              </div>
              <span className="text-sm text-steel">进入 {s.entered} 人 · 流失 {s.dropped_off} 人 ({s.drop_rate}%)</span>
            </div>
            <div className="mt-2 h-2 w-full rounded-full bg-gray-100">
              <div className="h-2 rounded-full bg-blue-500" style={{ width: `${Math.max(1, Math.min(100, s.entered / Math.max(funnel.funnel[0].entered, 1) * 100))}%` }} />
            </div>
          </div>
        ))}
      </div>
      {funnel.bottleneck_analysis && (
        <div className="mt-4 rounded-md bg-blue-50 px-4 py-3 text-sm">
          <strong>AI 分析：</strong> {funnel.bottleneck_analysis}
        </div>
      )}
    </div>
  );
}

function ChannelsView({ channels }: { channels: InsightChannels }) {
  return (
    <div className="design-card">
      <h2 className="font-semibold">渠道效果分析</h2>
      <p className="mt-1 text-sm text-steel">各来源候选人的数量、入职率和平均匹配分。</p>
      <div className="mt-4 space-y-2">
        {channels.channels.map((c) => (
          <div className="rounded-md border border-line px-4 py-3" key={c.source}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">{c.source}</span>
              <span className="text-sm text-steel">{c.total} 人</span>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-3 text-sm">
              <div>入职率 <strong>{c.onboard_rate}%</strong></div>
              <div>入职 {c.onboarded} 人</div>
              <div>平均匹配分 <strong>{c.avg_match_score}</strong></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TimeToHireView({ data }: { data: InsightTimeToHire }) {
  return (
    <div className="design-card">
      <h2 className="font-semibold">招聘周期分析</h2>
      <p className="mt-1 text-sm text-steel">从候选人进入流程到入职的平均天数。</p>
      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-blue-600">{data.avg_days}</div>
          <div className="text-sm text-steel">平均天数</div>
        </div>
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold">{data.median_days}</div>
          <div className="text-sm text-steel">中位数</div>
        </div>
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-green-600">{data.min_days}</div>
          <div className="text-sm text-steel">最短</div>
        </div>
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-red-600">{data.max_days}</div>
          <div className="text-sm text-steel">最长</div>
        </div>
      </div>
      <p className="mt-3 text-sm text-steel">样本量：{data.samples} 位已入职候选人</p>
      {data.ai_analysis && (
        <div className="mt-3 rounded-md bg-blue-50 px-4 py-3 text-sm">
          <strong>AI 分析：</strong> {data.ai_analysis}
        </div>
      )}
    </div>
  );
}

function BiasView({ data }: { data: InsightInterviewerBias }) {
  return (
    <div className="design-card">
      <h2 className="font-semibold">面试官评分偏差分析</h2>
      <p className="mt-1 text-sm text-steel">识别面试官评分趋势，发现评分偏高或偏低的情况。</p>
      <div className="mt-4 space-y-2">
        {data.interviewers.map((i) => {
          const tone = i.bias_direction === "偏高" ? "text-red-600" : i.bias_direction === "偏低" ? "text-blue-600" : "text-green-600";
          return (
            <div className="rounded-md border border-line px-4 py-3" key={i.interviewer_id}>
              <div className="flex items-center justify-between">
                <span className="font-semibold">{i.interviewer_name}</span>
                <span className={`font-semibold ${tone}`}>{i.bias_direction} (偏差 {i.bias >= 0 ? "+" : ""}{i.bias})</span>
              </div>
              <div className="mt-1 grid grid-cols-3 gap-3 text-sm text-steel">
                <span>平均评分 {i.avg_rating} / 5</span>
                <span>标准差 {i.std}</span>
                <span>评分次数 {i.count}</span>
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-sm text-steel">全局平均评分 {data.global_avg_rating} / 5 · 总反馈 {data.total_feedbacks} 条</p>
    </div>
  );
}

function OfferView({ data }: { data: InsightOfferConversion }) {
  return (
    <div className="design-card">
      <h2 className="font-semibold">Offer 转化分析</h2>
      <p className="mt-1 text-sm text-steel">Offer 发送、接受、拒绝的统计和趋势。</p>
      <div className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-blue-600">{data.total}</div>
          <div className="text-sm text-steel">总 Offer</div>
        </div>
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-green-600">{data.accepted}</div>
          <div className="text-sm text-steel">已接受</div>
        </div>
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-red-600">{data.declined}</div>
          <div className="text-sm text-steel">已拒绝</div>
        </div>
        <div className="rounded-md border border-line px-4 py-3 text-center">
          <div className="text-2xl font-bold text-purple-600">{data.acceptance_rate}%</div>
          <div className="text-sm text-steel">接受率</div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4 text-sm text-steel">
        <div>已发送 {data.sent} · 草稿 {data.draft} · 已取消 {data.cancelled}</div>
        <div>平均薪资 {data.avg_salary}K</div>
      </div>
    </div>
  );
}

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    pending: "待处理", ai_screen: "AI 初筛", business_review: "业务复核",
    interview_first: "一面", interview_second: "二面", interview_final: "终面",
    offer: "Offer", onboarded: "已入职", rejected: "已淘汰",
  };
  return map[stage] || stage;
}
