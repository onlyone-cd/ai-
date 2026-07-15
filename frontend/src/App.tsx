import { useEffect, useMemo, useRef, useState } from "react";
import { Button as AntButton, Card as AntCard, Empty as AntEmpty, Layout as AntLayout, Menu as AntMenu, Spin as AntSpin, Statistic as AntStatistic } from "antd";
import {
  ArrowLeft,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Database,
  Download,
  FileText,
  GraduationCap,
  HandCoins,
  LogOut,
  Mail,
  MapPin,
  MessageSquareText,
  Phone,
  Plus,
  RefreshCw,
  Search,
  SendHorizontal,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  Upload,
  UserCog,
  UserRound,
  Wrench,
  Users,
  X
} from "lucide-react";
import { api, AgentConversation, AgentMessage, AgentResponse, AiInterviewPlan, AiSettings, AuditLog, BackgroundTask, BiOverview, BossInboxItem, Candidate, clearToken, DataIntegrity, EmployeeAnalysis, EmployeeProfile, EmployeeRecommendation, InterviewAssignment, InterviewFeedback, InterviewMessage, InterviewSpeechStatus, Job, LLMUsageSummary, MatchingWeights, MatchResult, notify, OfferRecord, OpsBackupStatus, OpsDataQuality, OpsDeployGates, OrganizationUnit, PipelineItem, PublicInterviewRoom, setToken, SkillTag, SystemSettings, User } from "./lib/api";

const stageLabels: Record<string, string> = {
  pending: "待处理",
  ai_screen: "AI 初筛",
  business_review: "业务复核",
  interview_first: "一面",
  interview_second: "二面",
  interview_final: "终面",
  offer: "Offer",
  onboarded: "入职",
  rejected: "淘汰"
};

const offerStatusLabels: Record<string, string> = {
  draft: "草稿",
  sent: "已发放",
  accepted: "已接受",
  declined: "已拒绝",
  cancelled: "已取消"
};

type View = "candidates" | "organization" | "internal" | "jobs" | "pipeline" | "interviews" | "offers" | "boss" | "bi" | "agent" | "settings" | "tasks" | "audit" | "users";

async function copyTextToClipboard(text: string) {
  const value = String(text || "");
  if (!value) return false;
  const clipboard = navigator.clipboard;
  if (clipboard && typeof clipboard.writeText === "function") {
    try {
      await clipboard.writeText(value);
      return true;
    } catch {
      // Some production browsers disable Clipboard API on plain HTTP.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, value.length);
  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

function App() {
  const roomToken = window.location.pathname.match(/^\/interview-room\/([^/]+)/)?.[1] || "";
  const [user, setUser] = useState<User | null>(null);
  const [view, setView] = useState<View>("candidates");
  const [loading, setLoading] = useState(true);
  const [feedbackToast, setFeedbackToast] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    const onFeedback = (event: Event) => {
      const detail = (event as CustomEvent<{ type: "success" | "error"; text: string }>).detail;
      setFeedbackToast(detail);
    };
    const onUnhandled = (event: PromiseRejectionEvent) => {
      const text = event.reason instanceof Error ? event.reason.message : "操作失败";
      setFeedbackToast({ type: "error", text });
    };
    window.addEventListener("hireinsight-feedback", onFeedback);
    window.addEventListener("unhandledrejection", onUnhandled);
    return () => {
      window.removeEventListener("hireinsight-feedback", onFeedback);
      window.removeEventListener("unhandledrejection", onUnhandled);
    };
  }, []);

  useEffect(() => {
    if (!feedbackToast) return;
    const timer = window.setTimeout(() => setFeedbackToast(null), 2600);
    return () => window.clearTimeout(timer);
  }, [feedbackToast]);

  useEffect(() => {
    if (roomToken) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, [roomToken]);

  if (loading) return <div className="grid min-h-screen place-items-center text-sm text-steel"><AntSpin tip="正在连接服务" /></div>;
  if (roomToken) return <CandidateInterviewRoom token={roomToken} />;
  if (!user) return <Login onLogin={setUser} />;

  const navItems = [
    { key: "candidates", icon: <Users size={15} />, label: "人才库" },
    { key: "organization", icon: <Building2 size={15} />, label: "组织与内部人才" },
    { key: "jobs", icon: <BriefcaseBusiness size={15} />, label: "岗位匹配" },
    { key: "pipeline", icon: <ChevronRight size={15} />, label: "流程看板" },
    { key: "interviews", icon: <CalendarDays size={15} />, label: "面试管理" },
    { key: "offers", icon: <HandCoins size={15} />, label: "Offer 管理" },
    { key: "boss", icon: <MessageSquareText size={15} />, label: "BOSS 闭环" },
    { key: "bi", icon: <BarChart3 size={15} />, label: "BI 看板" },
    { key: "agent", icon: <Bot size={15} />, label: "AI 助手" },
    { key: "settings", icon: <Settings size={15} />, label: "系统设置" },
    ...(user.role !== "interviewer" ? [{ key: "tasks", icon: <Database size={15} />, label: "后台任务" }] : []),
    ...(user.role === "admin" ? [{ key: "audit", icon: <Clock3 size={15} />, label: "操作日志" }] : []),
    ...(user.role === "admin" ? [{ key: "users", icon: <UserCog size={15} />, label: "用户管理" }] : [])
  ];

  return (
    <AntLayout className="min-h-screen bg-slate-50 text-ink">
      <AntLayout.Sider width={252} className="app-sider fixed inset-y-0 left-0 z-10 hidden border-r border-white/10 bg-slate-950 lg:block">
        <div className="flex h-14 items-center gap-3 border-b border-white/10 px-4">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-white text-mint">
            <Sparkles size={15} />
          </div>
          <div>
            <div className="text-sm font-semibold text-white">HireInsight</div>
            <div className="text-xs text-slate-400">AI 招聘系统</div>
          </div>
        </div>
        <AntMenu
          className="border-0 bg-transparent p-2"
          items={navItems.map((item) => ({ ...item, label: <span data-testid={`nav-${item.key}`}>{item.label}</span> }))}
          mode="inline"
          selectedKeys={[view]}
          theme="dark"
          onClick={({ key }) => setView(key as View)}
        />
      </AntLayout.Sider>

      <AntLayout className="min-h-screen bg-slate-50 lg:pl-[252px]">
        <AntLayout.Header className="sticky top-0 z-10 flex h-10 items-center justify-between border-b border-line bg-white/90 px-3 leading-normal backdrop-blur">
          <div>
            <h1 className="text-sm font-semibold">{titleFor(view)}</h1>
            <p className="text-[11px] text-steel">标签证据 · AI 复核 · 流程同步</p>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-md border border-line px-3 py-2 text-xs sm:flex">
              <ShieldCheck size={15} className="text-mint" />
              {user.name} · {user.role}
            </div>
            <AntButton
              icon={<LogOut size={18} />}
              title="退出登录"
              onClick={() => {
                clearToken();
                setUser(null);
                notify("success", "已退出登录");
              }}
            />
          </div>
        </AntLayout.Header>

        <AntLayout.Content className="app-content p-2.5 lg:p-3" data-testid="app-content">
          <MobileTabs view={view} setView={setView} isAdmin={user.role === "admin"} canUseTasks={user.role !== "interviewer"} />
          {view === "candidates" && <CandidatesPage />}
          {view === "organization" && <InternalTalentPage />}
          {view === "internal" && <InternalTalentPage />}
          {view === "jobs" && <JobsPage />}
          {view === "pipeline" && <PipelinePage />}
          {view === "interviews" && <InterviewsPage />}
          {view === "offers" && <OffersPage />}
          {view === "boss" && <BossPage />}
          {view === "bi" && <BiPage />}
          {view === "agent" && <AgentPage />}
          {view === "settings" && <SettingsPage />}
          {view === "tasks" && <TasksPage setView={setView} />}
          {view === "audit" && <AuditLogsPage />}
          {view === "users" && <UsersPage currentUser={user} />}
        </AntLayout.Content>
        {feedbackToast && <div className={`feedback-toast ${feedbackToast.type}`}>{feedbackToast.text}</div>}
      </AntLayout>
    </AntLayout>
  );
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const data = await api.login(username, password);
      setToken(data.token);
      onLogin(data.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-line bg-white p-6 shadow-panel" data-testid="login-form">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-md bg-mint text-white">
            <Sparkles size={19} />
          </div>
          <div>
            <h1 className="font-semibold">HireInsight</h1>
            <p className="text-xs text-steel">Flask + React 招聘管理系统</p>
          </div>
        </div>
        <label className="field-label">用户名</label>
        <input className="input" data-testid="login-username" value={username} onChange={(event) => setUsername(event.target.value)} />
        <label className="field-label mt-4">密码</label>
        <input className="input" data-testid="login-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        {error && <div className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        <button className="primary-button mt-5 w-full" data-testid="login-submit" type="submit">
          <Check size={17} />
          登录
        </button>
      </form>
    </div>
  );
}

function CandidateInterviewRoom({ token }: { token: string }) {
  const [room, setRoom] = useState<PublicInterviewRoom | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<string[]>([]);
  const [reply, setReply] = useState("");
  const [questionText, setQuestionText] = useState("");
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [cheatEvents, setCheatEvents] = useState<string[]>([]);
  const [speechSupport, setSpeechSupport] = useState({ recognition: false, synthesis: false });
  const [speechStatus, setSpeechStatus] = useState<InterviewSpeechStatus | null>(null);
  const recognitionRef = useRef<any>(null);
  const current = room?.plan.questions[index];

  useEffect(() => {
    setSpeechSupport({
      recognition: Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition),
      synthesis: Boolean(window.speechSynthesis)
    });
    api.publicInterviewRoom(token)
      .then((data) => {
        setRoom(data);
        setAnswers(Array(data.plan.questions.length).fill(""));
        setMessages([{ role: "ai", text: data.plan.opening }]);
        setSubmitted(data.assignment.status === "completed");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "面试间不可用"));
    api.publicInterviewSpeechStatus(token)
      .then((data) => setSpeechStatus(data.speech))
      .catch(() => setSpeechStatus(null));
    return () => {
      window.speechSynthesis?.cancel();
      recognitionRef.current?.stop?.();
    };
  }, [token]);

  useEffect(() => {
    const record = (text: string) => {
      const item = `${new Date().toLocaleTimeString()} ${text}`;
      setCheatEvents((events) => [...events, item]);
      setNotice(`防作弊提醒：${text}`);
    };
    const block = (event: Event) => {
      event.preventDefault();
      record("检测到复制/粘贴/右键等非语音操作");
    };
    const onVisibility = () => {
      if (document.hidden) record("检测到离开面试页面");
    };
    const onBlur = () => record("检测到窗口失焦");
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("blur", onBlur);
    window.addEventListener("paste", block);
    window.addEventListener("copy", block);
    window.addEventListener("cut", block);
    window.addEventListener("contextmenu", block);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("paste", block);
      window.removeEventListener("copy", block);
      window.removeEventListener("cut", block);
      window.removeEventListener("contextmenu", block);
    };
  }, []);

  async function speak(text: string) {
    if (!window.speechSynthesis) {
      setNotice("当前浏览器不支持语音合成，已切换为文字面试模式。请使用 Chrome 打开候选人链接体验语音播报。");
      return;
    }
    api.publicInterviewTts(token, { text, voice: room?.plan.avatar.voice || "zh-CN" }).catch(() => undefined);
    window.speechSynthesis?.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    utterance.rate = 0.95;
    window.speechSynthesis?.speak(utterance);
  }

  function startQuestion() {
    if (!room || !current) return;
    setMessages((items) => items[items.length - 1]?.text === current.question ? items : [...items, { role: "ai", text: current.question }]);
    speak(`${room.plan.opening}。第 ${index + 1} 题，${current.question}`);
  }

  function listen(mode: "answer" | "question" = "answer") {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setNotice("当前浏览器不支持语音识别，无法参加语音面试。请使用 Chrome 打开候选人链接。");
      return;
    }
    const recognition = new SpeechRecognition();
    const startedAt = Date.now();
    let recognizedText = "";
    recognition.lang = "zh-CN";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event: any) => {
      const text = Array.from(event.results).map((result: any) => result[0]?.transcript || "").join("");
      recognizedText = text;
      if (mode === "question") {
        setQuestionText(text);
      } else {
        setAnswers((items) => items.map((item, itemIndex) => itemIndex === index ? text : item));
      }
    };
    recognition.onend = () => {
      setListening(false);
      if (recognizedText.trim()) {
        api.publicInterviewAsr(token, { transcript: recognizedText.trim(), source: "browser_recognition", duration_ms: Date.now() - startedAt }).catch(() => undefined);
      }
    };
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
  }

  async function askFollowUp() {
    if (!current) return;
    const answer = answers[index] || "";
    const data = await api.publicInterviewTurn(token, { question: current.question, answer, intent: "followup" });
    setReply(data.reply);
    setMessages((items) => [...items, { role: "candidate", text: answer || "（未作答）" }, { role: "ai", text: data.reply }]);
    speak(data.reply);
  }

  async function clarifyQuestion() {
    if (!current) return;
    const data = await api.publicInterviewTurn(token, { question: current.question, intent: "clarify", candidate_question: questionText });
    setQuestionText("");
    setReply(data.reply);
    setMessages((items) => [...items, { role: "candidate", text: questionText || "我没理解这道题" }, { role: "ai", text: data.reply }]);
    speak(data.reply);
  }

  async function completeInterview() {
    const data = await api.publicInterviewComplete(token, { answers, messages, cheat_events: cheatEvents });
    setRoom((currentRoom) => currentRoom ? { ...currentRoom, assignment: data.assignment } : currentRoom);
    setSubmitted(true);
    setNotice(data.closing);
    setMessages((items) => [...items, { role: "ai", text: data.closing }]);
    speak(data.closing);
  }

  function next() {
    const nextIndex = Math.min(index + 1, (room?.plan.questions.length || 1) - 1);
    setIndex(nextIndex);
    setReply("");
    if (room?.plan.questions[nextIndex]) {
      setMessages((items) => [...items, { role: "ai", text: room.plan.questions[nextIndex].question }]);
    }
    window.setTimeout(() => room?.plan.questions[nextIndex] && speak(`第 ${nextIndex + 1} 题，${room.plan.questions[nextIndex].question}`), 0);
  }

  if (error) return <div className="grid min-h-screen place-items-center bg-slate-50 p-4 text-sm text-red-700">{error}</div>;
  if (!room) return <div className="grid min-h-screen place-items-center bg-slate-50 text-sm text-steel">正在进入 AI 面试间...</div>;

  const answered = answers.filter((item) => item.trim()).length;
  const progress = Math.round((answered / room.plan.questions.length) * 100);

  return (
    <main className="min-h-screen bg-slate-50 p-4 lg:p-8">
      <section className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[320px_1fr]">
        <aside className="rounded-lg border border-line bg-white p-5 shadow-panel">
          <div className="grid place-items-center text-center">
            <div className={`grid h-24 w-24 place-items-center rounded-full bg-blue-50 text-mint ${listening ? "ring-4 ring-blue-200" : ""}`}>
              <Bot size={44} />
            </div>
            <h1 className="mt-4 text-lg font-semibold">AI 模拟面试官</h1>
            <p className="mt-1 text-sm text-steel">{room.assignment.job.title} · {stageLabels[room.assignment.round]}</p>
          </div>
            <div className="mt-5 rounded-md bg-slate-50 p-3 text-sm text-steel">
              <div>候选人：{room.assignment.candidate.name_masked}</div>
              <div className="mt-1">面试方式：网页面试</div>
              <div className="mt-1">答题进度：{progress}/100</div>
              <div className="mt-1">异常操作记录：{cheatEvents.length} 次</div>
            </div>
            <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs text-steel">
              语音后端：{speechStatus?.asr.enabled ? "ASR" : "ASR未启用"} / {speechStatus?.tts.enabled ? "TTS" : "TTS未启用"}
            </div>
            {!speechSupport.recognition && (
              <div className="mt-3 rounded-md bg-orange-50 px-3 py-2 text-xs text-orange-700">
                当前浏览器不支持语音识别，不能参加语音面试。请使用 Chrome 打开候选人链接。
              </div>
            )}
          <button className="primary-button mt-4 w-full" onClick={startQuestion} disabled={submitted}>
            <Sparkles size={17} />
            {speechSupport.synthesis ? "开始播报" : "查看题目"}
          </button>
        </aside>

        <section className="rounded-lg border border-line bg-white p-5 shadow-panel">
          <div className="flex flex-wrap items-center gap-2">
            <span className="badge">{current?.type}</span>
            <span className="text-xs text-steel">第 {index + 1} / {room.plan.questions.length} 题</span>
            {submitted && <span className="badge">已结束</span>}
          </div>
          <h2 className="mt-4 text-xl font-semibold">{current?.question}</h2>
          <p className="mt-2 text-sm text-steel">评分点：{current?.rubric}</p>
          <div className="mt-4 max-h-64 space-y-2 overflow-auto rounded-lg border border-line bg-slate-50 p-3">
            {messages.map((item, itemIndex) => (
              <div className={`rounded-md px-3 py-2 text-sm ${item.role === "ai" ? "bg-white text-ink" : "ml-auto bg-blue-50 text-blue-800"}`} key={`${item.role}-${itemIndex}`}>
                <div className="mb-1 text-xs font-semibold text-steel">{item.role === "ai" ? "AI 面试官" : "候选人"}</div>
                {item.text}
              </div>
            ))}
          </div>
          <textarea
            className="input mt-5 min-h-40"
            value={answers[index] || ""}
            readOnly
            onPaste={(event) => event.preventDefault()}
            placeholder="这里只显示语音识别结果，不能手动输入或粘贴"
          />
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <div className="input flex items-center text-steel">{questionText || "没听懂时，点击“语音提问”后直接说出问题"}</div>
            <button className="secondary-button shrink-0" onClick={() => listen("question")} disabled={submitted || !speechSupport.recognition || listening}>语音提问</button>
            <button className="secondary-button shrink-0" onClick={clarifyQuestion} disabled={submitted}>解释题目</button>
          </div>
          {notice && <div className="mt-4 rounded-md bg-orange-50 px-3 py-2 text-sm text-orange-700">{notice}</div>}
          {reply && <div className="mt-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">{reply}</div>}
          <div className="mt-5 flex flex-wrap justify-between gap-2">
            <div className="flex flex-wrap gap-2">
              <button className="secondary-button" onClick={() => listen("answer")} disabled={submitted || !speechSupport.recognition || listening}>开始语音识别</button>
              <button className="secondary-button" onClick={() => recognitionRef.current?.stop?.()} disabled={submitted || !listening}>停止识别</button>
              <button className="secondary-button" onClick={askFollowUp} disabled={submitted}>继续追问</button>
            </div>
            <div className="flex flex-wrap gap-2">
              <button className="secondary-button" onClick={completeInterview} disabled={submitted}>结束面试</button>
              <button className="primary-button" onClick={next} disabled={submitted || index >= room.plan.questions.length - 1}>下一题</button>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [stats, setStats] = useState<{ key: string; label: string; count: number }[]>([]);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobQuery, setJobQuery] = useState("");
  const [selectedJobId, setSelectedJobId] = useState(0);
  const [matchResults, setMatchResults] = useState<MatchResult[]>([]);
  const [matchMessage, setMatchMessage] = useState("");
  const [matchLoading, setMatchLoading] = useState(false);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  function loadCandidates() {
    api.candidates(filter).then((data) => {
      setCandidates(data.items);
      setStats(data.experience_stats);
    });
  }

  useEffect(() => {
    loadCandidates();
  }, [filter]);

  useEffect(() => {
    api.jobs().then((data) => {
      setJobs(data.items);
      setSelectedJobId((current) => current || data.items[0]?.id || 0);
    });
  }, []);

  const filteredJobs = useMemo(() => {
    const keyword = jobQuery.trim().toLowerCase();
    if (!keyword) return jobs;
    return jobs.filter((job) =>
      [job.title, job.city, job.department, job.job_code, job.jd_structured?.skill_tags_raw]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    );
  }, [jobs, jobQuery]);

  const selectedJob = jobs.find((job) => job.id === selectedJobId);
  const scoreByCandidate = useMemo(() => new Map(matchResults.map((item) => [item.candidate_id, item])), [matchResults]);
  const activeJobCount = jobs.filter((job) => job.status === "active").length;
  const parseFailedCount = candidates.filter((candidate) => candidate.parse_status === "failed").length;
  const taggedCount = candidates.filter((candidate) => candidate.tags.length > 0).length;

  const visibleCandidates = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    const matched = keyword ? candidates.filter((candidate) =>
      [
        candidate.name_masked,
        candidate.title,
        candidate.city,
        candidate.source,
        candidate.owner_name,
        candidate.gender,
        candidate.email_masked,
        candidate.phone_masked,
        candidate.experience_analysis?.label,
        ...candidate.tags.flatMap((tag) => [tag.tag, tag.category])
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    ) : candidates;
    return matched
      .filter((candidate) => !matchResults.length || scoreByCandidate.has(candidate.id))
      .sort((a, b) => {
        const scoreA = matchResults.length ? (scoreByCandidate.get(a.id)?.score || 0) : resumeScore(a.tags);
        const scoreB = matchResults.length ? (scoreByCandidate.get(b.id)?.score || 0) : resumeScore(b.tags);
        return scoreB - scoreA;
      });
  }, [candidates, query, matchResults.length, scoreByCandidate]);
  const pagedCandidates = useClientPagination(visibleCandidates, 20);

  async function runTalentMatch() {
    if (!selectedJobId) {
      setMatchMessage("请先选择一个岗位");
      notify("error", "请先选择一个岗位");
      return;
    }
    setMatchLoading(true);
    setMatchMessage(`正在按「${selectedJob?.title || "当前岗位"}」进行岗位匹配，请稍候...`);
    try {
      const data = await api.matchJob(selectedJobId);
      setMatchResults(data.items);
      const aiReviewed = data.items.filter((item) => item.reason.ai_review?.source === "deepseek").length;
      setMatchMessage(`已按「${data.job.title}」完成综合匹配，AI 已深度复核前 ${aiReviewed} 位，候选人已按综合分排序。`);
      notify("success", `岗位匹配完成，返回 ${data.items.length} 位候选人`);
    } catch (error) {
      const text = error instanceof Error ? error.message : "岗位匹配失败";
      setMatchMessage(text);
      notify("error", text);
    } finally {
      setMatchLoading(false);
    }
  }

  async function addCandidateToPipeline(candidate: Candidate) {
    if (!selectedJobId) {
      setMatchMessage("请先选择一个岗位，再加入流程");
      notify("error", "请先选择一个岗位，再加入流程");
      return;
    }
    try {
      const result = await api.batchPipeline(selectedJobId, {
        candidate_id: candidate.id,
        note: "从人才库加入流程"
      });
      setMatchMessage(result.created.length
        ? `${candidate.name_masked} 已加入「${selectedJob?.title || "当前岗位"}」流程`
        : `${candidate.name_masked} 已在该岗位流程中，无需重复加入`);
      if (!result.created.length) notify("success", "候选人已在该岗位流程中");
    } catch (error) {
      setMatchMessage(error instanceof Error ? error.message : "加入流程失败");
    }
  }

  if (selected) {
    return (
      <CandidateDetailPage
        candidate={selected}
        onBack={() => {
          setSelected(null);
          loadCandidates();
        }}
        onDeleted={() => {
          setSelected(null);
          loadCandidates();
        }}
      />
    );
  }

  return (
    <section className="talent-page" data-testid="page-candidates">
      <aside className="talent-filter">
        <div className="talent-filter-title">
          <BriefcaseBusiness size={16} />
          <span>人才库</span>
        </div>
        <button className="talent-filter-active" onClick={() => setFilter("all")}>
          <Users size={16} />
          全部人才
          <ChevronRight size={16} />
        </button>
        <div className="talent-filter-group">
          <div>任职岗位</div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={16} />
            <input className="input pl-9" value={jobQuery} onChange={(event) => setJobQuery(event.target.value)} placeholder="搜索岗位、城市、技能" />
          </div>
          <select className="select w-full" value={selectedJobId} onChange={(event) => { setSelectedJobId(Number(event.target.value)); setMatchResults([]); setMatchMessage(""); }}>
            <option value={0}>不限岗位</option>
            {filteredJobs.map((job) => (
              <option value={job.id} key={job.id}>
                {job.title} · {job.city || "未填城市"} · {job.status === "active" ? "开放" : "关闭"}
              </option>
            ))}
          </select>
        </div>
        <div className="talent-filter-group">
          <div>应聘职位</div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={16} />
            <input className="input pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="姓名、公司、学校、技能" />
          </div>
        </div>
        <div className="talent-filter-group">
          <div>工作经验</div>
          <div className="talent-experience-grid">
            <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>全部 {candidates.length}</button>
            {stats.map((item) => (
              <button className={filter === item.key ? "active" : ""} key={item.key} onClick={() => setFilter(item.key)}>
                {item.label} {item.count}
              </button>
            ))}
          </div>
        </div>
        <button className="secondary-button w-full" onClick={() => { setFilter("all"); setQuery(""); setJobQuery(""); setMatchResults([]); setMatchMessage(""); notify("success", "筛选已重置"); }}>
          <RefreshCw size={16} />
          重置筛选
        </button>
      </aside>

      <main className="talent-main">
        <div className="talent-toolbar">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={17} />
            <input className="input pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索人才库" />
          </div>
          <button className="secondary-button" onClick={runTalentMatch} disabled={!selectedJobId || matchLoading}>
            <Sparkles size={17} />
            {matchLoading ? "匹配中" : "岗位匹配"}
          </button>
          <button className="secondary-button" data-testid="resume-upload-open" onClick={() => setUploadOpen(true)}>
            <Upload size={17} />
            上传简历
          </button>
          <button className="secondary-button" onClick={() => api.exportCsv("candidates")}>
            <Download size={17} />
            导出人才
          </button>
        </div>

        <div className="talent-title-row">
          <div>
            <h1>人才库概览</h1>
            <p>{selectedJob ? `当前匹配岗位：${selectedJob.title}` : "使用左侧筛选快速定位候选人，选择岗位后可查看 AI 匹配并加入流程。"}</p>
          </div>
          <span>当前显示 {visibleCandidates.length} / {candidates.length} 人</span>
        </div>

        {matchMessage && (
          <div className="talent-match-panel">
            <strong>{matchMessage}</strong>
            <p>规则：简历评分为技能熟练度折算，岗位匹配分为 JD 技能权重 × 候选人技能分，满分均为 100。</p>
          </div>
        )}

        <div className="talent-summary-grid">
          <KpiMini label="候选人总数" value={candidates.length} hint="今日归档 0" />
          <KpiMini label="有标签人才" value={taggedCount} hint={`当前显示 ${visibleCandidates.length} 人`} />
          <KpiMini label="解析异常" value={parseFailedCount} hint="可在详情页重试解析" />
          <KpiMini label="在招岗位" value={activeJobCount} hint="可用于岗位匹配" />
        </div>

        <div className="talent-list-card data-panel">
          <div className="talent-list-head">
            <span>候选人</span>
            <span>画像与标签</span>
            <span>归档与申请</span>
            <span>操作</span>
          </div>
          <div className="data-list talent-data-list">
            {pagedCandidates.items.map((candidate) => (
              <div className="talent-row" key={candidate.id}>
                <div className="talent-person">
                  <div>
                    <h3>{candidate.name_masked}</h3>
                    <p>{candidate.title} · {candidate.city || "城市未识别"}</p>
                    <p>{candidate.email_masked || "-"} · {candidate.phone_masked || "-"}</p>
                  </div>
                </div>
                <div>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="badge muted">简历评分 {resumeScore(candidate.tags)}/100</span>
                    <span className="badge">{candidate.experience_analysis.label}</span>
                    {scoreByCandidate.has(candidate.id) && <span className="badge">匹配 {scoreByCandidate.get(candidate.id)?.score}/100</span>}
                  </div>
                  <TagList tags={candidate.tags} limit={5} compact />
                  {scoreByCandidate.has(candidate.id) && (
                    <p className="mt-2 text-xs text-steel">
                      命中：{scoreByCandidate.get(candidate.id)?.reason.hits.slice(0, 4).map((hit) => hit.candidate_tag).join("、") || "无"}；
                      缺失：{scoreByCandidate.get(candidate.id)?.reason.missing_tags.slice(0, 3).join("、") || "无"}
                    </p>
                  )}
                </div>
                <div className="talent-archive">
                  <p>来源渠道：{candidate.source}</p>
                  <p>目标职位：待分配职位</p>
                  <p>归档人：{candidate.owner_name}</p>
                </div>
                <div className="talent-actions">
                  <button className="secondary-button" onClick={() => setSelected(candidate)}>查看详情</button>
                  <button className="primary-button" onClick={() => addCandidateToPipeline(candidate)}>加入流程</button>
                </div>
              </div>
            ))}
            {visibleCandidates.length === 0 && <EmptyState icon={<Search size={22} />} text="没有匹配的候选人" />}
          </div>
          <PaginationControls total={visibleCandidates.length} limit={pagedCandidates.limit} offset={pagedCandidates.offset} onChange={pagedCandidates.onChange} />
        </div>
      </main>

      {uploadOpen && <UploadResumeModal onClose={() => setUploadOpen(false)} onUploaded={loadCandidates} />}
    </section>
  );
}

function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [matches, setMatches] = useState<MatchResult[]>([]);
  const [preview, setPreview] = useState<MatchResult[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [error, setError] = useState("");
  const [pipelineMessage, setPipelineMessage] = useState("");
  const [query, setQuery] = useState("");

  function load() {
    api.jobs().then((data) => {
      setJobs(data.items);
      setJobId((current) => current ?? data.items[0]?.id ?? null);
    });
  }

  useEffect(load, []);

  useEffect(() => {
    if (!jobId) return;
    setError("");
    api.getJob(jobId).then(setSelectedJob);
    api.matchPreview(jobId, 5).then((data) => setPreview(data.items));
  }, [jobId]);

  async function runMatch() {
    if (!jobId) return;
    setError("");
    try {
      const data = await api.matchJob(jobId);
      setMatches(data.items);
      setSelectedJob(data.job);
      notify("success", `AI 综合匹配已完成，返回 ${data.items.length} 位候选人`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "匹配失败");
    }
  }

  async function addToPipeline(candidateIds: number[]) {
    if (!jobId || !candidateIds.length) return;
    setPipelineMessage("");
    const result = await api.batchPipeline(jobId, {
      candidate_ids: candidateIds,
      stage: "pending",
      note: "从岗位匹配页加入流程"
    });
    setPipelineMessage(`已加入 ${result.created.length} 人，跳过 ${result.skipped.length} 人`);
    if (!result.created.length) notify("success", "候选人已在流程中");
  }

  async function setJobStatus(next: "active" | "closed") {
    if (!selectedJob) return;
    const updated = next === "closed" ? await api.closeJob(selectedJob.id) : await api.restoreJob(selectedJob.id);
    setSelectedJob(updated);
    setJobs(jobs.map((job) => (job.id === updated.id ? updated : job)));
    setMatches([]);
  }

  async function removeJob() {
    if (!selectedJob || !window.confirm(`确认删除岗位「${selectedJob.title}」及其匹配、流程、面试、Offer、BOSS 草稿？`)) return;
    await api.deleteJob(selectedJob.id);
    const nextJobs = jobs.filter((job) => job.id !== selectedJob.id);
    setJobs(nextJobs);
    setSelectedJob(null);
    setMatches([]);
    setPreview([]);
    setJobId(nextJobs[0]?.id ?? null);
  }

  const visibleJobs = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return jobs;
    return jobs.filter((job) =>
      [
        job.title,
        job.city,
        job.department,
        job.job_code,
        job.status,
        job.jd_text,
        job.jd_structured?.skill_tags_raw,
        ...(job.jd_structured?.skills || []).map((skill) => skill.tag)
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    );
  }, [jobs, query]);
  const visibleMatches = useMemo(() => (matches.length ? matches : preview), [matches, preview]);
  const pagedJobs = useClientPagination(visibleJobs, 20);
  const pagedMatches = useClientPagination(visibleMatches, 20);

  if (selectedCandidate) {
    return (
      <CandidateDetailPage
        candidate={selectedCandidate}
        backLabel="返回岗位匹配"
        onBack={() => setSelectedCandidate(null)}
        onDeleted={() => {
          setSelectedCandidate(null);
          setMatches([]);
          setPreview([]);
          load();
        }}
      />
    );
  }

  return (
    <section className="grid gap-5 xl:grid-cols-[380px_1fr]" data-testid="page-jobs">
      <div className="data-panel xl:sticky xl:top-4 xl:self-start">
        <div className="data-panel-head">
          <div>
            <h2>岗位列表</h2>
            <p>共 {visibleJobs.length} 个岗位，列表内滚动查看。</p>
          </div>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={17} />
          <input className="input pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索岗位、技能、城市" />
        </div>
        <button className="primary-button w-full" data-testid="job-create-toggle" onClick={() => { setFormOpen(!formOpen); notify("success", formOpen ? "已收起新建岗位" : "已打开新建岗位"); }}>
          <Plus size={17} />
          新建岗位
        </button>
        {formOpen && <JobForm onCreated={(job) => { setJobs([job, ...jobs]); setJobId(job.id); setFormOpen(false); }} />}
        <div className="data-list" data-testid="job-list">
          {pagedJobs.items.map((job) => (
            <button key={job.id} onClick={() => { setJobId(job.id); notify("success", `已选择岗位：${job.title}`); }} className={`data-row w-full text-left ${jobId === job.id ? "active" : ""}`}>
              <div className="min-w-0">
                <div className="data-row-title">
                  <h3>{job.title}</h3>
                  <span className={`badge ${job.status === "active" ? "" : "muted"}`}>{job.status === "active" ? "开放" : "关闭"}</span>
                </div>
                <p className="data-row-meta">{job.department || "未分部门"} · {job.city || "未填城市"} · {job.job_code || "无编号"}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {(job.jd_structured.skills || []).slice(0, 3).map((skill) => <span className="chip" key={skill.tag}>{skill.tag} {skill.weight}</span>)}
                  {(job.jd_structured.skills || []).length > 3 && <span className="chip muted">+{(job.jd_structured.skills || []).length - 3}</span>}
                </div>
              </div>
            </button>
          ))}
          {visibleJobs.length === 0 && <EmptyState icon={<Search size={22} />} text="没有匹配的岗位" />}
        </div>
        <PaginationControls total={visibleJobs.length} limit={pagedJobs.limit} offset={pagedJobs.offset} onChange={pagedJobs.onChange} />
      </div>
      <div className="space-y-4">
        {selectedJob && (
          <div className="rounded-lg border border-line bg-white p-4 shadow-panel">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-semibold">{selectedJob.title}</h2>
                  <span className={`badge ${selectedJob.status === "active" ? "" : "muted"}`}>{selectedJob.status === "active" ? "开放" : "关闭"}</span>
                </div>
                <p className="mt-1 text-sm text-steel">{selectedJob.department} · {selectedJob.city} · {selectedJob.job_code}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="secondary-button" onClick={() => setJobStatus(selectedJob.status === "active" ? "closed" : "active")}>
                  {selectedJob.status === "active" ? "关闭岗位" : "恢复岗位"}
                </button>
                <button className="secondary-button text-red-700" onClick={removeJob}>
                  <Trash2 size={17} />
                  删除岗位
                </button>
                <button className="secondary-button" onClick={() => api.exportCsv("jobs")}>
                  <Download size={17} />
                  导出岗位
                </button>
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <InfoItem label="要求年限" value={selectedJob.jd_structured.years_required ? `${selectedJob.jd_structured.years_required} 年以上` : "未识别"} />
              <InfoItem label="学历" value={selectedJob.jd_structured.education || "未识别"} />
              <InfoItem label="薪资" value={selectedJob.jd_structured.salary_range ? `${selectedJob.jd_structured.salary_range.min_k}-${selectedJob.jd_structured.salary_range.max_k}K` : "未识别"} />
            </div>
            <div className="mt-4">
              <p className="text-xs font-medium text-steel">岗位技能权重</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {(selectedJob.jd_structured.skills || []).map((skill) => <span className="chip" key={skill.tag}>{skill.tag} · {skill.weight}</span>)}
              </div>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <RequirementList title="关键要求" items={selectedJob.jd_structured.must_have || []} />
              <RequirementList title="加分项" items={selectedJob.jd_structured.nice_to_have || []} />
            </div>
          </div>
        )}
        <div className="toolbar">
          <div>
            <h2 className="font-semibold">匹配结果</h2>
            <p className="text-xs text-steel">预览先按标签规则排序；执行匹配会调用 AI 阅读完整 JD 与简历，并按规则分 35% + AI 分 65% 生成综合分，不做 50 分初筛。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="secondary-button" onClick={() => addToPipeline(visibleMatches.slice(0, 5).map((item) => item.candidate_id))} disabled={!jobId || !visibleMatches.length}>
              <Plus size={17} />
              批量加入前 5
            </button>
            <button className="primary-button" onClick={runMatch} disabled={!jobId || selectedJob?.status === "closed"}>
              <RefreshCw size={17} />
              执行匹配
            </button>
          </div>
        </div>
        {error && <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        {pipelineMessage && <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{pipelineMessage}</div>}
        {visibleMatches.length === 0 ? (
          <EmptyState icon={<Database size={22} />} text="暂无候选人，请先上传简历或调整岗位" />
        ) : (
          <div className="data-panel">
            <div className="data-list">
            {pagedMatches.items.map((match) => (
              <div className="data-row" key={match.id ?? `${match.candidate_id}-${match.score}`}>
                <div className="score-ring">{match.score}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{match.candidate.name_masked}</h3>
                    <span className="badge">{match.candidate.title}</span>
                    <span className="badge muted">规则 {match.reason.rule_score ?? match.score}/100</span>
                    {typeof match.reason.ai_score === "number" && <span className="badge">AI {match.reason.ai_score}/100</span>}
                    {match.reason.ai_review?.recommendation && <span className="badge good">{match.reason.ai_review.recommendation}</span>}
                  </div>
                  {match.reason.ai_review && (
                    <div className="mt-2 rounded-md border border-line bg-slate-50 px-3 py-2 text-xs text-steel">
                      <p className="font-medium text-ink">
                        {match.reason.ai_review.source === "deepseek"
                          ? "AI 综合判断"
                          : match.reason.ai_review.source === "failed" || match.reason.ai_review.source === "ai_unavailable"
                            ? "AI 暂不可用"
                            : "规则匹配"}
                        {match.reason.ai_review.summary ? `：${match.reason.ai_review.summary}` : ""}
                      </p>
                      {(match.reason.ai_review.strengths?.length || match.reason.ai_review.risks?.length || match.reason.ai_review.interview_focus?.length || match.reason.ai_review.evidence?.length || match.reason.ai_review.rule_corrections?.length) ? (
                        <div className="mt-2 grid gap-2 md:grid-cols-3">
                          <p><span className="font-medium text-ink">优势</span>：{match.reason.ai_review.strengths?.slice(0, 3).join("、") || "暂无"}</p>
                          <p><span className="font-medium text-ink">风险</span>：{match.reason.ai_review.risks?.slice(0, 3).join("、") || "暂无"}</p>
                          <p><span className="font-medium text-ink">面试重点</span>：{match.reason.ai_review.interview_focus?.slice(0, 3).join("、") || "暂无"}</p>
                          {match.reason.ai_review.evidence?.length ? <p><span className="font-medium text-ink">AI 证据</span>：{match.reason.ai_review.evidence.slice(0, 3).join("、")}</p> : null}
                          {match.reason.ai_review.rule_corrections?.length ? <p><span className="font-medium text-ink">规则纠偏</span>：{match.reason.ai_review.rule_corrections.slice(0, 3).join("、")}</p> : null}
                        </div>
                      ) : null}
                    </div>
                  )}
                  <div className="mt-3">
                    <div className="flex flex-wrap gap-2">
                      <button className="secondary-button" onClick={() => setSelectedCandidate(match.candidate)}>
                        <FileText size={17} />
                        查看简历
                      </button>
                      <button className="secondary-button" onClick={() => addToPipeline([match.candidate_id])}>
                        <Plus size={17} />
                        加入流程
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    <div>
                      <p className="text-xs font-medium text-steel">命中标签</p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {match.reason.hits.map((hit) => (
                          <span className="chip good" key={`${hit.jd_tag}-${hit.candidate_tag}`}>
                            {hit.jd_tag} / {hit.candidate_tag} · {hit.match_type}
                          </span>
                        ))}
                      </div>
                      {match.reason.hits.some((hit) => hit.evidence?.length) && (
                        <div className="mt-1 grid gap-1">
                          {match.reason.hits.slice(0, 3).map((hit) => hit.evidence?.[0] ? (
                            <p className="truncate text-[11px] text-steel" key={`${hit.jd_tag}-${hit.candidate_tag}-evidence`}>
                              {hit.candidate_tag} 证据：{hit.evidence[0]}
                            </p>
                          ) : null)}
                        </div>
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-medium text-steel">缺失标签</p>
                      <div className="mt-1 flex flex-wrap gap-1.5">
                        {match.reason.missing_tags.length ? match.reason.missing_tags.map((tag) => <span className="chip warn" key={tag}>{tag}</span>) : <span className="chip good">无</span>}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            </div>
            <PaginationControls total={visibleMatches.length} limit={pagedMatches.limit} offset={pagedMatches.offset} onChange={pagedMatches.onChange} />
          </div>
        )}
      </div>
    </section>
  );
}

function JobForm({ onCreated }: { onCreated: (job: Job) => void }) {
  const cities = ["上海", "北京", "深圳", "广州", "杭州", "南京", "苏州", "成都", "武汉", "西安", "远程"];
  const [payload, setPayload] = useState({ title: "", city: "上海", job_code: "", jd_text: "", skill_tags_raw: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    onCreated(await api.createJob(payload));
  }
  async function aiFill(action: "generate" | "calibrate") {
    setBusy(true);
    setMessage(action === "generate" ? "AI 正在生成 JD..." : "AI 正在校准 JD...");
    try {
      const data = action === "generate" ? await api.generateJobJd(payload) : await api.calibrateJobJd(payload);
      setPayload({ ...payload, jd_text: data.jd_text, skill_tags_raw: data.skill_tags_raw });
      setMessage(data.source === "deepseek" ? "DeepSeek 已完成" : "已用本地规则完成");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "AI 处理失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="rounded-lg border border-line bg-white p-4 shadow-panel" data-testid="job-form">
      <label className="field-label">岗位名称</label>
      <input className="input" value={payload.title} onChange={(event) => setPayload({ ...payload, title: event.target.value })} placeholder="例如：Java 后端工程师" />
      <div className="mt-3 grid grid-cols-2 gap-3">
        <select className="select w-full" value={payload.city} onChange={(event) => setPayload({ ...payload, city: event.target.value })}>
          {cities.map((city) => <option value={city} key={city}>{city}</option>)}
        </select>
        <input className="input" value={payload.job_code} onChange={(event) => setPayload({ ...payload, job_code: event.target.value })} placeholder="岗位编号，可不填" />
      </div>
      <label className="field-label mt-3">JD</label>
      <textarea className="input min-h-20" value={payload.jd_text} onChange={(event) => setPayload({ ...payload, jd_text: event.target.value })} />
      <label className="field-label mt-3">技能权重</label>
      <input className="input" value={payload.skill_tags_raw} onChange={(event) => setPayload({ ...payload, skill_tags_raw: event.target.value })} />
      {message && <div className="mt-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</div>}
      <div className="mt-4 grid grid-cols-2 gap-2">
        <button className="secondary-button" type="button" onClick={() => aiFill("generate")} disabled={busy || !payload.title.trim()}>
          <Sparkles size={17} />
          AI 生成 JD
        </button>
        <button className="secondary-button" type="button" onClick={() => aiFill("calibrate")} disabled={busy || (!payload.title.trim() && !payload.jd_text.trim())}>
          <Wrench size={17} />
          AI 校准 JD
        </button>
      </div>
      <button className="primary-button mt-4 w-full" type="submit">
        <Check size={17} />
        保存岗位
      </button>
    </form>
  );
}

function RequirementList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-md border border-line p-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      {items.length ? (
        <ul className="mt-2 space-y-1 text-sm text-steel">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-steel">未识别</p>
      )}
    </div>
  );
}

function PipelinePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState<number | null>(null);
  const [board, setBoard] = useState<{ scope?: string; job_id?: number | null; total?: number; stages: string[]; stage_counts?: Record<string, number>; job_counts?: Record<string, number>; source_counts?: Record<string, number>; columns: Record<string, PipelineItem[]> } | null>(null);
  const [historyTarget, setHistoryTarget] = useState<PipelineItem | null>(null);
  const [history, setHistory] = useState<PipelineItem[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");

  useEffect(() => {
    api.jobs().then((data) => {
      setJobs(data.items);
      setJobId(null);
    });
  }, []);

  useEffect(() => {
    api.pipeline(jobId).then(setBoard);
    setHistoryTarget(null);
    setHistory([]);
  }, [jobId]);

  useEffect(() => {
    const refresh = () => api.pipeline(jobId).then(setBoard).catch(() => undefined);
    const timer = window.setInterval(refresh, 15000);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [jobId]);

  async function loadBoard(silent = false) {
    setBoard(await api.pipeline(jobId));
    if (!silent) notify("success", "流程看板已刷新");
  }

  async function move(item: PipelineItem, stage: string) {
    const note = notes[item.id] || `推进到${stageLabels[stage]}`;
    await api.movePipeline({ candidate_id: item.candidate_id, job_id: item.job_id, stage, note });
    setNotes({ ...notes, [item.id]: "" });
    setMessage(`${item.candidate.name_masked} 已推进到 ${stageLabels[stage]}`);
    await loadBoard(true);
    if (historyTarget?.candidate_id === item.candidate_id) {
      await showHistory(item);
    }
  }

  async function showHistory(item: PipelineItem) {
    setHistoryTarget(item);
    const data = await api.pipelineHistory(item.job_id, item.candidate_id);
    setHistory(data.items);
  }

  function nextStages(stage: string) {
    if (!board) return [];
    const index = board.stages.indexOf(stage);
    const forward = board.stages.slice(index + 1, index + 3);
    return [...forward, "rejected"].filter((value, idx, array) => value !== stage && array.indexOf(value) === idx);
  }

  function visibleItems(stage: string) {
    const keyword = query.trim().toLowerCase();
    return (board?.columns[stage] || []).filter((item) => {
      if (sourceFilter !== "all" && item.source_type !== sourceFilter) return false;
      if (!keyword) return true;
      return [
        item.candidate.name_masked,
        item.candidate.title,
        item.job?.title,
        item.job?.department,
        item.job?.city,
        stageLabels[item.stage] || item.stage,
        item.source_label,
        item.note,
        item.updated_by
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }

  const totals = board?.total ?? (board?.stages.reduce((sum, stage) => sum + (board.columns[stage]?.length || 0), 0) || 0);
  const visibleTotal = board?.stages.reduce((sum, stage) => sum + visibleItems(stage).length, 0) || 0;
  const selectedJob = jobs.find((job) => job.id === jobId);
  const sourceCounts = board?.source_counts || {};

  return (
    <section className="space-y-5">
      <div className="toolbar">
        <div>
          <h2 className="font-semibold">流程看板</h2>
          <p className="text-xs text-steel">{selectedJob ? `当前筛选岗位：${selectedJob.title}` : "默认显示全部招聘岗位"} · 当前显示 {visibleTotal} 人，完整流程 {totals} 人</p>
        </div>
        <select className="select" value={jobId ?? ""} onChange={(event) => setJobId(event.target.value ? Number(event.target.value) : null)}>
          <option value="">全部岗位</option>
          {jobs.map((job) => <option value={job.id} key={job.id}>{job.title}</option>)}
        </select>
        <div className="flex flex-wrap gap-2">
          <select className="select" value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}>
            <option value="all">全部来源</option>
            <option value="interview">面试安排</option>
            <option value="manual">手动流程</option>
            <option value="offer">Offer</option>
            <option value="onboarding">入职</option>
          </select>
          <div className="pipeline-source-summary">
            <span>面试 {sourceCounts.interview || 0}</span>
            <span>手动 {sourceCounts.manual || 0}</span>
            <span>Offer {sourceCounts.offer || 0}</span>
            <span>入职 {sourceCounts.onboarding || 0}</span>
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={17} />
            <input className="input w-56 pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人、岗位、备注" />
          </div>
          <button className="secondary-button" onClick={() => loadBoard()}>
            <RefreshCw size={17} />
            刷新
          </button>
          <button className="secondary-button" onClick={() => api.exportCsv("pipeline")}>
            <Download size={17} />
            导出流程
          </button>
        </div>
      </div>
      {message && <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</div>}
      <div className="space-y-4">
        <div className="pipeline-board">
          {board?.stages.map((stage) => (
            <div key={stage} className="pipeline-column">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold">{stageLabels[stage]}</h3>
                <span className="badge muted">{visibleItems(stage).length}</span>
              </div>
              <div className="pipeline-column-list">
                {visibleItems(stage).map((item) => (
                  <div className="pipeline-card" key={item.id}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="truncate text-xs font-semibold">{item.candidate.name_masked}</div>
                        <div className="mt-0.5 truncate text-xs text-steel">{item.candidate.title} · {item.candidate.experience_analysis?.label || "经验未识别"}</div>
                        <div className="mt-0.5 truncate text-xs text-steel">{item.job?.title || `岗位 ${item.job_id}`}</div>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          <span className={`badge ${item.source_type === "interview" ? "" : "muted"}`}>{item.source_label || "手动流程"}</span>
                          {item.source_status && <span className="badge muted">{item.source_status}</span>}
                          {item.updated_by && <span className="badge muted">{item.updated_by}</span>}
                        </div>
                      </div>
                      <button className="icon-button h-7 w-7" title="流程历史" onClick={() => showHistory(item)}>
                        <Clock3 size={15} />
                      </button>
                    </div>
                    <TagList tags={item.candidate.tags.slice(0, 3)} />
                    <input
                      className="input pipeline-note-input mt-2"
                      placeholder="推进备注"
                      value={notes[item.id] || ""}
                      onChange={(event) => setNotes({ ...notes, [item.id]: event.target.value })}
                    />
                    <div className="pipeline-card-actions">
                      {nextStages(stage).map((next) => (
                        <button className={next === "rejected" ? "secondary-button text-red-700" : "secondary-button"} key={next} onClick={() => move(item, next)}>
                          {stageLabels[next]}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                {visibleItems(stage).length === 0 && <div className="rounded-md border border-dashed border-line bg-slate-50 px-3 py-6 text-center text-xs text-steel">暂无候选人</div>}
              </div>
            </div>
          ))}
        </div>
        {historyTarget && <PipelineHistoryPanel target={historyTarget} history={history} onClose={() => setHistoryTarget(null)} />}
      </div>
    </section>
  );
}

function PipelineHistoryPanel({ target, history, onClose }: { target: PipelineItem | null; history: PipelineItem[]; onClose: () => void }) {
  if (!target) {
    return (
      <aside className="rounded-lg border border-line bg-white p-5 shadow-panel">
        <h3 className="font-semibold">流程历史</h3>
        <p className="mt-3 text-sm text-steel">点击候选人卡片上的时钟查看完整阶段记录。</p>
      </aside>
    );
  }
  return (
    <aside className="rounded-lg border border-line bg-white p-5 shadow-panel">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{target.candidate.name_masked}</h3>
          <p className="mt-1 text-xs text-steel">{target.candidate.title} · {target.job?.title || `岗位 ${target.job_id}`}</p>
        </div>
        <button className="secondary-button" onClick={onClose}>关闭</button>
      </div>
      <div className="mt-5 space-y-3">
        {history.map((item) => (
          <div className="border-l-2 border-mint pl-3" key={item.id}>
            <div className="flex items-center gap-2">
              <span className="badge">{stageLabels[item.stage]}</span>
              <span className="text-xs text-steel">{item.updated_by}</span>
            </div>
            <p className="mt-1 text-sm text-steel">{item.note || "无备注"}</p>
            <p className="mt-1 text-xs text-steel">{formatDateTime(item.ts)}</p>
          </div>
        ))}
      </div>
    </aside>
  );
}

function InterviewsPage() {
  const [assignments, setAssignments] = useState<InterviewAssignment[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [interviewers, setInterviewers] = useState<User[]>([]);
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState<InterviewAssignment | null>(null);
  const [aiInterview, setAiInterview] = useState<InterviewAssignment | null>(null);
  const [resultAssignment, setResultAssignment] = useState<InterviewAssignment | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    candidate_id: 0,
    job_id: 0,
    interviewer_id: 0,
    round: "interview_first",
    scheduled_at: "",
    location: "腾讯会议",
    note: ""
  });

  async function load(silent = false) {
    const [assignmentData, jobData, candidateData, interviewerData] = await Promise.all([
      api.interviewAssignments(),
      api.jobs(),
      api.candidates(),
      api.interviewers()
    ]);
    setAssignments(assignmentData.items);
    setJobs(jobData.items);
    setCandidates(candidateData.items);
    setInterviewers(interviewerData.items);
    setForm((current) => ({
      ...current,
      candidate_id: current.candidate_id || candidateData.items[0]?.id || 0,
      job_id: current.job_id || jobData.items[0]?.id || 0,
      interviewer_id: current.interviewer_id || interviewerData.items[0]?.id || 0,
      scheduled_at: current.scheduled_at || defaultDateTimeLocal()
    }));
    if (!silent) notify("success", "面试安排已刷新");
  }

  useEffect(() => {
    load(true);
  }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      const created = await api.createInterviewAssignment(form);
      setAssignments([created, ...assignments]);
      setMessage("面试已安排，并已同步推进流程阶段");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "面试安排失败");
    } finally {
      setBusy(false);
    }
  }

  async function cancelAssignment(assignment: InterviewAssignment) {
    const updated = await api.cancelInterviewAssignment(assignment.id);
    setAssignments(assignments.map((item) => (item.id === updated.id ? updated : item)));
    setMessage("面试已取消");
  }

  async function editAssignment(assignment: InterviewAssignment) {
    const location = window.prompt("修改地点/会议链接", assignment.location || "");
    if (location === null) return;
    const updated = await api.updateInterviewAssignment(assignment.id, { location });
    setAssignments(assignments.map((item) => (item.id === updated.id ? updated : item)));
    setMessage("面试安排已更新");
  }

  async function removeAssignment(assignment: InterviewAssignment) {
    if (!window.confirm(`确认删除 ${assignment.candidate.name_masked} 的面试安排？`)) return;
    await api.deleteInterviewAssignment(assignment.id);
    setAssignments(assignments.filter((item) => item.id !== assignment.id));
    setMessage("面试安排已删除");
  }

  async function copyRoomLink(assignment: InterviewAssignment) {
    const data = await api.interviewRoomLink(assignment.id);
    const copied = await copyTextToClipboard(data.url);
    if (copied) {
      notify("success", "候选人面试间链接已复制");
      return;
    }
    window.prompt("请手动复制候选人面试间链接", data.url);
    notify("error", "浏览器限制自动复制，请手动复制");
  }

  const visibleAssignments = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return assignments.filter((assignment) => {
      if (status !== "all" && assignment.status !== status) return false;
      if (!keyword) return true;
      return [
        assignment.candidate.name_masked,
        assignment.candidate.title,
        assignment.job.title,
        assignment.interviewer.name,
        stageLabels[assignment.round] || assignment.round,
        assignment.location,
        assignment.note,
        assignment.status
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [assignments, query, status]);
  const pagedAssignments = useClientPagination(visibleAssignments, 20);

  return (
    <section className="grid gap-5 xl:grid-cols-[380px_1fr]">
      <form onSubmit={create} className="rounded-lg border border-line bg-white p-5 shadow-panel">
        <h2 className="font-semibold">安排面试</h2>
        <label className="field-label mt-4">候选人</label>
        <select className="select w-full" value={form.candidate_id} onChange={(event) => setForm({ ...form, candidate_id: Number(event.target.value) })}>
          {candidates.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.name_masked} · {candidate.title}</option>)}
        </select>
        <label className="field-label mt-3">岗位</label>
        <select className="select w-full" value={form.job_id} onChange={(event) => setForm({ ...form, job_id: Number(event.target.value) })}>
          {jobs.map((job) => <option value={job.id} key={job.id}>{job.title}</option>)}
        </select>
        <label className="field-label mt-3">面试官</label>
        <select className="select w-full" value={form.interviewer_id} onChange={(event) => setForm({ ...form, interviewer_id: Number(event.target.value) })}>
          {interviewers.map((interviewer) => <option value={interviewer.id} key={interviewer.id}>{interviewer.name} · {interviewer.role}</option>)}
        </select>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label className="field-label">轮次</label>
            <select className="select w-full" value={form.round} onChange={(event) => setForm({ ...form, round: event.target.value })}>
              <option value="interview_first">一面</option>
              <option value="interview_second">二面</option>
              <option value="interview_final">终面</option>
            </select>
          </div>
          <div>
            <label className="field-label">时间</label>
            <input className="input" type="datetime-local" value={form.scheduled_at} onChange={(event) => setForm({ ...form, scheduled_at: event.target.value })} />
          </div>
        </div>
        <label className="field-label mt-3">地点/会议链接</label>
        <input className="input" value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} />
        <label className="field-label mt-3">备注</label>
        <textarea className="input min-h-20" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
        <button className="primary-button mt-4 w-full" type="submit" disabled={busy || !form.candidate_id || !form.job_id || !form.interviewer_id}>
          <CalendarDays size={17} />
          {busy ? "安排中" : "安排面试"}
        </button>
        {message && <p className="mt-3 text-sm text-mint">{message}</p>}
      </form>

      <div className="space-y-4">
        <div className="toolbar">
          <div>
            <h2 className="font-semibold">面试安排</h2>
            <p className="text-xs text-steel">安排后会同步推进到对应面试阶段，反馈提交后继续推进流程。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={17} />
              <input className="input w-56 pl-9" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索候选人、岗位、面试官" />
            </div>
            <select className="select" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="all">全部状态</option>
              <option value="scheduled">待反馈</option>
              <option value="completed">已反馈</option>
              <option value="cancelled">已取消</option>
            </select>
            <button className="secondary-button" onClick={() => load()}>
              <RefreshCw size={17} />
              刷新
            </button>
            <button className="secondary-button" onClick={() => api.exportCsv("interviews")}>
              <Download size={17} />
              导出面试
            </button>
          </div>
        </div>
        <div className="data-panel">
          <div className="data-panel-head">
            <div>
              <h2>面试列表</h2>
              <p>当前筛选 {visibleAssignments.length} 条，默认分页显示。</p>
            </div>
          </div>
          <div className="data-list">
          {pagedAssignments.items.map((assignment) => (
            <div className="data-row flex-col items-stretch sm:flex-row sm:items-center" key={assignment.id}>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{assignment.candidate.name_masked}</h3>
                  <span className="badge">{stageLabels[assignment.round] || assignment.round}</span>
                  <span className={`badge ${assignment.status === "completed" ? "" : "muted"}`}>{assignment.status === "completed" ? "已反馈" : assignment.status === "cancelled" ? "已取消" : "待反馈"}</span>
                </div>
                <p className="mt-1 text-sm text-steel">{assignment.job.title} · {assignment.interviewer.name} · {formatDateTime(assignment.scheduled_at)}</p>
                <p className="mt-2 text-sm text-steel">{assignment.location || "未填写地点"}</p>
              </div>
              <div className="flex flex-wrap justify-start gap-2 sm:justify-end">
                <button className="secondary-button" onClick={() => setResultAssignment(assignment)} disabled={assignment.status !== "completed"}>
                  查看结果
                </button>
                {assignment.status === "scheduled" && (
                  <>
                    <button className="secondary-button" onClick={() => setSelected(assignment)}>
                      提交反馈
                    </button>
                    <button className="secondary-button" onClick={() => setAiInterview(assignment)} title="后台预览 AI 面试题和模拟问答，不是候选人入口">
                      <Bot size={17} />
                      面试官预览
                    </button>
                    <button className="secondary-button" onClick={() => copyRoomLink(assignment)}>
                      复制面试间
                    </button>
                    <button className="secondary-button" onClick={() => editAssignment(assignment)}>编辑</button>
                    <button className="secondary-button" onClick={() => cancelAssignment(assignment)}>取消</button>
                  </>
                )}
                <button className="secondary-button text-red-700" onClick={() => removeAssignment(assignment)}>
                  <Trash2 size={17} />
                  删除
                </button>
              </div>
            </div>
          ))}
          {visibleAssignments.length === 0 && <EmptyState icon={<Search size={22} />} text="没有匹配的面试安排" />}
          </div>
          <PaginationControls total={visibleAssignments.length} limit={pagedAssignments.limit} offset={pagedAssignments.offset} onChange={pagedAssignments.onChange} />
        </div>
      </div>
      {selected && <FeedbackModal assignment={selected} onClose={() => setSelected(null)} onSubmitted={() => { setSelected(null); load(); }} />}
      {aiInterview && <AiInterviewModal assignment={aiInterview} onClose={() => setAiInterview(null)} />}
      {resultAssignment && <InterviewResultModal assignment={resultAssignment} onClose={() => setResultAssignment(null)} />}
    </section>
  );
}

function InterviewResultModal({ assignment, onClose }: { assignment: InterviewAssignment; onClose: () => void }) {
  const [feedback, setFeedback] = useState<InterviewFeedback | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.interviewFeedback(assignment.id)
      .then((data) => setFeedback(data.items[0] || null))
      .catch((err) => setError(err instanceof Error ? err.message : "面试结果加载失败"));
  }, [assignment.id]);

  const scoreMatch = feedback?.comment?.match(/AI评分：(\d+)\/100/);
  const score = scoreMatch?.[1] || (feedback ? String(feedback.rating * 20) : "");
  const dimensions = parseInterviewDimensions(feedback?.comment || "");

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/20 p-4" onClick={onClose}>
      <div className="max-h-[88vh] w-full max-w-3xl overflow-auto rounded-lg border border-line bg-white p-5 shadow-panel" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">AI 面试结果</h2>
            <p className="mt-1 text-sm text-steel">{assignment.candidate.name_masked} · {assignment.job.title} · {stageLabels[assignment.round]}</p>
          </div>
          <div className="flex gap-2">
            {feedback && (
              <button className="secondary-button" onClick={() => api.interviewReport(assignment.id)}>
                <Download size={17} /> 导出报告
              </button>
            )}
            <button className="secondary-button" onClick={onClose}>关闭</button>
          </div>
        </div>
        {error && <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        {!feedback ? (
          <div className="py-8 text-center text-sm text-steel">正在加载面试结果...</div>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <InfoItem label="AI评分" value={`${score}/100`} />
              <InfoItem label="面试官评分" value={`${feedback.rating}/5`} />
              <InfoItem label="结论" value={feedback.decision === "pass" ? "通过" : feedback.decision === "reject" ? "淘汰" : "待定"} />
            </div>
            {dimensions.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-5">
                {dimensions.map((item) => <InfoItem label={item.label} value={`${item.value}/100`} key={item.label} />)}
              </div>
            )}
            <div className="rounded-lg border border-line p-4">
              <p className="text-xs font-medium text-steel">优势</p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-ink">{feedback.strengths || "暂无"}</p>
            </div>
            <div className="rounded-lg border border-line p-4">
              <p className="text-xs font-medium text-steel">风险</p>
              <p className="mt-2 whitespace-pre-wrap text-sm text-ink">{feedback.risks || "暂无"}</p>
            </div>
            <div className="rounded-lg border border-line p-4">
              <p className="text-xs font-medium text-steel">面试内容</p>
              <pre className="mt-2 whitespace-pre-wrap text-sm leading-7 text-ink">{feedback.comment || "暂无记录"}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AiInterviewModal({ assignment, onClose }: { assignment: InterviewAssignment; onClose: () => void }) {
  const [plan, setPlan] = useState<AiInterviewPlan | null>(null);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<string[]>([]);
  const [auto, setAuto] = useState(false);
  const [error, setError] = useState("");
  const current = plan?.questions[index];

  useEffect(() => {
    setError("");
    api.interviewAiPlan(assignment.id)
      .then((data) => {
        setPlan(data);
        setAnswers(Array(data.questions.length).fill(""));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "AI 面试方案生成失败"));
    return () => window.speechSynthesis?.cancel();
  }, [assignment.id]);

  function speak(text: string) {
    window.speechSynthesis?.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "zh-CN";
    window.speechSynthesis?.speak(utterance);
  }

  function startAuto() {
    if (!plan) return;
    setAuto(true);
    speak(`${plan.opening}。第 ${index + 1} 题，${current?.question || ""}`);
  }

  function next() {
    if (!plan) return;
    const nextIndex = Math.min(index + 1, plan.questions.length - 1);
    setIndex(nextIndex);
    if (auto) speak(`第 ${nextIndex + 1} 题，${plan.questions[nextIndex].question}`);
  }

  const answered = answers.filter((item) => item.trim()).length;
  const score = plan?.questions.length ? Math.round((answered / plan.questions.length) * 100) : 0;

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/20 p-4" onClick={onClose}>
      <div className="w-full max-w-4xl rounded-lg border border-line bg-white p-5 shadow-panel" onClick={(event) => event.stopPropagation()}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="font-semibold">AI 模拟人面试</h2>
            <p className="mt-1 text-sm text-steel">{assignment.candidate.name_masked} · {assignment.job.title} · {stageLabels[assignment.round]}</p>
          </div>
          <button className="secondary-button" onClick={onClose}>关闭</button>
        </div>
        {error ? (
          <div className="mt-5 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
        ) : !plan ? (
          <div className="py-10 text-center text-sm text-steel">正在生成 AI 面试方案...</div>
        ) : (
          <div className="mt-5 grid gap-4 lg:grid-cols-[260px_1fr]">
            <aside className="rounded-lg border border-line bg-slate-50 p-4">
              <div className="grid place-items-center">
                <div className="grid h-20 w-20 place-items-center rounded-full bg-blue-50 text-mint">
                  <Bot size={36} />
                </div>
                <h3 className="mt-3 font-semibold">{plan.avatar.name}</h3>
                <p className="text-xs text-steel">{plan.avatar.role} · {plan.source === "deepseek" ? "AI 已生成" : "本地兜底"}</p>
              </div>
              <div className="mt-4 rounded-md bg-white p-3 text-xs text-steel">
                <div className="font-medium text-ink">{plan.meeting.provider}</div>
                <div className="mt-1">{plan.meeting.location}</div>
                <div className="mt-2">{plan.meeting.note}</div>
              </div>
              <button className="primary-button mt-4 w-full" onClick={startAuto}>
                <Sparkles size={17} />
                开始自动提问
              </button>
              <div className="mt-3 text-center text-xs text-steel">完成度 {score}/100</div>
            </aside>
            <main className="min-w-0">
              <p className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-800">{plan.opening}</p>
              <div className="mt-4 rounded-lg border border-line p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="badge">{current?.type}</span>
                  <span className="text-xs text-steel">第 {index + 1} / {plan.questions.length} 题</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold">{current?.question}</h3>
                <p className="mt-2 text-sm text-steel">评分点：{current?.rubric}</p>
                <textarea
                  className="input mt-4 min-h-32"
                  value={answers[index] || ""}
                  onChange={(event) => setAnswers(answers.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}
                  placeholder="候选人回答记录"
                />
                <div className="mt-4 flex flex-wrap justify-between gap-2">
                  <button className="secondary-button" onClick={() => speak(current?.question || "")}>重播问题</button>
                  <div className="flex gap-2">
                    <button className="secondary-button" onClick={() => setIndex(Math.max(index - 1, 0))} disabled={index === 0}>上一题</button>
                    <button className="primary-button" onClick={next} disabled={index >= plan.questions.length - 1}>下一题</button>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5">
                {plan.rubric.map((item) => <span className="chip" key={item}>{item}</span>)}
              </div>
              {answered === plan.questions.length && <p className="mt-4 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">{plan.closing}</p>}
            </main>
          </div>
        )}
      </div>
    </div>
  );
}

function FeedbackModal({ assignment, onClose, onSubmitted }: { assignment: InterviewAssignment; onClose: () => void; onSubmitted: () => void }) {
  const [form, setForm] = useState({ rating: 4, decision: "pass", strengths: "", risks: "", comment: "" });
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    await api.submitInterviewFeedback({ assignment_id: assignment.id, ...form });
    setBusy(false);
    onSubmitted();
  }

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/20 p-4" onClick={onClose}>
      <form className="w-full max-w-2xl rounded-lg border border-line bg-white p-5 shadow-panel" onSubmit={submit} onClick={(event) => event.stopPropagation()}>
        <h2 className="font-semibold">面试反馈</h2>
        <p className="mt-1 text-sm text-steel">{assignment.candidate.name_masked} · {assignment.job.title} · {stageLabels[assignment.round]}</p>
        <div className="mt-4 grid grid-cols-2 gap-3">
          <div>
            <label className="field-label">评分</label>
            <input className="input" type="number" min={1} max={5} value={form.rating} onChange={(event) => setForm({ ...form, rating: Number(event.target.value) })} />
          </div>
          <div>
            <label className="field-label">结论</label>
            <select className="select w-full" value={form.decision} onChange={(event) => setForm({ ...form, decision: event.target.value })}>
              <option value="pass">通过</option>
              <option value="hold">待定</option>
              <option value="reject">淘汰</option>
            </select>
          </div>
        </div>
        <label className="field-label mt-3">优势</label>
        <textarea className="input min-h-20" value={form.strengths} onChange={(event) => setForm({ ...form, strengths: event.target.value })} />
        <label className="field-label mt-3">风险</label>
        <textarea className="input min-h-20" value={form.risks} onChange={(event) => setForm({ ...form, risks: event.target.value })} />
        <label className="field-label mt-3">综合评价</label>
        <textarea className="input min-h-24" value={form.comment} onChange={(event) => setForm({ ...form, comment: event.target.value })} />
        <div className="mt-5 flex justify-end gap-3">
          <button className="secondary-button" type="button" onClick={onClose}>关闭</button>
          <button className="primary-button" type="submit" disabled={busy}>
            <Check size={17} />
            提交反馈
          </button>
        </div>
      </form>
    </div>
  );
}

function OffersPage() {
  const [offers, setOffers] = useState<OfferRecord[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [filter, setFilter] = useState("all");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    candidate_id: 0,
    job_id: 0,
    salary_min_k: "18",
    salary_max_k: "25",
    salary_months: "13",
    city: "",
    start_date: defaultDate(),
    status: "draft",
    note: ""
  });

  async function load(silent = false) {
    const [offerData, jobData, candidateData] = await Promise.all([api.offers(filter), api.jobs(), api.candidates()]);
    setOffers(offerData.items);
    setJobs(jobData.items);
    setCandidates(candidateData.items);
    setForm((current) => ({
      ...current,
      candidate_id: current.candidate_id || candidateData.items[0]?.id || 0,
      job_id: current.job_id || jobData.items[0]?.id || 0,
      city: current.city || jobData.items[0]?.city || ""
    }));
    if (!silent) notify("success", "Offer 台账已刷新");
  }

  useEffect(() => {
    load(true);
  }, [filter]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      const created = await api.createOffer(form);
      setOffers([created, ...offers]);
      setMessage("Offer 已创建，并已同步到流程看板");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Offer 创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function setOfferStatus(offer: OfferRecord, status: string) {
    const updated = await api.updateOffer(offer.id, { status });
    setOffers(offers.map((item) => (item.id === updated.id ? updated : item)));
    setMessage(`Offer 状态已更新为：${offerStatusLabels[status]}`);
  }

  async function editOffer(offer: OfferRecord) {
    const note = window.prompt("修改 Offer 备注", offer.note || "");
    if (note === null) return;
    const updated = await api.updateOffer(offer.id, { note });
    setOffers(offers.map((item) => (item.id === updated.id ? updated : item)));
    setMessage("Offer 已更新");
  }

  async function removeOffer(offer: OfferRecord) {
    if (!window.confirm(`确认删除 ${offer.candidate.name_masked} 的 Offer？`)) return;
    await api.deleteOffer(offer.id);
    setOffers(offers.filter((item) => item.id !== offer.id));
    setMessage("Offer 已删除");
  }
  const pagedOffers = useClientPagination(offers, 20);

  return (
    <section className="grid gap-5 xl:grid-cols-[380px_1fr]">
      <form onSubmit={create} className="rounded-lg border border-line bg-white p-5 shadow-panel">
        <h2 className="font-semibold">创建 Offer</h2>
        <label className="field-label mt-4">候选人</label>
        <select className="select w-full" value={form.candidate_id} onChange={(event) => setForm({ ...form, candidate_id: Number(event.target.value) })}>
          {candidates.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.name_masked} · {candidate.title}</option>)}
        </select>
        <label className="field-label mt-3">岗位</label>
        <select className="select w-full" value={form.job_id} onChange={(event) => {
          const job = jobs.find((item) => item.id === Number(event.target.value));
          setForm({ ...form, job_id: Number(event.target.value), city: job?.city || form.city });
        }}>
          {jobs.map((job) => <option value={job.id} key={job.id}>{job.title}</option>)}
        </select>
        <div className="mt-3 grid grid-cols-3 gap-3">
          <div>
            <label className="field-label">最低月薪 K</label>
            <input className="input" value={form.salary_min_k} onChange={(event) => setForm({ ...form, salary_min_k: event.target.value })} />
          </div>
          <div>
            <label className="field-label">最高月薪 K</label>
            <input className="input" value={form.salary_max_k} onChange={(event) => setForm({ ...form, salary_max_k: event.target.value })} />
          </div>
          <div>
            <label className="field-label">薪资月数</label>
            <input className="input" value={form.salary_months} onChange={(event) => setForm({ ...form, salary_months: event.target.value })} />
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <label className="field-label">城市</label>
            <input className="input" value={form.city} onChange={(event) => setForm({ ...form, city: event.target.value })} />
          </div>
          <div>
            <label className="field-label">预计入职</label>
            <input className="input" type="date" value={form.start_date} onChange={(event) => setForm({ ...form, start_date: event.target.value })} />
          </div>
        </div>
        <label className="field-label mt-3">状态</label>
        <select className="select w-full" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}>
          {Object.entries(offerStatusLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
        </select>
        <label className="field-label mt-3">备注</label>
        <textarea className="input min-h-20" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} />
        <button className="primary-button mt-4 w-full" type="submit" disabled={busy || !form.candidate_id || !form.job_id}>
          <HandCoins size={17} />
          {busy ? "创建中" : "创建 Offer"}
        </button>
        {message && <p className="mt-3 text-sm text-mint">{message}</p>}
      </form>

      <div className="space-y-4">
        <div className="toolbar">
          <div>
            <h2 className="font-semibold">Offer 台账</h2>
            <p className="text-xs text-steel">创建、发放、接受或拒绝都会写入流程历史，接受后进入入职阶段。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select className="select" value={filter} onChange={(event) => setFilter(event.target.value)}>
              <option value="all">全部状态</option>
              {Object.entries(offerStatusLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
            </select>
            <button className="secondary-button" onClick={() => load()}>
              <RefreshCw size={17} />
              刷新
            </button>
            <button className="secondary-button" onClick={() => api.exportCsv("offers")}>
              <Download size={17} />
              导出 Offer
            </button>
          </div>
        </div>
        {offers.length === 0 ? (
          <EmptyState icon={<HandCoins size={22} />} text="暂无 Offer 记录" />
        ) : (
          <div className="data-panel">
            <div className="data-panel-head">
              <div>
                <h2>Offer 列表</h2>
                <p>共 {offers.length} 条记录。</p>
              </div>
            </div>
            <div className="data-list">
            {pagedOffers.items.map((offer) => (
              <div className="data-row" key={offer.id}>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{offer.candidate.name_masked}</h3>
                    <span className="badge">{offerStatusLabels[offer.status] || offer.status}</span>
                    <span className="badge muted">{offer.job.title}</span>
                  </div>
                  <p className="mt-1 text-sm text-steel">{offer.city || offer.job.city} · {formatSalary(offer)} · 预计入职 {offer.start_date || "待定"}</p>
                  <p className="mt-2 text-sm text-steel">{offer.note || "无备注"}</p>
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-2">
                  <button className="secondary-button" onClick={() => setOfferStatus(offer, "sent")} disabled={offer.status === "sent" || offer.status === "accepted"}>
                    已发放
                  </button>
                  <button className="secondary-button" onClick={() => setOfferStatus(offer, "accepted")} disabled={offer.status === "accepted"}>
                    已接受
                  </button>
                  <button className="secondary-button" onClick={() => setOfferStatus(offer, "declined")} disabled={offer.status === "declined"}>
                    已拒绝
                  </button>
                  <button className="secondary-button" onClick={() => setOfferStatus(offer, "cancelled")} disabled={offer.status === "cancelled" || offer.status === "accepted"}>
                    取消
                  </button>
                  <button className="secondary-button" onClick={() => editOffer(offer)}>
                    编辑
                  </button>
                  <button className="secondary-button" onClick={() => api.offerLetter(offer.id)}>
                    <Download size={17} />
                    导出确认函
                  </button>
                  <button className="secondary-button text-red-700" onClick={() => removeOffer(offer)}>
                    <Trash2 size={17} />
                    删除
                  </button>
                </div>
              </div>
            ))}
            </div>
            <PaginationControls total={offers.length} limit={pagedOffers.limit} offset={pagedOffers.offset} onChange={pagedOffers.onChange} />
          </div>
        )}
      </div>
    </section>
  );
}

function BossPage() {
  const [status, setStatus] = useState<{
    cookie_bound: boolean;
    account: string;
    mode: string;
    can_auto_send: boolean;
    verified?: boolean;
    account_id?: number | null;
    candidate_count?: number;
    job_count?: number;
    last_candidate_at?: string | null;
    last_job_at?: string | null;
  } | null>(null);
  const [tab, setTab] = useState<"inbox" | "recommend" | "jobs">("inbox");
  const [inbox, setInbox] = useState<BossInboxItem[]>([]);
  const [inboxQuery, setInboxQuery] = useState("");
  const [message, setMessage] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [recommendations, setRecommendations] = useState<MatchResult[]>([]);
  const [candidateId, setCandidateId] = useState(0);
  const [jobId, setJobId] = useState(0);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  async function load(silent = false) {
    setRefreshing(true);
    try {
      const [statusData, inboxData, jobData] = await Promise.all([
        api.bossStatus(),
        api.bossInbox(),
        api.bossJobs()
      ]);
      setStatus(statusData);
      setInbox(inboxData.items);
      setJobs(jobData.items);
      setCandidateId((current) => current || inboxData.items.find((item) => item.candidate_id)?.candidate_id || 0);
      setJobId((current) => current || jobData.items[0]?.id || 0);
      if (!silent) notify("success", "BOSS 数据已刷新");
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load(true);
  }, []);

  useEffect(() => {
    if (!jobId) {
      setRecommendations([]);
      return;
    }
    api.bossJobRecommendations(jobId, 8).then((data) => setRecommendations(data.items));
  }, [jobId]);

  const visibleInbox = inbox.filter((item) => [item.name, item.title, item.summary].join(" ").toLowerCase().includes(inboxQuery.trim().toLowerCase()));
  const pagedInbox = useClientPagination(visibleInbox, 20);
  const pagedRecommendations = useClientPagination(recommendations, 20);
  const pagedBossJobs = useClientPagination(jobs, 20);
  const selectedJob = jobs.find((job) => job.id === jobId);
  const syncTimes = [status?.last_candidate_at, status?.last_job_at].filter((value): value is string => Boolean(value)).sort();
  const lastSyncAt = syncTimes[syncTimes.length - 1];
  const lastSyncText = lastSyncAt ? new Date(lastSyncAt).toLocaleString("zh-CN", { hour12: false }) : "暂无同步";

  async function runAiScreen() {
    if (!candidateId || !jobId) return;
    const data = await api.bossAiScreen({ job_id: jobId, candidate_ids: [candidateId] });
    setMessage(`AI 初筛已写入流程 ${data.created.length} 人，跳过 ${data.skipped.length} 人`);
  }

  async function openCandidate(candidateId?: number) {
    if (!candidateId) return;
    const candidate = await api.getCandidate(candidateId);
    setSelectedCandidate(candidate);
  }

  async function verifyBoss() {
    if (!status?.account_id) return;
    const data = await api.verifyBossAccount(status.account_id);
    setStatus({ ...status, verified: data.account.verified });
    setMessage(data.account.verified ? "BOSS 登录态校验通过" : "BOSS 登录态待重新绑定");
  }

  async function copyPluginToken() {
    const value = localStorage.getItem("hireinsight_token") || "";
    const copied = await copyTextToClipboard(value);
    if (copied) {
      setMessage("插件 Token 已复制，请粘贴到 Chrome 扩展中");
      notify("success", "插件 Token 已复制");
      return;
    }
    window.prompt("请手动复制插件 Token", value);
    setMessage("浏览器限制自动复制，请手动复制插件 Token");
    notify("error", "浏览器限制自动复制，请手动复制");
  }

  function openBoss() {
    window.open("https://www.zhipin.com/web/geek/chat", "_blank", "noopener,noreferrer");
    notify("success", "已打开 BOSS 页面");
  }

  function switchBossTab(next: typeof tab) {
    setTab(next);
  }

  function selectJob(job: Job, nextTab?: "recommend") {
    setJobId(job.id);
    if (nextTab) setTab(nextTab);
    setMessage(nextTab ? `已切换到「${job.title}」的推荐候选人` : `已选择岗位：${job.title}`);
  }

  if (selectedCandidate) {
    return (
      <CandidateDetailPage
        candidate={selectedCandidate}
        onBack={() => setSelectedCandidate(null)}
        onDeleted={() => {
          setSelectedCandidate(null);
          load(true);
        }}
      />
    );
  }

  return (
    <section className="design-page">
      <div className="design-title">
        <h1>BOSS 直聘</h1>
        <p>扫码登录即用：收件箱闭环、推荐候选人、查看/下载简历、岗位列表。</p>
      </div>

      <div className="boss-status-bar">
        <div className="flex flex-wrap items-center gap-3">
          <span className="status-pill">{status?.cookie_bound ? "已激活" : "未激活"}</span>
          <span>账号 {status?.account || "-"}</span>
          <span className="text-sm text-steel">{status?.mode || "-"} · {status?.verified ? "已校验" : "待校验"} · 自动发送{status?.can_auto_send ? "允许" : "禁止"}</span>
          <span className="badge muted">候选人 {status?.candidate_count ?? inbox.length}</span>
          <span className="badge muted">岗位 {status?.job_count ?? jobs.length}</span>
          <span className="text-sm text-steel">最近同步 {lastSyncText}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="secondary-button" onClick={() => api.bossExtension()}>
            <Download size={17} />
            下载插件
          </button>
          <button className="secondary-button" onClick={copyPluginToken}>复制插件 Token</button>
          <button className="secondary-button" onClick={verifyBoss} disabled={!status?.account_id}>校验登录态</button>
          <button className="black-button" onClick={openBoss}>打开 BOSS</button>
        </div>
      </div>

      <div className="boss-tabs">
        <button className={tab === "inbox" ? "active" : ""} onClick={() => switchBossTab("inbox")}>收件箱闭环</button>
        <button className={tab === "recommend" ? "active" : ""} onClick={() => switchBossTab("recommend")}>推荐候选人</button>
        <button className={tab === "jobs" ? "active" : ""} onClick={() => switchBossTab("jobs")}>岗位列表</button>
      </div>

      <div className="grid gap-4">
        <div className="space-y-4">
          {tab !== "jobs" && <div className="design-card">
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <label className="field-label">BOSS 岗位</label>
                <select className="select w-full" value={jobId} onChange={(event) => setJobId(Number(event.target.value))}>
                  {jobs.map((job) => <option value={job.id} key={job.id}>{job.title}</option>)}
                </select>
              </div>
              <div>
                <label className="field-label">BOSS 候选人</label>
                <select className="select w-full" value={candidateId} onChange={(event) => setCandidateId(Number(event.target.value))}>
                  {inbox.filter((item) => item.candidate_id).map((item) => <option value={item.candidate_id} key={item.candidate_id}>{item.name} · {item.title}</option>)}
                </select>
              </div>
            </div>
            <button className="secondary-button mt-4" onClick={runAiScreen} disabled={!candidateId || !jobId}>
              <Check size={17} />
              AI 初筛入流程
            </button>
          </div>}

          {tab === "inbox" && <div className="design-card">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-semibold">收件箱候选人</h2>
                <p className="mt-1 text-sm text-steel">这里只显示已通过 BOSS 插件同步并解析入库的候选人。</p>
              </div>
              <button className="secondary-button" onClick={() => load()} disabled={refreshing}>
                <RefreshCw size={17} className={refreshing ? "animate-spin" : ""} />
                刷新
              </button>
            </div>
            <div className="relative mb-4">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-steel" size={16} />
              <input className="input pl-9" value={inboxQuery} onChange={(event) => setInboxQuery(event.target.value)} placeholder="搜索 BOSS 候选人、岗位、简历摘要" />
            </div>
            {message && <div className="mb-3 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</div>}
            <div className="data-list">
              {visibleInbox.length === 0 ? <EmptyState icon={<Users size={22} />} text="暂无匹配的 BOSS 候选人" /> : pagedInbox.items.map((item) => (
                <div className="boss-inbox-row" key={item.external_id}>
                  <div>
                    <h3>{item.name}</h3>
                    <p>{item.title}</p>
                    <span>{item.summary}</span>
                  </div>
                  <button className="secondary-button mt-3" onClick={() => openCandidate(item.candidate_id)} disabled={!item.candidate_id}>
                    <FileText size={17} />
                    查看简历
                  </button>
                </div>
              ))}
            </div>
            <PaginationControls total={visibleInbox.length} limit={pagedInbox.limit} offset={pagedInbox.offset} onChange={pagedInbox.onChange} />
          </div>}

          {tab === "recommend" && <div className="design-card">
            <h2 className="font-semibold">推荐候选人</h2>
            <p className="mt-1 text-sm text-steel">只从 BOSS 已导入的沟通过候选人里匹配当前 BOSS 岗位{selectedJob ? `：${selectedJob.title}` : ""}。</p>
            <div className="data-list mt-4">
              {recommendations.length === 0 ? <EmptyState icon={<Users size={22} />} text="当前岗位暂无推荐候选人" /> : pagedRecommendations.items.map((item) => (
                <div className={`data-row text-left ${candidateId === item.candidate_id ? "active" : ""}`} key={item.candidate_id}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{item.candidate.name_masked}</h3>
                      <span className="badge">{item.score}/100</span>
                    </div>
                    <p className="text-sm text-steel">{item.candidate.title} · {item.candidate.city || "城市未识别"}</p>
                    <p className="mt-2 text-xs text-steel">
                      命中：{item.reason.hits.slice(0, 4).map((hit) => hit.candidate_tag).join("、") || "暂无"}；缺失：{item.reason.missing_tags.slice(0, 3).join("、") || "无"}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button className="secondary-button" onClick={() => { setCandidateId(item.candidate_id); notify("success", `已选择候选人：${item.candidate.name_masked}`); }}>
                        <Check size={17} />
                        选中候选人
                      </button>
                      <button className="secondary-button" onClick={() => openCandidate(item.candidate_id)}>
                        <FileText size={17} />
                        查看简历
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <PaginationControls total={recommendations.length} limit={pagedRecommendations.limit} offset={pagedRecommendations.offset} onChange={pagedRecommendations.onChange} />
          </div>}

          {tab === "jobs" && <div className="design-card">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="font-semibold">BOSS 岗位列表</h2>
              <button className="secondary-button" onClick={() => load()} disabled={refreshing}>
                <RefreshCw size={17} className={refreshing ? "animate-spin" : ""} />
                刷新
              </button>
            </div>
            <div className="data-list mt-4">
              {jobs.length === 0 ? <EmptyState icon={<BriefcaseBusiness size={22} />} text="暂无同步的 BOSS 岗位，请先用浏览器插件同步岗位列表" /> : pagedBossJobs.items.map((job) => (
                <div className={`data-row text-left ${jobId === job.id ? "active" : ""}`} key={job.id}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{job.title}</h3>
                      <span className={`badge ${job.status === "active" ? "" : "muted"}`}>{job.status === "active" ? "开放" : "关闭"}</span>
                    </div>
                    <p className="text-sm text-steel">{job.city || "未填城市"} · {job.job_code || "无编号"}</p>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 md:mt-0">
                    <button className="secondary-button" onClick={() => selectJob(job)}>
                      <Check size={17} />
                      选中岗位
                    </button>
                    <button className="primary-button" onClick={() => selectJob(job, "recommend")}>
                      <Users size={17} />
                      匹配候选人
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <PaginationControls total={jobs.length} limit={pagedBossJobs.limit} offset={pagedBossJobs.offset} onChange={pagedBossJobs.onChange} />
          </div>}
        </div>
      </div>
    </section>
  );
}

function BiPage() {
  const [data, setData] = useState<BiOverview | null>(null);
  const [llmUsage, setLlmUsage] = useState<LLMUsageSummary | null>(null);
  const [periodDays, setPeriodDays] = useState(30);
  useEffect(() => {
    api.bi(periodDays).then(setData);
    api.llmUsage(periodDays).then(setLlmUsage).catch(() => setLlmUsage(null));
  }, [periodDays]);
  if (!data) return <EmptyState icon={<BarChart3 size={22} />} text="正在加载 BI 数据" />;
  const funnel = data.pipeline_funnel;
  const inFlow = Object.entries(funnel).reduce((sum, [stage, count]) => sum + (["onboarded", "rejected"].includes(stage) ? 0 : count), 0);
  const onboarded = funnel.onboarded || 0;
  const interviews = (funnel.interview_first || 0) + (funnel.interview_second || 0) + (funnel.interview_final || 0);
  const offers = funnel.offer || 0;

  return (
    <section className="design-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="design-title">
          <h1>数据看板</h1>
          <p>看团队招聘进度、卡点和协同跟进</p>
        </div>
        <div className="period-tabs">
          {[7, 30, 90].map((days) => (
            <button key={days} className={periodDays === days ? "active" : ""} onClick={() => setPeriodDays(days)}>
              近 {days} 天
            </button>
          ))}
        </div>
      </div>

      {llmUsage?.alerts?.length ? (
        <div className="design-card">
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold">AI 用量告警</h2>
              <p className="text-xs text-steel">
                日均调用 {llmUsage.summary.avg_daily_calls} 次 · 日均成本 ${llmUsage.summary.avg_daily_cost_usd.toFixed(4)} · 失败率 {llmUsage.summary.failure_rate}%
              </p>
            </div>
            <span className="badge danger">{llmUsage.alerts.length} 项告警</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            {llmUsage.alerts.map((item) => (
              <div className="rounded-md border border-line px-3 py-2 text-sm" key={item.key}>
                <span className={item.severity === "error" ? "text-red-700" : "text-amber-700"}>{item.severity === "error" ? "阻塞" : "提醒"}</span>
                <span className="ml-2 text-ink">{item.message}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="kpi-grid">
        <KpiCard label="在招专员" value={data.active_jobs} hint="开放岗位" tone="blue" />
        <KpiCard label="当前入职" value={onboarded} hint="归档结果" tone="green" />
        <KpiCard label="全流程入职占比" value={`${data.total_candidates ? ((onboarded / data.total_candidates) * 100).toFixed(1) : "0.0"}%`} hint="活跃流程 + 归档结果" tone="purple" />
        <KpiCard label="当前流程人数" value={inFlow} hint="不含已入职/已淘汰" tone="yellow" />
        <KpiCard label="有效推荐" value={data.total_candidates} hint="人才库候选人" tone="orange" />
        <KpiCard label="推荐成功面试" value={interviews} hint="进入面试中阶段" tone="blue" />
        <KpiCard label="面试通过" value={`${offers} / ${interviews}`} hint={`通过率 ${interviews ? ((offers / interviews) * 100).toFixed(1) : "0.0"}%`} tone="purple" />
        <KpiCard label="待补反馈" value={funnel.business_review || 0} hint="业务复核中" tone="red" />
        <KpiCard label="AI 调用" value={llmUsage?.summary.total_calls ?? 0} hint={`成功率 ${llmUsage?.summary.success_rate ?? 100}%`} tone="blue" />
        <KpiCard label="AI 成本" value={`$${(llmUsage?.summary.estimated_cost_usd ?? 0).toFixed(4)}`} hint={`日均 $${(llmUsage?.summary.avg_daily_cost_usd ?? 0).toFixed(4)} · ${llmUsage?.summary.total_tokens ?? 0} tokens`} tone="green" />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <div className="design-card">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold">需求健康</h2>
            <span className="status-chip">A/B/C {data.active_jobs} / {inFlow} / {offers}</span>
          </div>
          <div className="mini-grid">
            <KpiMini label="活跃需求" value={data.active_jobs} hint="待处理与招聘中" />
            <KpiMini label="邀聊需求" value={funnel.pending || 0} hint="超过目标后期" />
            <KpiMini label="HR 无推荐" value={0} hint="接手 7 天未推荐" />
            <KpiMini label="业务待反馈" value={funnel.business_review || 0} hint="卡在业务复核" />
          </div>
        </div>
        <div className="design-card">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold">简历消化</h2>
            <span className="status-chip">进流程 {data.total_candidates ? ((inFlow / data.total_candidates) * 100).toFixed(1) : "0.0"}%</span>
          </div>
          <div className="mini-grid">
            <KpiMini label="入库简历" value={data.total_candidates} hint="当前周期" />
            <KpiMini label="绑定岗位" value={inFlow} hint={`${Math.max(data.total_candidates - inFlow, 0)} 份暂未绑定`} />
            <KpiMini label="已匹配" value={funnel.ai_screen || 0} hint="匹配率" />
            <KpiMini label="已进流程" value={inFlow} hint={`${Math.max(data.total_candidates - inFlow, 0)} 份未进流程`} />
            <KpiMini label="进流程率" value={`${data.total_candidates ? ((inFlow / data.total_candidates) * 100).toFixed(1) : "0.0"}%`} hint="入库到流程转化" />
          </div>
        </div>
      </div>
    </section>
  );
}

function KpiCard({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint: string; tone: string }) {
  return (
    <AntCard className={`kpi-card tone-${tone}`} variant="outlined">
      <AntStatistic title={label} value={String(value)} />
      <p>{hint}</p>
    </AntCard>
  );
}

function KpiMini({ label, value, hint }: { label: string; value: React.ReactNode; hint: string }) {
  return (
    <AntCard className="kpi-mini" size="small" variant="outlined">
      <AntStatistic title={label} value={String(value)} />
      <p>{hint}</p>
    </AntCard>
  );
}

function PaginationControls({
  total,
  limit,
  offset,
  onChange
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number, limit: number) => void;
}) {
  if (total <= 0) return null;
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const start = Math.min(offset + 1, total);
  const end = Math.min(offset + limit, total);
  return (
    <div className="mt-4 flex flex-col gap-3 rounded-lg border border-line bg-white px-3 py-3 text-sm text-steel sm:flex-row sm:items-center sm:justify-between">
      <span>显示 {start}-{end} / {total}</span>
      <div className="flex flex-wrap items-center gap-2">
        <select className="select" value={limit} onChange={(event) => onChange(0, Number(event.target.value))}>
          {[20, 50, 100, 200].map((size) => <option key={size} value={size}>{size} / 页</option>)}
        </select>
        <button className="secondary-button" type="button" disabled={page <= 1} onClick={() => onChange(Math.max(0, offset - limit), limit)}>
          上一页
        </button>
        <span className="px-2">{page} / {pageCount}</span>
        <button className="secondary-button" type="button" disabled={page >= pageCount} onClick={() => onChange(offset + limit, limit)}>
          下一页
        </button>
      </div>
    </div>
  );
}

function useClientPagination<T>(items: T[], defaultLimit = 20) {
  const [limit, setLimit] = useState(defaultLimit);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    setOffset(0);
  }, [items.length, limit]);

  const pagedItems = useMemo(() => items.slice(offset, offset + limit), [items, offset, limit]);

  return {
    items: pagedItems,
    limit,
    offset,
    onChange: (nextOffset: number, nextLimit: number) => {
      setLimit(nextLimit);
      setOffset(Math.max(0, nextOffset));
    }
  };
}

function AgentPage() {
  type AgentTurn = { role: "user" | "assistant"; content: string; response?: AgentResponse };
  const [message, setMessage] = useState("");
  const [conversations, setConversations] = useState<AgentConversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<AgentConversation | null>(null);
  const [turns, setTurns] = useState<AgentTurn[]>([]);
  const [tools, setTools] = useState<{ name: string; description: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<Record<string, unknown> | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api.agentTools().then((data) => setTools(data.items));
    loadConversations();
  }, []);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  async function loadConversations(selectId?: number) {
    setLoading(true);
    try {
      const data = await api.agentConversations();
      setConversations(data.items);
      const target = selectId ? data.items.find((item) => item.id === selectId) : data.items[0];
      if (target) {
        await openConversation(target.id);
      } else {
        setActiveConversation(null);
        setTurns(welcomeTurns());
        setPendingAction(null);
      }
    } finally {
      setLoading(false);
    }
  }

  async function openConversation(id: number) {
    const data = await api.getAgentConversation(id);
    setActiveConversation(data);
    setPendingAction(data.pending_action || null);
    setTurns(agentMessagesToTurns(data.messages || []));
  }

  async function newConversation() {
    const data = await api.createAgentConversation("新对话");
    setConversations((items) => [data, ...items]);
    setActiveConversation(data);
    setPendingAction(null);
    setTurns(welcomeTurns());
  }

  async function archiveConversation(id: number) {
    await api.updateAgentConversation(id, { status: "archived" });
    const next = conversations.filter((item) => item.id !== id);
    setConversations(next);
    if (activeConversation?.id === id) {
      if (next[0]) await openConversation(next[0].id);
      else {
        setActiveConversation(null);
        setTurns(welcomeTurns());
        setPendingAction(null);
      }
    }
  }

  async function send(nextMessage = message) {
    const content = nextMessage.trim();
    if (!content || busy) return;
    setBusy(true);
    setTurns((current) => [...current, { role: "user", content }]);
    setMessage("");
    try {
      const data = await api.chat(content, pendingAction, activeConversation?.id || null);
      setPendingAction(data.pending_action || null);
      setTurns((current) => [...current, { role: "assistant", content: data.answer, response: data }]);
      if (data.conversation) {
        setActiveConversation(data.conversation);
        setConversations((items) => upsertConversation(items, data.conversation as AgentConversation));
      }
    } finally {
      setBusy(false);
    }
  }

  const latest = [...turns].reverse().find((turn) => turn.response)?.response;
  const quickQuestions = latest?.suggestions || ["现在人才库有多少人？软件开发和会计分别多少？", "创建岗位 数据分析师 城市上海 部门数据部 JD 要求 SQL、Python、报表分析，3 年以上经验", "推荐财务会计主管候选人", "现在面试和 Offer 状态怎么样？"];

  return (
    <section className="agent-chat-page" data-testid="page-agent">
      <header className="agent-page-head">
        <div>
          <h1>AI Agent</h1>
          <span>{busy ? "正在执行" : loading ? "正在加载历史" : "就绪"} · 已连接 {tools.length || 12} 个工具 · 历史自动保存</span>
        </div>
        <button className="primary-button" type="button" onClick={newConversation}>
          <Plus size={17} />
          新建聊天
        </button>
      </header>

      <div className="agent-shell">
        <aside className="agent-sidebar">
          <div className="agent-sidebar-title">
            <span>对话历史</span>
            <span>{conversations.length}</span>
          </div>
          <div className="agent-session-list">
            {conversations.map((item) => (
              <button
                className={`agent-session ${activeConversation?.id === item.id ? "active" : ""}`}
                key={item.id}
                type="button"
                onClick={() => openConversation(item.id)}
              >
                <strong>{item.title}</strong>
                <span>{item.last_message || "暂无消息"}</span>
                <small>{item.updated_at ? formatDateTime(item.updated_at) : ""}</small>
              </button>
            ))}
            {!conversations.length && <div className="agent-empty">还没有历史对话</div>}
          </div>
        </aside>

        <main className="agent-main">
          <div className="agent-thread">
            {turns.map((turn, index) => (
              <div className={`agent-turn ${turn.role}`} key={`${turn.role}-${index}`}>
                <div className="agent-turn-icon">
                  {turn.role === "assistant" ? <Bot size={16} /> : <Users size={16} />}
                </div>
                <div className="agent-message">
                  <p>{turn.content}</p>
                  {turn.role === "assistant" && turn.response && <AgentTrace response={turn.response} />}
                </div>
              </div>
            ))}
            {busy && (
              <div className="agent-turn assistant">
                <div className="agent-turn-icon"><Bot size={16} /></div>
                <div className="agent-message agent-thinking">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            <div ref={threadEndRef} />
          </div>

          <div className="agent-quick-row">
            {quickQuestions.slice(0, 4).map((question) => (
              <button type="button" key={question} onClick={() => send(question)}>
                {question}
              </button>
            ))}
          </div>

          <form
            className="agent-composer"
            data-testid="agent-composer"
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
          >
            <textarea
              data-testid="agent-input"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
              placeholder="输入问题，Enter 发送 · Shift+Enter 换行"
            />
            <button type="submit" disabled={busy || !message.trim()} title="发送">
              <SendHorizontal size={18} />
            </button>
          </form>
          <div className="agent-footnote">
            <span>当前对话：{activeConversation?.title || "新对话"}</span>
            {activeConversation && (
              <button type="button" onClick={() => archiveConversation(activeConversation.id)}>
                归档对话
              </button>
            )}
          </div>
        </main>
      </div>
    </section>
  );
}

function welcomeTurns(): { role: "user" | "assistant"; content: string; response?: AgentResponse }[] {
  return [{
    role: "assistant",
    content: "我是招聘 AI Agent。现在支持新建多轮对话、保留历史记录，并可以结合上下文调用人才库、岗位匹配、流程、面试、Offer、BOSS 和 BI 工具。"
  }];
}

function agentMessagesToTurns(messages: AgentMessage[]): { role: "user" | "assistant"; content: string; response?: AgentResponse }[] {
  if (!messages.length) return welcomeTurns();
  return messages.map((item) => ({
    role: item.role,
    content: item.content,
    response: item.response || undefined
  }));
}

function upsertConversation(items: AgentConversation[], conversation: AgentConversation) {
  return [conversation, ...items.filter((item) => item.id !== conversation.id)].sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
}

function AgentTrace({ response }: { response: AgentResponse }) {
  const trace = response.agent_trace;
  if (!trace && (!response.tool || response.tool === "chat")) return null;
  const plan = trace?.plan || [];
  const calls = trace?.tool_calls || response.tool_calls || (response.tool ? [{ name: response.tool, status: "succeeded", readonly: response.readonly }] : []);
  const knowledge = trace?.knowledge;
  const knowledgeCount = knowledge
    ? (knowledge.candidates?.length || 0) + (knowledge.employees?.length || 0) + (knowledge.users?.length || 0) + (knowledge.jobs?.length || 0)
    : 0;
  return (
    <div className="agent-trace">
      <div className="agent-trace-head">
        <span><Sparkles size={14} />{trace?.mode === "deepseek" ? "DeepSeek 规划" : "本地规划"}</span>
        <span>{trace?.intent || response.tool}</span>
      </div>
      {plan.length > 0 && (
        <div className="agent-trace-steps">
          {plan.slice(0, 4).map((item, index) => (
            <div className="agent-trace-step" key={`${item.step}-${index}`}>
              <b>{index + 1}</b>
              <span>{item.step}</span>
              {item.detail && <small>{item.detail}</small>}
            </div>
          ))}
        </div>
      )}
      <div className="agent-trace-calls">
        {calls.map((call, index) => (
          <span className={call.status === "succeeded" ? "done" : "planned"} key={`${call.name}-${index}`}>
            <Wrench size={13} />
            {call.name}
            <small>{call.status === "succeeded" ? "已调用" : "计划"}</small>
          </span>
        ))}
      </div>
      <details className="agent-trace-detail">
        <summary>
          <Database size={13} />
          记忆与知识库
          <ChevronRight size={13} />
        </summary>
        <div className="agent-trace-grid">
          <span>历史记忆：{trace?.memory?.length || 0} 条</span>
          <span>知识命中：{knowledgeCount} 条</span>
          <span>联网：{trace?.web?.needed ? "已判断需要" : "未需要"}</span>
          {trace?.planner_error && <span>规划器兜底：{trace.planner_error}</span>}
        </div>
        {calls.some((call) => call.summary) && (
          <ul>
            {calls.filter((call) => call.summary).map((call, index) => <li key={`${call.name}-summary-${index}`}>{call.name}：{call.summary}</li>)}
          </ul>
        )}
      </details>
    </div>
  );
}

function TasksPage({ setView }: { setView: (view: View) => void }) {
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [status, setStatus] = useState("all");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [opsStatus, setOpsStatus] = useState<OpsBackupStatus | null>(null);
  const [dataQuality, setDataQuality] = useState<OpsDataQuality | null>(null);
  const [deployGates, setDeployGates] = useState<OpsDeployGates | null>(null);
  const [opsBusy, setOpsBusy] = useState(false);

  async function load(nextStatus = status) {
    const data = await api.tasks(nextStatus);
    setTasks(data.items);
    setCounts(data.status_counts || {});
  }

  async function loadOps() {
    const [statusData, qualityData, gateData] = await Promise.all([api.opsBackupStatus(), api.opsDataQuality(), api.opsDeployGates()]);
    setOpsStatus(statusData);
    setDataQuality(qualityData);
    setDeployGates(gateData);
  }

  useEffect(() => {
    load(status);
    loadOps();
  }, [status]);

  async function retry(task: BackgroundTask) {
    setBusyId(task.id);
    try {
      await api.retryTask(task.id);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function runTaskNow(task: BackgroundTask) {
    setBusyId(task.id);
    try {
      await api.runTask(task.id);
      await load(status);
    } finally {
      setBusyId(null);
    }
  }

  async function createBackup() {
    setOpsBusy(true);
    try {
      await api.createBackupExport();
      await Promise.all([load(), loadOps()]);
    } finally {
      setOpsBusy(false);
    }
  }

  const statuses = ["all", "queued", "running", "succeeded", "failed"];
  const pagedTasks = useClientPagination(tasks, 20);
  const totalRows = opsStatus ? Object.values(opsStatus.counts || {}).reduce((sum, value) => sum + Number(value || 0), 0) : 0;
  const moduleTarget: Record<string, View> = {
    "人才库": "candidates",
    "组织与内部人才": "organization",
    "岗位匹配": "jobs",
  };

  return (
    <section className="space-y-4">
      <div className="toolbar">
        <div>
          <h2 className="font-semibold">后台任务</h2>
          <p className="text-xs text-steel">用于批量解析、AI 评分、BOSS 同步等耗时任务的队列状态。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select className="select" value={status} onChange={(event) => setStatus(event.target.value)}>
            {statuses.map((item) => <option value={item} key={item}>{taskStatusLabel(item)}{item !== "all" ? ` · ${counts[item] || 0}` : ""}</option>)}
          </select>
          <button className="secondary-button" onClick={() => load()}>
            <RefreshCw size={17} />
            刷新
          </button>
        </div>
      </div>

      <div className="data-panel">
        <div className="data-panel-head">
          <div>
            <h2>上线运维</h2>
            <p>备份、迁移、环境预检只做安全操作；生产覆盖迁移保留为人工确认命令。</p>
          </div>
          <button className="primary-button" disabled={opsBusy} onClick={createBackup}>
            <Download size={17} />
            {opsBusy ? "创建中" : "创建本地备份包"}
          </button>
        </div>
        {!opsStatus ? (
          <div className="p-4"><AntSpin tip="正在读取运维状态" /></div>
        ) : (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              <KpiMini label="环境" value={opsStatus.environment} hint={opsStatus.database} />
              <KpiMini label="预检" value={opsStatus.readiness.ready ? "可上线" : "需处理"} hint={`${opsStatus.readiness.summary.errors} 错误 / ${opsStatus.readiness.summary.warnings} 警告`} />
              <KpiMini label="迁移版本" value={opsStatus.migration.at_head ? "最新" : "未对齐"} hint={opsStatus.migration.current.join(", ") || "未记录"} />
              <KpiMini label="数据行数" value={totalRows} hint="全表合计，仅用于备份校验" />
            </div>
            <div className="design-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold">上线部署门禁</h3>
                  <p className="text-xs text-steel">生产环境启动前必须通过的配置、迁移、目录和 AI 能力检查。</p>
                </div>
                {deployGates && (
                  <div className="flex flex-wrap gap-2">
                    <span className={`badge ${deployGates.ready ? "success" : "danger"}`}>{deployGates.ready ? "门禁通过" : "门禁未通过"}</span>
                    <span className="badge muted">{deployGates.summary.errors} 阻断 · {deployGates.summary.warnings} 警告</span>
                  </div>
                )}
              </div>
              {!deployGates ? (
                <div className="mt-4"><AntSpin tip="正在读取部署门禁" /></div>
              ) : (
                <div className="mt-4 grid gap-2 md:grid-cols-2">
                  {deployGates.gates.map((gate) => (
                    <div className={`rounded-md border p-3 ${gate.ok ? "border-line bg-white" : gate.severity === "error" ? "border-red-200 bg-red-50" : "border-orange-200 bg-orange-50"}`} key={gate.key}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`badge ${gate.ok ? "success" : gate.severity === "error" ? "danger" : "muted"}`}>{gate.ok ? "通过" : gate.severity === "error" ? "阻断" : "警告"}</span>
                        <strong>{gate.title}</strong>
                        <span className="badge muted">{gate.category}</span>
                      </div>
                      <p className="mt-2 text-xs text-steel">{gate.detail}</p>
                      {!gate.ok && <p className="mt-1 text-xs text-ink">处理：{gate.action}</p>}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="design-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold">上线数据质量</h3>
                  <p className="text-xs text-steel">上线前重点处理会影响解析、匹配、组织统计和迁移追溯的数据风险。</p>
                </div>
                {dataQuality && (
                  <div className="flex flex-wrap gap-2">
                    <span className={`badge ${dataQuality.ready ? "success" : "danger"}`}>{dataQuality.ready ? "无阻断项" : "存在阻断项"}</span>
                    <span className="badge muted">{dataQuality.summary.issues} 类问题 · {dataQuality.summary.items} 条数据</span>
                  </div>
                )}
              </div>
              {!dataQuality ? (
                <div className="mt-4"><AntSpin tip="正在读取数据质量" /></div>
              ) : dataQuality.issues.length === 0 ? (
                <EmptyState icon={<ShieldCheck size={22} />} text="暂无上线数据质量风险" />
              ) : (
                <div className="mt-4 grid gap-3">
                  {dataQuality.issues.map((issue) => (
                    <div className="rounded-lg border border-line bg-white p-3" key={issue.key}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`badge ${issue.severity === "error" ? "danger" : "muted"}`}>{issue.severity === "error" ? "阻断" : "待优化"}</span>
                            <h4 className="font-semibold">{issue.title}</h4>
                            <span className="badge">{issue.count} 条</span>
                          </div>
                          <p className="mt-1 text-sm text-steel">{issue.impact}</p>
                          <p className="mt-1 text-xs text-steel">建议：{issue.action}</p>
                        </div>
                        <button className="secondary-button" type="button" onClick={() => setView(moduleTarget[issue.module] || "tasks")}>
                          打开{issue.module}
                        </button>
                      </div>
                      {issue.samples.length > 0 && (
                        <div className="mt-3 grid gap-2 md:grid-cols-2">
                          {issue.samples.map((sample) => (
                            <div className="rounded-md bg-slate-50 px-3 py-2 text-sm" key={`${issue.key}-${sample.id}`}>
                              <div className="flex items-center justify-between gap-2">
                                <strong className="truncate">{sample.name}</strong>
                                {sample.status && <span className="badge muted">{sample.status}</span>}
                              </div>
                              <p className="mt-1 truncate text-xs text-steel">{sample.subtitle || sample.error || `#${sample.id}`}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
              <div className="design-card">
                <h3 className="font-semibold">存储位置</h3>
                <div className="mt-3 grid gap-2 text-sm">
                  <StatusLine label="上传目录" value={opsStatus.storage.upload_dir_exists ? opsStatus.storage.upload_dir : "目录不存在"} />
                  <StatusLine label="备份目录" value={opsStatus.storage.backup_dir_exists ? opsStatus.storage.backup_dir : "目录不存在"} />
                  <StatusLine label="迁移 Head" value={opsStatus.migration.heads.join(", ") || "-"} />
                </div>
              </div>
              <div className="design-card">
                <h3 className="font-semibold">生产迁移命令</h3>
                <div className="mt-3 grid gap-2">
                  <code className="block overflow-auto rounded-md bg-slate-950 p-3 text-xs text-white">{opsStatus.commands.production_preflight}</code>
                  <code className="block overflow-auto rounded-md bg-slate-950 p-3 text-xs text-white">{opsStatus.commands.test_to_prod_migrate}</code>
                  <p className="text-xs text-orange-700">{opsStatus.commands.restore_warning}</p>
                </div>
              </div>
            </div>
            <div className="design-card">
              <h3 className="font-semibold">最近备份包</h3>
              <div className="mt-3 grid gap-2">
                {opsStatus.recent_packages.length === 0 && <EmptyState icon={<Database size={22} />} text="暂无备份包" />}
                {opsStatus.recent_packages.map((item) => (
                  <div className="data-row" key={item.path}>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <FileText size={16} className="text-mint" />
                        <h3 className="truncate font-semibold">{item.filename}</h3>
                        <span className="badge muted">{formatBytes(item.size_bytes)}</span>
                        {item.format && <span className="badge success">{item.format}</span>}
                      </div>
                      <p className="mt-1 text-xs text-steel">{formatDateTime(item.modified_at)} · {item.path}</p>
                    </div>
                    <span className="badge">{item.uploads?.files || 0} 附件</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="data-panel">
        <div className="data-list">
        {pagedTasks.items.map((task) => (
          <div className="data-row flex-col items-start" key={task.id}>
            <div className="flex w-full flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">#{task.id} {taskTypeLabel(task.task_type)}</h3>
                  <span className={`badge ${task.status === "failed" ? "danger" : task.status === "succeeded" ? "success" : "muted"}`}>{taskStatusLabel(task.status)}</span>
                  <span className="badge muted">尝试 {task.attempts}/{task.max_attempts}</span>
                </div>
                <p className="mt-1 text-sm text-steel">
                  {task.creator_name || "系统"} · 创建 {task.created_at ? formatDateTime(task.created_at) : "-"}
                  {task.finished_at ? ` · 完成 ${formatDateTime(task.finished_at)}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {task.status === "queued" && (
                  <button className="primary-button" disabled={busyId === task.id} onClick={() => runTaskNow(task)}>
                    <RefreshCw size={17} />
                    {busyId === task.id ? "执行中" : "立即执行"}
                  </button>
                )}
                {task.status === "failed" && (
                  <button className="secondary-button" disabled={busyId === task.id} onClick={() => retry(task)}>
                    <RefreshCw size={17} />
                    重新排队
                  </button>
                )}
              </div>
            </div>
            {task.error && <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{task.error}</p>}
            {Object.keys(task.result || {}).length > 0 && <p className="mt-2 text-xs text-steel">{JSON.stringify(task.result)}</p>}
          </div>
        ))}
        {tasks.length === 0 && <EmptyState icon={<Database size={22} />} text="暂无后台任务" />}
        </div>
        <PaginationControls total={tasks.length} limit={pagedTasks.limit} offset={pagedTasks.offset} onChange={pagedTasks.onChange} />
      </div>
    </section>
  );
}

function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [filter, setFilter] = useState("");

  function load() {
    api.auditLogs().then((data) => setLogs(data.items));
  }

  useEffect(load, []);

  const visible = useMemo(() => {
    const keyword = filter.trim().toLowerCase();
    if (!keyword) return logs;
    return logs.filter((item) =>
      [item.user_name, item.action, item.target_type, item.target_name, JSON.stringify(item.details || {})]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    );
  }, [logs, filter]);
  const pagedLogs = useClientPagination(visible, 20);

  return (
    <section className="space-y-4">
      <div className="toolbar">
        <div>
          <h2 className="font-semibold">操作日志</h2>
          <p className="text-xs text-steel">记录候选人、岗位、面试、Offer 和用户管理等关键动作。</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <input className="input w-64" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="搜索操作人、对象、动作" />
          <button className="secondary-button" onClick={load}>
            <RefreshCw size={17} />
            刷新
          </button>
        </div>
      </div>
      <div className="data-panel">
        <div className="data-list">
        {pagedLogs.items.map((item) => (
          <div className="data-row" key={item.id}>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{item.user_name}</h3>
                <span className="badge">{auditActionLabel(item.action)}</span>
                <span className="badge muted">{auditTargetLabel(item.target_type)}</span>
              </div>
              <p className="mt-1 text-sm text-steel">{item.target_name || `#${item.target_id || "-"}`} · {formatDateTime(item.created_at)}</p>
              {Object.keys(item.details || {}).length > 0 && <p className="mt-2 text-xs text-steel">{JSON.stringify(item.details)}</p>}
            </div>
          </div>
        ))}
        {visible.length === 0 && <EmptyState icon={<Clock3 size={22} />} text="暂无操作日志" />}
        </div>
        <PaginationControls total={visible.length} limit={pagedLogs.limit} offset={pagedLogs.offset} onChange={pagedLogs.onChange} />
      </div>
    </section>
  );
}

function UsersPage({ currentUser }: { currentUser: User }) {
  const [users, setUsers] = useState<User[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [payload, setPayload] = useState({ username: "", name: "", role: "recruiter", password: "ChangeMe123" });

  async function load() {
    const data = await api.users();
    setUsers(data.items);
  }

  useEffect(() => {
    load();
  }, []);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const created = await api.createUser(payload);
      setUsers([...users, created]);
      setPayload({ username: "", name: "", role: "recruiter", password: "ChangeMe123" });
      setMessage("用户已创建");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "用户创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function setActive(target: User, active: boolean) {
    const updated = await api.updateUser(target.id, { active });
    setUsers(users.map((item) => (item.id === updated.id ? updated : item)));
  }
  const pagedUsers = useClientPagination(users, 20);

  return (
    <section className="grid gap-5 xl:grid-cols-[360px_1fr]">
      <form onSubmit={create} className="rounded-lg border border-line bg-white p-4 shadow-panel">
        <h2 className="font-semibold">创建账号</h2>
        <label className="field-label mt-4">用户名</label>
        <input className="input" value={payload.username} onChange={(event) => setPayload({ ...payload, username: event.target.value })} />
        <label className="field-label mt-3">姓名</label>
        <input className="input" value={payload.name} onChange={(event) => setPayload({ ...payload, name: event.target.value })} />
        <label className="field-label mt-3">角色</label>
        <select className="select w-full" value={payload.role} onChange={(event) => setPayload({ ...payload, role: event.target.value })}>
          <option value="admin">admin</option>
          <option value="manager">manager</option>
          <option value="recruiter">recruiter</option>
          <option value="interviewer">interviewer</option>
        </select>
        <label className="field-label mt-3">初始密码</label>
        <input className="input" value={payload.password} onChange={(event) => setPayload({ ...payload, password: event.target.value })} />
        <button className="primary-button mt-4 w-full" type="submit" disabled={busy}>
          <Plus size={17} />
          {busy ? "创建中" : "创建"}
        </button>
        {message && <p className="mt-3 text-sm text-mint">{message}</p>}
      </form>

      <div className="data-panel">
        <div className="data-panel-head">
          <div>
            <h2>账号列表</h2>
            <p>共 {users.length} 个系统账号。</p>
          </div>
        </div>
        <div className="data-list">
        {pagedUsers.items.map((item) => (
          <div className="data-row" key={item.id}>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="font-semibold">{item.name}</h3>
                <span className="badge">{item.role}</span>
                <span className={`badge ${item.active ? "" : "muted"}`}>{item.active ? "启用" : "禁用"}</span>
              </div>
              <p className="mt-1 text-sm text-steel">{item.username}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {(item.permissions || []).slice(0, 6).map((permission) => (
                  <span className="chip" key={permission}>{permission}</span>
                ))}
              </div>
            </div>
            <button className="secondary-button" disabled={item.id === currentUser.id} onClick={() => setActive(item, !item.active)}>
              {item.active ? "禁用" : "启用"}
            </button>
          </div>
        ))}
        </div>
        <PaginationControls total={users.length} limit={pagedUsers.limit} offset={pagedUsers.offset} onChange={pagedUsers.onChange} />
      </div>
    </section>
  );
}

function OrganizationManagementPage() {
  const [units, setUnits] = useState<OrganizationUnit[]>([]);
  const [employees, setEmployees] = useState<EmployeeProfile[]>([]);
  const [selectedId, setSelectedId] = useState(0);
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeProfile | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [orgFormOpen, setOrgFormOpen] = useState(false);
  const [orgFormMode, setOrgFormMode] = useState<"create" | "edit" | null>(null);
  const [orgResumeOpen, setOrgResumeOpen] = useState(false);
  const [orgQuery, setOrgQuery] = useState("");
  const [orgTreeExpanded, setOrgTreeExpanded] = useState<Set<number>>(() => new Set());
  const [unitForm, setUnitForm] = useState({ name: "", unit_type: "department", parent_id: 0, city: "", headcount_plan: "" });
  const [resumeFiles, setResumeFiles] = useState<File[]>([]);
  const [employeeTotal, setEmployeeTotal] = useState(0);
  const [employeeLimit, setEmployeeLimit] = useState(20);
  const [employeeOffset, setEmployeeOffset] = useState(0);
  const flatUnits = useMemo(() => flattenOrganizationUnits(units), [units]);
  const selectedUnit = flatUnits.find((unit) => unit.id === selectedId);
  const selectedPath = useMemo(() => organizationPath(flatUnits, selectedId), [flatUnits, selectedId]);
  const childUnits = selectedUnit?.children || [];
  const orgTreeExpandedIds = useMemo(() => {
    const next = new Set(orgTreeExpanded);
    selectedPath.forEach((unit) => next.add(unit.id));
    return next;
  }, [orgTreeExpanded, selectedPath]);
  const orgSearchResults = useMemo(() => {
    const keyword = orgQuery.trim().toLowerCase();
    if (!keyword) return [];
    return flatUnits.filter((unit) => `${unit.name} ${unit.city || ""} ${unit.unit_type || ""}`.toLowerCase().includes(keyword)).slice(0, 20);
  }, [flatUnits, orgQuery]);

  async function load(nextSelectedId = selectedId, nextOffset = employeeOffset, nextLimit = employeeLimit) {
    const tree = await api.organizationTree();
    setUnits(tree.items);
    const flattened = flattenOrganizationUnits(tree.items);
    const activeId = nextSelectedId || flattened[0]?.id || 0;
    if (activeId) {
      setSelectedId(activeId);
      const data = await api.organizationEmployees(activeId, { limit: nextLimit, offset: nextOffset });
      setEmployees(data.items);
      setEmployeeTotal(data.total);
      setEmployeeLimit(data.limit);
      setEmployeeOffset(data.offset);
      const unit = flattened.find((item) => item.id === activeId);
      if (unit) {
        setUnitForm({
          name: unit.name || "",
          unit_type: unit.unit_type || "department",
          parent_id: unit.parent_id || 0,
          city: unit.city || "",
          headcount_plan: unit.headcount_plan ? String(unit.headcount_plan) : ""
        });
      }
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function selectUnit(id: number) {
    setOrgFormOpen(false);
    setOrgFormMode(null);
    setEmployeeOffset(0);
    await load(id, 0, employeeLimit);
  }

  async function changeOrganizationEmployeePage(nextOffset: number, nextLimit = employeeLimit) {
    setEmployeeOffset(nextOffset);
    setEmployeeLimit(nextLimit);
    await load(selectedId, nextOffset, nextLimit);
  }

  function toggleOrgTreeUnit(unitId: number) {
    setOrgTreeExpanded((current) => {
      const next = new Set(current);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  }

  async function saveUnit(event: React.FormEvent) {
    event.preventDefault();
    if (!unitForm.name.trim()) {
      notify("error", "组织名称必填");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        ...unitForm,
        parent_id: unitForm.parent_id || undefined,
        headcount_plan: unitForm.headcount_plan ? Number(unitForm.headcount_plan) : undefined
      };
      const unit = orgFormMode === "create" ? await api.createOrganizationUnit(payload) : await api.updateOrganizationUnit(selectedId, payload);
      setMessage(`${unit.name} 已保存`);
      await load(unit.id);
      setOrgFormOpen(false);
      setOrgFormMode(null);
    } finally {
      setBusy(false);
    }
  }

  async function addChild() {
    setUnitForm({ name: "", unit_type: "department", parent_id: selectedId, city: selectedUnit?.city || "", headcount_plan: "" });
    setOrgFormMode("create");
    setOrgFormOpen(true);
  }

  function editCurrentUnit() {
    if (!selectedUnit) return;
    setUnitForm({
      name: selectedUnit.name || "",
      unit_type: selectedUnit.unit_type || "department",
      parent_id: selectedUnit.parent_id || 0,
      city: selectedUnit.city || "",
      headcount_plan: selectedUnit.headcount_plan ? String(selectedUnit.headcount_plan) : ""
    });
    setOrgFormMode("edit");
    setOrgFormOpen(true);
  }

  async function removeUnit() {
    if (!selectedUnit) return;
    if (!window.confirm(`确认删除组织「${selectedUnit.name}」？有员工或下级组织时不能删除。`)) return;
    await api.deleteOrganizationUnit(selectedUnit.id);
    setMessage("组织节点已删除");
    await load(0);
  }

  async function importExcel(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const data = await api.importOrganizationExcel(file);
      setMessage(`组织架构已导入，新增 ${data.created.length} 个节点`);
      await load(0);
    } finally {
      setBusy(false);
    }
  }

  async function uploadEmployeeResumes(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId) {
      notify("error", "请先选择组织节点");
      return;
    }
    if (!resumeFiles.length) {
      notify("error", "请先选择员工简历");
      return;
    }
    setBusy(true);
    try {
      const data = await api.uploadOrganizationEmployeeResumes(selectedId, resumeFiles);
      setMessage(`已导入 ${data.success_count} 名员工，失败 ${data.failed_count} 个文件`);
      setResumeFiles([]);
      setOrgResumeOpen(false);
      await load(selectedId);
    } finally {
      setBusy(false);
    }
  }

  async function openEmployee(employeeId: number) {
    const employee = await api.getEmployee(employeeId);
    setSelectedEmployee(employee);
  }

  if (selectedEmployee) {
    return (
      <EmployeeDetailPage
        employee={selectedEmployee}
        onBack={() => setSelectedEmployee(null)}
        onChanged={(employee) => {
          setSelectedEmployee(employee);
          load(selectedId);
        }}
        backLabel="返回组织架构"
      />
    );
  }

  return (
    <section className="space-y-5">
      <div className="design-card">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">组织架构</h2>
            <p className="mt-1 text-xs text-steel">按上级组织折叠展开定位部门，页面空间主要留给组织维护和员工列表。</p>
            <label className="field-label mt-4">搜索组织</label>
            <input className="input" value={orgQuery} onChange={(event) => setOrgQuery(event.target.value)} placeholder="搜索组织名称" />
            <div className="org-tree mt-3">
              {orgQuery.trim() ? (
                orgSearchResults.length ? (
                  orgSearchResults.map((unit) => (
                    <button className={`org-search-row ${selectedId === unit.id ? "active" : ""}`} key={unit.id} type="button" onClick={() => selectUnit(unit.id)}>
                      <span>{"　".repeat(unit.depth)}{unit.name}</span>
                      <span>{unit.employee_count || 0} 人</span>
                    </button>
                  ))
                ) : (
                  <div className="rounded-md border border-dashed border-line p-3 text-xs text-steel">未找到匹配组织</div>
                )
              ) : (
                <CompactOrganizationTree
                  units={units}
                  selectedId={selectedId}
                  expandedIds={orgTreeExpandedIds}
                  onToggle={toggleOrgTreeUnit}
                  onSelect={selectUnit}
                />
              )}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="secondary-button" onClick={() => load()}>
              <RefreshCw size={16} />
              刷新
            </button>
            <label className="secondary-button cursor-pointer">
              <Upload size={16} />
              导入组织架构 Excel
              <input className="hidden" type="file" accept=".xlsx" onChange={(event) => importExcel(event.target.files)} />
            </label>
          </div>
        </div>
        {selectedPath.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-steel">
            <span>路径</span>
            {selectedPath.map((unit) => <span className="chip" key={unit.id}>{unit.name}</span>)}
          </div>
        )}
        {childUnits.length > 0 && orgQuery.trim() && (
          <div className="mt-3 flex flex-wrap gap-2">
            {childUnits.map((unit) => (
              <button className="secondary-button" key={unit.id} type="button" onClick={() => selectUnit(unit.id)}>
                {unit.name}
                <span className="badge muted">{unit.employee_count || 0}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <aside className="hidden">
        <div className="design-card">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">组织架构</h2>
              <p className="text-xs text-steel">支持 Excel 导入、增删改查、按部门归档员工简历</p>
            </div>
            <button className="secondary-button" onClick={() => load()}>
              <RefreshCw size={16} />
            </button>
          </div>
          <label className="secondary-button mt-4 w-full cursor-pointer">
            <Upload size={16} />
            导入组织架构 Excel
            <input className="hidden" type="file" accept=".xlsx" onChange={(event) => importExcel(event.target.files)} />
          </label>
          <div className="mt-4 max-h-[520px] space-y-1 overflow-auto pr-1">
            {units.map((unit) => (
              <OrganizationNode key={unit.id} unit={unit} selectedId={selectedId} onSelect={selectUnit} />
            ))}
          </div>
        </div>
      </aside>

      <main className="space-y-4">
        <div className="toolbar">
          <div>
            <h2 className="font-semibold">{selectedUnit?.name || "新建组织"}</h2>
            <p className="text-xs text-steel">员工上传后会显示在当前组织节点下，并同步建立内部员工档案。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="secondary-button" type="button" onClick={addChild}>
              <Plus size={17} />
              添加组织
            </button>
            {selectedUnit && (
              <>
                <button className="secondary-button" type="button" onClick={editCurrentUnit}>
                  <Check size={17} />
                  编辑组织
                </button>
                <button className="secondary-button text-red-700" type="button" onClick={removeUnit}>
                  <Trash2 size={17} />
                  删除
                </button>
              </>
            )}
          </div>
        </div>

        {message && <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</div>}

        <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
          <div className="space-y-4">
            {orgFormOpen && (
            <div className="modal-backdrop" onClick={() => { setOrgFormOpen(false); setOrgFormMode(null); }}>
            <form className="modal-panel" onSubmit={saveUnit} onClick={(event) => event.stopPropagation()}>
              <div className="modal-head">
                <div>
                  <h3 className="font-semibold">{orgFormMode === "create" ? "添加组织" : "编辑组织"}</h3>
                  <p>维护组织名称、上级组织、类型和编制信息。</p>
                </div>
                <button className="icon-button" type="button" onClick={() => { setOrgFormOpen(false); setOrgFormMode(null); }}>
                  <X size={16} />
                </button>
              </div>
              <label className="field-label mt-4">组织名称</label>
              <input className="input" value={unitForm.name} onChange={(event) => setUnitForm({ ...unitForm, name: event.target.value })} />
              <label className="field-label mt-3">上级组织</label>
              <select className="select w-full" value={unitForm.parent_id} onChange={(event) => setUnitForm({ ...unitForm, parent_id: Number(event.target.value) })}>
                <option value={0}>无上级</option>
                {flatUnits.filter((unit) => unit.id !== selectedId).map((unit) => (
                  <option key={unit.id} value={unit.id}>{"　".repeat(unit.depth)}{unit.name}</option>
                ))}
              </select>
              <label className="field-label mt-3">组织类型</label>
              <select className="select w-full" value={unitForm.unit_type} onChange={(event) => setUnitForm({ ...unitForm, unit_type: event.target.value })}>
                <option value="company">公司</option>
                <option value="business_unit">事业部</option>
                <option value="department">部门</option>
                <option value="team">小组</option>
              </select>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <input className="input" placeholder="城市" value={unitForm.city} onChange={(event) => setUnitForm({ ...unitForm, city: event.target.value })} />
                <input className="input" placeholder="编制人数" value={unitForm.headcount_plan} onChange={(event) => setUnitForm({ ...unitForm, headcount_plan: event.target.value })} />
              </div>
              <button className="primary-button mt-4 w-full" disabled={busy}>
                <Check size={17} />
                保存组织
              </button>
              <button className="secondary-button mt-2 w-full" type="button" onClick={() => { setOrgFormOpen(false); setOrgFormMode(null); }}>
                取消
              </button>
            </form>
            </div>
            )}

            {orgResumeOpen && (
            <div className="modal-backdrop" onClick={() => setOrgResumeOpen(false)}>
            <form className="modal-panel" onSubmit={uploadEmployeeResumes} onClick={(event) => event.stopPropagation()}>
              <div className="modal-head">
                <div>
                  <h3 className="font-semibold">上传部门员工简历</h3>
                  <p>支持多文件和 ZIP，导入后员工名字会显示在部门员工列表。</p>
                </div>
                <button className="icon-button" type="button" onClick={() => setOrgResumeOpen(false)}>
                  <X size={16} />
                </button>
              </div>
              <label className="upload-drop mt-4">
                <FileText size={28} />
                <strong>{resumeFiles.length ? `已选择 ${resumeFiles.length} 个文件` : "选择员工简历或 ZIP"}</strong>
                <span>上传到：{selectedUnit?.name || "未选择组织"}</span>
                <input type="file" multiple accept=".txt,.md,.docx,.pdf,.zip" onChange={(event) => setResumeFiles(Array.from(event.target.files || []))} />
              </label>
              {resumeFiles.length > 0 && (
                <div className="mt-3 flex max-h-24 flex-wrap gap-1.5 overflow-auto">
                  {resumeFiles.map((file) => <span className="chip" key={`${file.name}-${file.size}`}>{file.name}</span>)}
                </div>
              )}
              <button className="primary-button mt-4 w-full" type="submit" disabled={busy || !selectedId || !resumeFiles.length}>
                <Upload size={17} />
                上传并归档员工
              </button>
              <button className="secondary-button mt-2 w-full" type="button" onClick={() => setOrgResumeOpen(false)}>
                取消
              </button>
            </form>
            </div>
            )}

            <div className="design-card">
              <h3 className="font-semibold">员工简历归档</h3>
              <p className="mt-1 text-xs text-steel">从当前组织入口上传员工简历，导入后自动建立内部员工档案。</p>
              <button className="primary-button mt-4 w-full" type="button" onClick={() => setOrgResumeOpen(true)} disabled={!selectedId}>
                <Upload size={17} />
                上传员工简历
              </button>
            </div>
          </div>

          <div className="design-card">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold">部门员工</h3>
                <p className="text-xs text-steel">{selectedUnit?.name || "全部"} · {employeeTotal} 人</p>
              </div>
            </div>
            {employees.length === 0 ? (
              <EmptyState icon={<Users size={22} />} text="当前组织下暂无员工" />
            ) : (
              <div className="mt-4 grid gap-3">
                {employees.map((employee) => (
                  <div className="row-card" key={employee.id}>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{employee.name}</h3>
                        <span className="badge">{employee.current_title}</span>
                        <span className="badge muted">{employee.employee_no || `#${employee.id}`}</span>
                      </div>
                      <p className="mt-1 text-sm text-steel">{employee.phone || "手机未维护"} · {employee.email || "邮箱未维护"}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <span className="badge">{employmentStatusLabel(employee.employment_status)}</span>
                      <button className="secondary-button" type="button" onClick={() => openEmployee(employee.id)}>
                        <FileText size={16} />
                        查看档案
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <PaginationControls
              total={employeeTotal}
              limit={employeeLimit}
              offset={employeeOffset}
              onChange={changeOrganizationEmployeePage}
            />
          </div>
        </section>
      </main>
    </section>
  );
}

function InternalTalentPage() {
  const [units, setUnits] = useState<OrganizationUnit[]>([]);
  const [employees, setEmployees] = useState<EmployeeProfile[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedUnitId, setSelectedUnitId] = useState<number>(0);
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeProfile | null>(null);
  const [message, setMessage] = useState("");
  const [salaryImport, setSalaryImport] = useState<{ updated_count: number; skipped_count: number; failed_count: number } | null>(null);
  const [transferOpen, setTransferOpen] = useState(false);
  const [salaryImportOpen, setSalaryImportOpen] = useState(false);
  const [employeeImportOpen, setEmployeeImportOpen] = useState(false);
  const [employeeImport, setEmployeeImport] = useState<{ created_count: number; updated_count: number; skipped_count: number; failed_count: number } | null>(null);
  const [orgFormOpen, setOrgFormOpen] = useState(false);
  const [orgFormMode, setOrgFormMode] = useState<"create" | "edit" | null>(null);
  const [orgResumeOpen, setOrgResumeOpen] = useState(false);
  const [resumeFiles, setResumeFiles] = useState<File[]>([]);
  const [unitForm, setUnitForm] = useState({ name: "", unit_type: "department", parent_id: 0, city: "", headcount_plan: "" });
  const [orgTreeQuery, setOrgTreeQuery] = useState("");
  const [orgTreeExpanded, setOrgTreeExpanded] = useState<Set<number>>(() => new Set());
  const [batchResult, setBatchResult] = useState<{ analyzed_count: number; skipped_count: number } | null>(null);
  const [employeeTotal, setEmployeeTotal] = useState(0);
  const [employeeOverview, setEmployeeOverview] = useState({ total: 0, active: 0, inactive: 0, with_compensation: 0, analyzed: 0, high_fit: 0, salary_risk: 0, avg_match_score: 0, avg_seniority_years: 0 });
  const [employeeLimit, setEmployeeLimit] = useState(20);
  const [employeeOffset, setEmployeeOffset] = useState(0);
  const [employeeQuery, setEmployeeQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    candidate_id: 0,
    organization_unit_id: 0,
    current_job_id: 0,
    employee_no: "",
    level: "",
    salary_monthly_k: "",
    salary_months: "13",
    hire_date: defaultDate()
  });
  const flatUnits = useMemo(() => flattenOrganizationUnits(units), [units]);
  const currentUnit = flatUnits.find((unit) => unit.id === selectedUnitId);
  const currentPath = useMemo(() => organizationPath(flatUnits, selectedUnitId), [flatUnits, selectedUnitId]);
  const currentChildren = currentUnit?.children || [];
  const orgTreeExpandedIds = useMemo(() => {
    const next = new Set(orgTreeExpanded);
    currentPath.forEach((unit) => next.add(unit.id));
    return next;
  }, [orgTreeExpanded, currentPath]);
  const orgSearchResults = useMemo(() => {
    const keyword = orgTreeQuery.trim().toLowerCase();
    if (!keyword) return [];
    return flatUnits.filter((unit) => `${unit.name} ${unit.city || ""} ${unit.unit_type || ""}`.toLowerCase().includes(keyword)).slice(0, 20);
  }, [flatUnits, orgTreeQuery]);

  async function load(unitId = selectedUnitId, nextOffset = employeeOffset, nextLimit = employeeLimit, nextQuery = employeeQuery) {
    const [tree, employeeData, candidateData, jobData] = await Promise.all([
      api.organizationTree(),
      api.employees(unitId || undefined, { limit: nextLimit, offset: nextOffset, q: nextQuery.trim() || undefined }),
      api.candidates(),
      api.jobs({ scope: "all" })
    ]);
    setUnits(tree.items);
    setEmployees(employeeData.items);
    setEmployeeTotal(employeeData.total);
    setEmployeeOverview(employeeData.overview);
    setEmployeeLimit(employeeData.limit);
    setEmployeeOffset(employeeData.offset);
    setCandidates(candidateData.items);
    setJobs(jobData.items);
    const flattened = flattenOrganizationUnits(tree.items);
    const firstUnit = flattened[0];
    const activeUnit = flattened.find((unit) => unit.id === unitId) || firstUnit;
    if (activeUnit) {
      setUnitForm({
        name: activeUnit.name || "",
        unit_type: activeUnit.unit_type || "department",
        parent_id: activeUnit.parent_id || 0,
        city: activeUnit.city || "",
        headcount_plan: activeUnit.headcount_plan ? String(activeUnit.headcount_plan) : ""
      });
    }
    setForm((current) => ({
      ...current,
      candidate_id: current.candidate_id || candidateData.items[0]?.id || 0,
      organization_unit_id: current.organization_unit_id || unitId || firstUnit?.id || 0,
      current_job_id: current.current_job_id || jobData.items[0]?.id || 0
    }));
  }

  useEffect(() => {
    load();
  }, []);

  async function selectUnit(unitId: number) {
    setSelectedUnitId(unitId);
    setSelectedEmployee(null);
    setEmployeeOffset(0);
    await load(unitId, 0, employeeLimit, employeeQuery);
  }

  async function changeInternalEmployeePage(nextOffset: number, nextLimit = employeeLimit) {
    setEmployeeOffset(nextOffset);
    setEmployeeLimit(nextLimit);
    await load(selectedUnitId, nextOffset, nextLimit, employeeQuery);
  }

  async function searchInternalEmployees(event: React.FormEvent) {
    event.preventDefault();
    setEmployeeOffset(0);
    await load(selectedUnitId, 0, employeeLimit, employeeQuery);
  }

  async function clearInternalEmployeeSearch() {
    setEmployeeQuery("");
    setEmployeeOffset(0);
    await load(selectedUnitId, 0, employeeLimit, "");
  }

  function toggleOrgTreeUnit(unitId: number) {
    setOrgTreeExpanded((current) => {
      const next = new Set(current);
      if (next.has(unitId)) next.delete(unitId);
      else next.add(unitId);
      return next;
    });
  }

  function addChildOrganization() {
    const parentId = selectedUnitId || flatUnits[0]?.id || 0;
    setUnitForm({ name: "", unit_type: "department", parent_id: parentId, city: currentUnit?.city || "", headcount_plan: "" });
    setOrgFormMode("create");
    setOrgFormOpen(true);
  }

  function editCurrentOrganization() {
    if (!currentUnit) return;
    setUnitForm({
      name: currentUnit.name || "",
      unit_type: currentUnit.unit_type || "department",
      parent_id: currentUnit.parent_id || 0,
      city: currentUnit.city || "",
      headcount_plan: currentUnit.headcount_plan ? String(currentUnit.headcount_plan) : ""
    });
    setOrgFormMode("edit");
    setOrgFormOpen(true);
  }

  async function saveOrganization(event: React.FormEvent) {
    event.preventDefault();
    if (!unitForm.name.trim()) {
      notify("error", "组织名称必填");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        ...unitForm,
        parent_id: unitForm.parent_id || undefined,
        headcount_plan: unitForm.headcount_plan ? Number(unitForm.headcount_plan) : undefined
      };
      const unit = orgFormMode === "create" ? await api.createOrganizationUnit(payload) : await api.updateOrganizationUnit(selectedUnitId, payload);
      setMessage(`${unit.name} 已保存`);
      setOrgFormOpen(false);
      setOrgFormMode(null);
      setSelectedUnitId(unit.id);
      await load(unit.id, 0, employeeLimit, employeeQuery);
    } finally {
      setBusy(false);
    }
  }

  async function deleteCurrentOrganization() {
    if (!currentUnit) return;
    if (!window.confirm(`确认删除组织「${currentUnit.name}」？有员工或下级组织时不能删除。`)) return;
    await api.deleteOrganizationUnit(currentUnit.id);
    setMessage("组织节点已删除");
    setSelectedUnitId(0);
    await load(0, 0, employeeLimit, employeeQuery);
  }

  async function importOrganizationExcel(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const data = await api.importOrganizationExcel(file);
      setMessage(`组织架构已导入，新增 ${data.created.length} 个节点`);
      await load(selectedUnitId, 0, employeeLimit, employeeQuery);
    } finally {
      setBusy(false);
    }
  }

  async function uploadOrganizationResumes(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedUnitId) {
      notify("error", "请先选择组织节点");
      return;
    }
    if (!resumeFiles.length) {
      notify("error", "请先选择员工简历");
      return;
    }
    setBusy(true);
    try {
      const data = await api.uploadOrganizationEmployeeResumes(selectedUnitId, resumeFiles);
      setMessage(`已导入 ${data.success_count} 名员工，失败 ${data.failed_count} 个文件`);
      setResumeFiles([]);
      setOrgResumeOpen(false);
      await load(selectedUnitId, 0, employeeLimit, employeeQuery);
    } finally {
      setBusy(false);
    }
  }

  async function createEmployee(event: React.FormEvent) {
    event.preventDefault();
    if (!form.candidate_id) {
      notify("error", "请先选择候选人");
      return;
    }
    setBusy(true);
    setMessage("");
    try {
      const employee = await api.createEmployeeFromCandidate(form);
      setMessage(`${employee.name} 已转为内部员工`);
      setTransferOpen(false);
      setSelectedEmployee(employee);
      await load(selectedUnitId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "转入内部员工失败");
    } finally {
      setBusy(false);
    }
  }

  async function importSalaryFile(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.importEmployeeCompensations(file);
      setSalaryImport(result);
      setMessage(`薪资表已导入：更新 ${result.updated_count} 人，跳过 ${result.skipped_count} 行，失败 ${result.failed_count} 行`);
      setSalaryImportOpen(false);
      await load(selectedUnitId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "薪资导入失败");
    } finally {
      setBusy(false);
    }
  }

  async function importEmployeeFile(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setMessage("");
    try {
      const result = await api.importEmployees(file);
      setEmployeeImport({
        created_count: result.created_count,
        updated_count: result.updated_count,
        skipped_count: result.skipped_count,
        failed_count: result.failed_count
      });
      setMessage(`员工台账已导入：新增 ${result.created_count} 人，更新 ${result.updated_count} 人，跳过 ${result.skipped_count} 行，失败 ${result.failed_count} 行`);
      setEmployeeImportOpen(false);
      await load(selectedUnitId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "员工台账导入失败");
    } finally {
      setBusy(false);
    }
  }

  async function batchAnalyze() {
    setBusy(true);
    setMessage("");
    try {
      const result = await api.batchAnalyzeEmployees({ organization_unit_id: selectedUnitId || undefined, limit: 300 });
      setBatchResult({ analyzed_count: result.analyzed_count, skipped_count: result.skipped_count });
      setMessage(`批量分析完成：已分析 ${result.analyzed_count} 人，跳过 ${result.skipped_count} 人`);
      await load(selectedUnitId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "批量分析失败");
    } finally {
      setBusy(false);
    }
  }

  if (selectedEmployee) {
    return (
      <EmployeeDetailPage
        employee={selectedEmployee}
        onBack={() => setSelectedEmployee(null)}
        onChanged={(employee) => {
          setSelectedEmployee(employee);
          load(selectedUnitId);
        }}
      />
    );
  }

  return (
    <section className="grid gap-5 xl:grid-cols-[320px_1fr]">
      <aside className="space-y-4">
        <div className="design-card">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">组织筛选</h2>
              <p className="text-xs text-steel">按上级部门折叠展开，快速定位员工所在组织。</p>
            </div>
            <button className="secondary-button" type="button" onClick={() => load(selectedUnitId)}>
              <RefreshCw size={16} />
            </button>
          </div>
          <label className="field-label mt-4">搜索组织</label>
          <input className="input" value={orgTreeQuery} onChange={(event) => setOrgTreeQuery(event.target.value)} placeholder="输入部门或团队名称" />
          <div className="org-tree mt-3">
            {orgTreeQuery.trim() ? (
              orgSearchResults.length ? (
                orgSearchResults.map((unit) => (
                  <button className={`org-search-row ${selectedUnitId === unit.id ? "active" : ""}`} key={unit.id} type="button" onClick={() => selectUnit(unit.id)}>
                    <span>{"　".repeat(unit.depth)}{unit.name}</span>
                    <span>{unit.employee_count || 0} 人</span>
                  </button>
                ))
              ) : (
                <div className="rounded-md border border-dashed border-line p-3 text-xs text-steel">未找到匹配组织</div>
              )
            ) : (
              <>
                <button className={`org-search-row ${selectedUnitId === 0 ? "active" : ""}`} type="button" onClick={() => selectUnit(0)}>
                  <span>全部内部人才</span>
                  <span>{employeeTotal} 人</span>
                </button>
                <CompactOrganizationTree
                  units={units}
                  selectedId={selectedUnitId}
                  expandedIds={orgTreeExpandedIds}
                  onToggle={toggleOrgTreeUnit}
                  onSelect={selectUnit}
                />
              </>
            )}
          </div>
          {currentPath.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {currentPath.map((unit) => <span className="chip" key={unit.id}>{unit.name}</span>)}
            </div>
          )}
          {currentChildren.length > 0 && orgTreeQuery.trim() && (
            <div className="mt-3 flex flex-wrap gap-2">
              {currentChildren.map((unit) => (
                <button className="secondary-button" key={unit.id} type="button" onClick={() => selectUnit(unit.id)}>
                  {unit.name}
                  <span className="badge muted">{unit.employee_count || 0}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="design-card">
          <h2 className="font-semibold">组织维护</h2>
          <p className="mt-1 text-xs text-steel">组织架构和内部员工在同一页面维护，避免重复入口。</p>
          <div className="mt-4 grid gap-2">
            <button className="secondary-button w-full" type="button" onClick={addChildOrganization}>
              <Plus size={16} />
              添加组织
            </button>
            <button className="secondary-button w-full" type="button" onClick={editCurrentOrganization} disabled={!currentUnit}>
              <Check size={16} />
              编辑当前组织
            </button>
            <button className="secondary-button w-full" type="button" onClick={() => setOrgResumeOpen(true)} disabled={!selectedUnitId}>
              <Upload size={16} />
              上传部门员工简历
            </button>
            <label className="secondary-button w-full cursor-pointer">
              <Upload size={16} />
              导入组织架构 Excel
              <input className="hidden" type="file" accept=".xlsx" onChange={(event) => importOrganizationExcel(event.target.files)} />
            </label>
            <button className="secondary-button w-full text-red-700" type="button" onClick={deleteCurrentOrganization} disabled={!currentUnit}>
              <Trash2 size={16} />
              删除当前组织
            </button>
          </div>
        </div>

        {orgFormOpen && (
          <div className="modal-backdrop" onClick={() => { setOrgFormOpen(false); setOrgFormMode(null); }}>
            <form className="modal-panel" onSubmit={saveOrganization} onClick={(event) => event.stopPropagation()}>
              <div className="modal-head">
                <div>
                  <h2 className="font-semibold">{orgFormMode === "create" ? "添加组织" : "编辑组织"}</h2>
                  <p>维护组织名称、上级组织、类型和编制信息。</p>
                </div>
                <button className="icon-button" type="button" onClick={() => { setOrgFormOpen(false); setOrgFormMode(null); }}>
                  <X size={16} />
                </button>
              </div>
              <label className="field-label mt-4">组织名称</label>
              <input className="input" value={unitForm.name} onChange={(event) => setUnitForm({ ...unitForm, name: event.target.value })} />
              <label className="field-label mt-3">上级组织</label>
              <select className="select w-full" value={unitForm.parent_id} onChange={(event) => setUnitForm({ ...unitForm, parent_id: Number(event.target.value) })}>
                <option value={0}>无上级</option>
                {flatUnits.filter((unit) => unit.id !== selectedUnitId).map((unit) => (
                  <option key={unit.id} value={unit.id}>{"　".repeat(unit.depth)}{unit.name}</option>
                ))}
              </select>
              <label className="field-label mt-3">组织类型</label>
              <select className="select w-full" value={unitForm.unit_type} onChange={(event) => setUnitForm({ ...unitForm, unit_type: event.target.value })}>
                <option value="company">公司</option>
                <option value="business_unit">事业部</option>
                <option value="department">部门</option>
                <option value="team">小组</option>
              </select>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <input className="input" placeholder="城市" value={unitForm.city} onChange={(event) => setUnitForm({ ...unitForm, city: event.target.value })} />
                <input className="input" placeholder="编制人数" value={unitForm.headcount_plan} onChange={(event) => setUnitForm({ ...unitForm, headcount_plan: event.target.value })} />
              </div>
              <button className="primary-button mt-4 w-full" disabled={busy}>
                <Check size={17} />
                保存组织
              </button>
            </form>
          </div>
        )}

        {orgResumeOpen && (
          <div className="modal-backdrop" onClick={() => setOrgResumeOpen(false)}>
            <form className="modal-panel" onSubmit={uploadOrganizationResumes} onClick={(event) => event.stopPropagation()}>
              <div className="modal-head">
                <div>
                  <h2 className="font-semibold">上传部门员工简历</h2>
                  <p>支持多文件和 ZIP，导入后员工会进入当前组织节点。</p>
                </div>
                <button className="icon-button" type="button" onClick={() => setOrgResumeOpen(false)}>
                  <X size={16} />
                </button>
              </div>
              <label className="upload-drop mt-4">
                <FileText size={28} />
                <strong>{resumeFiles.length ? `已选择 ${resumeFiles.length} 个文件` : "选择员工简历或 ZIP"}</strong>
                <span>上传到：{currentUnit?.name || "未选择组织"}</span>
                <input type="file" multiple accept=".txt,.md,.docx,.pdf,.zip" onChange={(event) => setResumeFiles(Array.from(event.target.files || []))} />
              </label>
              {resumeFiles.length > 0 && (
                <div className="mt-3 flex max-h-24 flex-wrap gap-1.5 overflow-auto">
                  {resumeFiles.map((file) => <span className="chip" key={`${file.name}-${file.size}`}>{file.name}</span>)}
                </div>
              )}
              <button className="primary-button mt-4 w-full" type="submit" disabled={busy || !selectedUnitId || !resumeFiles.length}>
                <Upload size={17} />
                上传并归档员工
              </button>
            </form>
          </div>
        )}

        <div className="hidden">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">组织架构</h2>
              <p className="text-xs text-steel">点击部门查看员工和风险概览</p>
            </div>
            <button className="secondary-button" onClick={() => load()}>
              <RefreshCw size={16} />
            </button>
          </div>
          <div className="mt-4 space-y-1">
            {units.map((unit) => (
              <OrganizationNode key={unit.id} unit={unit} selectedId={selectedUnitId} onSelect={selectUnit} />
            ))}
          </div>
        </div>

        <div className="design-card">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">内部员工转入</h2>
              <p className="mt-1 text-xs text-steel">从人才库候选人建立内部员工档案，默认不占用页面空间。</p>
            </div>
            <button className="primary-button" type="button" onClick={() => setTransferOpen(true)}>
              <Plus size={17} />
              转入内部员工
            </button>
          </div>
          {message && <p className="mt-3 text-sm text-mint">{message}</p>}
        </div>

        {transferOpen && (
        <div className="modal-backdrop" onClick={() => setTransferOpen(false)}>
        <form className="modal-panel" onSubmit={createEmployee} onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <div>
              <h2 className="font-semibold">候选人转内部员工</h2>
              <p>不会复制成两份简历，只建立员工档案并关联原候选人。</p>
            </div>
            <button className="icon-button" type="button" onClick={() => setTransferOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <label className="field-label mt-4">候选人</label>
          <select className="select w-full" value={form.candidate_id} onChange={(event) => setForm({ ...form, candidate_id: Number(event.target.value) })}>
            {candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name_masked} · {candidate.title}</option>)}
          </select>
          <label className="field-label mt-3">所属组织</label>
          <select className="select w-full" value={form.organization_unit_id} onChange={(event) => setForm({ ...form, organization_unit_id: Number(event.target.value) })}>
            {flatUnits.map((unit) => <option key={unit.id} value={unit.id}>{"　".repeat(unit.depth)}{unit.name}</option>)}
          </select>
          <label className="field-label mt-3">当前岗位</label>
          <select className="select w-full" value={form.current_job_id} onChange={(event) => setForm({ ...form, current_job_id: Number(event.target.value) })}>
            <option value={0}>暂不绑定岗位</option>
            {jobs.map((job) => <option key={job.id} value={job.id}>{job.title}</option>)}
          </select>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <input className="input" placeholder="员工编号" value={form.employee_no} onChange={(event) => setForm({ ...form, employee_no: event.target.value })} />
            <input className="input" placeholder="职级，如 P6" value={form.level} onChange={(event) => setForm({ ...form, level: event.target.value })} />
            <input className="input" placeholder="月薪 K" value={form.salary_monthly_k} onChange={(event) => setForm({ ...form, salary_monthly_k: event.target.value })} />
            <input className="input" placeholder="薪资月数" value={form.salary_months} onChange={(event) => setForm({ ...form, salary_months: event.target.value })} />
          </div>
          <label className="field-label mt-3">入职日期</label>
          <input className="input" type="date" value={form.hire_date} onChange={(event) => setForm({ ...form, hire_date: event.target.value })} />
          <button className="primary-button mt-4 w-full" type="submit" disabled={busy || !form.candidate_id}>
            <Plus size={17} />
            {busy ? "转入中" : "转为内部员工"}
          </button>
          <button className="secondary-button mt-2 w-full" type="button" onClick={() => setTransferOpen(false)}>
            取消
          </button>
          {message && <p className="mt-3 text-sm text-mint">{message}</p>}
        </form>
        </div>
        )}

        {employeeImportOpen && (
        <div className="modal-backdrop" onClick={() => setEmployeeImportOpen(false)}>
        <div className="modal-panel" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <div>
              <h2 className="font-semibold">员工台账批量导入</h2>
              <p>支持 CSV/XLSX/XLS，可按员工编号、手机号或邮箱更新已有员工。</p>
            </div>
            <button className="icon-button" type="button" onClick={() => setEmployeeImportOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <label className="secondary-button mt-4 w-full cursor-pointer">
            <Upload size={16} />
            选择员工台账
            <input className="hidden" type="file" accept=".csv,.xlsx,.xls" onChange={(event) => importEmployeeFile(event.target.files)} />
          </label>
          <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs text-steel">
            表头示例：employee_no、name、phone、email、department、current_title、level、salary_monthly_k、salary_months
          </div>
          {employeeImport && (
            <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
              <div className="rounded-md bg-green-50 p-2 text-green-700">新增 {employeeImport.created_count}</div>
              <div className="rounded-md bg-blue-50 p-2 text-blue-700">更新 {employeeImport.updated_count}</div>
              <div className="rounded-md bg-orange-50 p-2 text-orange-700">跳过 {employeeImport.skipped_count}</div>
              <div className="rounded-md bg-red-50 p-2 text-red-700">失败 {employeeImport.failed_count}</div>
            </div>
          )}
        </div>
        </div>
        )}

        <div className="design-card">
          <h2 className="font-semibold">员工台账</h2>
          <p className="mt-1 text-xs text-steel">批量创建或更新内部员工基础档案，可同时带入组织、学历、毕业院校、出生日期和入职时间。</p>
          <button className="secondary-button mt-4 w-full" type="button" onClick={() => setEmployeeImportOpen(true)}>
            <Upload size={16} />
            导入员工台账
          </button>
          {employeeImport && (
            <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
              <div className="rounded-md bg-green-50 p-2 text-green-700">新增 {employeeImport.created_count}</div>
              <div className="rounded-md bg-blue-50 p-2 text-blue-700">更新 {employeeImport.updated_count}</div>
              <div className="rounded-md bg-orange-50 p-2 text-orange-700">跳过 {employeeImport.skipped_count}</div>
              <div className="rounded-md bg-red-50 p-2 text-red-700">失败 {employeeImport.failed_count}</div>
            </div>
          )}
        </div>

        {salaryImportOpen && (
        <div className="modal-backdrop" onClick={() => setSalaryImportOpen(false)}>
        <div className="modal-panel" onClick={(event) => event.stopPropagation()}>
          <div className="modal-head">
            <div>
              <h2 className="font-semibold">薪资表批量导入</h2>
              <p>支持 CSV/XLSX/XLS，按员工编号、手机号、邮箱或姓名匹配员工。</p>
            </div>
            <button className="icon-button" type="button" onClick={() => setSalaryImportOpen(false)}>
              <X size={16} />
            </button>
          </div>
          <label className="secondary-button mt-4 w-full cursor-pointer">
            <Upload size={16} />
            选择薪资表
            <input className="hidden" type="file" accept=".csv,.xlsx,.xls" onChange={(event) => importSalaryFile(event.target.files)} />
          </label>
          <div className="mt-3 rounded-md bg-slate-50 p-3 text-xs text-steel">
            表头示例：employee_no、salary_monthly_k、salary_months、bonus_k、effective_date
          </div>
          {salaryImport && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-md bg-green-50 p-2 text-green-700">更新 {salaryImport.updated_count}</div>
              <div className="rounded-md bg-orange-50 p-2 text-orange-700">跳过 {salaryImport.skipped_count}</div>
              <div className="rounded-md bg-red-50 p-2 text-red-700">失败 {salaryImport.failed_count}</div>
            </div>
          )}
        </div>
        </div>
        )}

        <div className="design-card">
          <h2 className="font-semibold">薪资数据</h2>
          <p className="mt-1 text-xs text-steel">薪资表导入改为弹窗，避免侧栏被低频表单撑高。</p>
          <button className="secondary-button mt-4 w-full" type="button" onClick={() => setSalaryImportOpen(true)}>
            <Upload size={16} />
            导入薪资表
          </button>
          {salaryImport && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-md bg-green-50 p-2 text-green-700">更新 {salaryImport.updated_count}</div>
              <div className="rounded-md bg-orange-50 p-2 text-orange-700">跳过 {salaryImport.skipped_count}</div>
              <div className="rounded-md bg-red-50 p-2 text-red-700">失败 {salaryImport.failed_count}</div>
            </div>
          )}
        </div>
      </aside>

      <main className="space-y-4">
        <div className="toolbar">
          <div>
            <h2 className="font-semibold">{currentUnit ? currentUnit.name : "全部内部人才"}</h2>
            <p className="text-xs text-steel">内部员工独立管理，和外部人才库通过候选人来源关联。</p>
          </div>
          <button className="secondary-button" onClick={() => load(selectedUnitId)}>
            <RefreshCw size={17} />
            刷新
          </button>
          <button className="secondary-button" onClick={batchAnalyze} disabled={busy || !employees.length}>
            <Sparkles size={17} />
            批量分析
          </button>
          <button className="secondary-button" onClick={() => api.exportCsv("employees")}>
            <Download size={17} />
            导出员工
          </button>
        </div>

        <form className="design-card flex flex-col gap-3 md:flex-row md:items-end" onSubmit={searchInternalEmployees}>
          <div className="min-w-0 flex-1">
            <label className="field-label">搜索员工</label>
            <input
              className="input"
              value={employeeQuery}
              onChange={(event) => setEmployeeQuery(event.target.value)}
              placeholder="输入姓名、职位、员工编号或部门"
            />
          </div>
          <button className="primary-button" type="submit">
            <Search size={16} />
            搜索
          </button>
          {employeeQuery && (
            <button className="secondary-button" type="button" onClick={clearInternalEmployeeSearch}>
              清空
            </button>
          )}
        </form>

        <div className="grid gap-3 md:grid-cols-4">
          <KpiMini label="员工总数" value={employeeTotal} hint="当前组织范围" />
          <KpiMini label="有薪资数据" value={employeeOverview.with_compensation} hint={employees.some((item) => item.salary_hidden) ? "薪资已脱敏，仅管理员/经理可见" : "可做薪资分析"} />
          <KpiMini label="已分析" value={employeeOverview.analyzed} hint="岗位/薪资分析" />
          <KpiMini label="平均司龄" value={`${employeeOverview.avg_seniority_years} 年`} hint="按入职时间统计" />
          <KpiMini label="高匹配人才" value={employeeOverview.high_fit} hint="匹配分 >= 80" />
        </div>
        {batchResult && (
          <div className="rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">
            最近批量分析：完成 {batchResult.analyzed_count} 人，跳过 {batchResult.skipped_count} 人
          </div>
        )}

        <div className="data-panel">
          <div className="data-panel-head">
            <div>
              <h2>员工列表</h2>
              <p>默认 20 条分页，列表区独立滚动，避免页面被大批量数据撑长。</p>
            </div>
          </div>
          {employees.length === 0 ? (
            <EmptyState icon={<Building2 size={22} />} text="暂无内部员工，请先从候选人转入或导入员工档案" />
          ) : (
            <div className="data-list">
              {employees.map((employee) => (
                <div className="data-row" key={employee.id}>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{employee.name}</h3>
                      <span className="badge">{employee.current_title}</span>
                      <span className="badge muted">{employmentStatusLabel(employee.employment_status)}</span>
                      {employee.analyses?.[0] && <span className="badge">匹配 {employee.analyses[0].match_score}/100</span>}
                    </div>
                    <p className="mt-1 text-sm text-steel">{employee.organization_unit?.name || employee.department || "未分配部门"} · {employee.level || employee.education || "职级未维护"} · 司龄 {employee.seniority_years ?? "-"} 年 · {employeeSalary(employee)}</p>
                    <TagList tags={employee.tags} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button className="secondary-button" onClick={() => api.getEmployee(employee.id).then(setSelectedEmployee)}>
                      <FileText size={16} />
                      详细简历
                    </button>
                    <button className="primary-button" onClick={() => api.analyzeEmployeeCurrentJob(employee.id).then(() => load(selectedUnitId))}>
                      <Sparkles size={16} />
                      分析
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <PaginationControls
            total={employeeTotal}
            limit={employeeLimit}
            offset={employeeOffset}
            onChange={changeInternalEmployeePage}
          />
        </div>
      </main>
    </section>
  );
}

function EmployeeDetailPage({ employee, onBack, onChanged, backLabel = "返回内部人才" }: { employee: EmployeeProfile; onBack: () => void; onChanged: (employee: EmployeeProfile) => void; backLabel?: string }) {
  const [detail, setDetail] = useState(employee);
  const [analysis, setAnalysis] = useState<EmployeeAnalysis | null>(employee.analyses?.[0] || null);
  const [transfer, setTransfer] = useState<EmployeeRecommendation[]>([]);
  const [replacement, setReplacement] = useState<EmployeeRecommendation[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [units, setUnits] = useState<OrganizationUnit[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [editForm, setEditForm] = useState({
    name: employee.name || "",
    employee_no: employee.employee_no || "",
    phone: employee.phone || "",
    email: employee.email || "",
    organization_unit_id: employee.organization_unit_id || 0,
    current_job_id: employee.current_job_id || 0,
    current_title: employee.current_title || "",
    level: employee.level || "",
    city: employee.city || "",
    employment_status: employee.employment_status || "active",
    hire_date: employee.hire_date || "",
    birth_date: employee.birth_date || "",
    education: employee.education || "",
    graduation_school: employee.graduation_school || "",
    graduation_date: employee.graduation_date || "",
    manager_name: employee.manager_name || "",
    salary_monthly_k: employee.compensation?.salary_monthly_k ? String(employee.compensation.salary_monthly_k) : "",
    salary_annual_k: employee.compensation?.salary_annual_k ? String(employee.compensation.salary_annual_k) : "",
    salary_months: employee.compensation?.salary_months ? String(employee.compensation.salary_months) : "12",
    bonus_k: employee.compensation?.bonus_k ? String(employee.compensation.bonus_k) : ""
  });
  const [busy, setBusy] = useState(false);
  const resume = detail.resume_json || detail.candidate?.resume_json || {};
  const experiences = resumeArray(resume, "experience");
  const projects = resumeArray(resume, "projects");
  const education = resumeArray(resume, "education");
  const flatUnits = useMemo(() => flattenOrganizationUnits(units), [units]);

  useEffect(() => {
    api.getEmployee(employee.id).then((data) => {
      setDetail(data);
      setAnalysis(data.analyses?.[0] || null);
    });
  }, [employee.id]);

  async function reloadDetail() {
    const fresh = await api.getEmployee(detail.id);
    setDetail(fresh);
    setAnalysis(fresh.analyses?.[0] || null);
    onChanged(fresh);
    return fresh;
  }

  async function openEdit() {
    const [tree, jobData, fresh] = await Promise.all([
      api.organizationTree(),
      api.jobs({ scope: "all" }),
      api.getEmployee(detail.id)
    ]);
    setUnits(tree.items);
    setJobs(jobData.items);
    setDetail(fresh);
    setEditForm({
      name: fresh.name || "",
      employee_no: fresh.employee_no || "",
      phone: fresh.phone || "",
      email: fresh.email || "",
      organization_unit_id: fresh.organization_unit_id || 0,
      current_job_id: fresh.current_job_id || 0,
      current_title: fresh.current_title || "",
      level: fresh.level || "",
      city: fresh.city || "",
      employment_status: fresh.employment_status || "active",
      hire_date: fresh.hire_date || "",
      birth_date: fresh.birth_date || "",
      education: fresh.education || "",
      graduation_school: fresh.graduation_school || "",
      graduation_date: fresh.graduation_date || "",
      manager_name: fresh.manager_name || "",
      salary_monthly_k: fresh.compensation?.salary_monthly_k ? String(fresh.compensation.salary_monthly_k) : "",
      salary_annual_k: fresh.compensation?.salary_annual_k ? String(fresh.compensation.salary_annual_k) : "",
      salary_months: fresh.compensation?.salary_months ? String(fresh.compensation.salary_months) : "12",
      bonus_k: fresh.compensation?.bonus_k ? String(fresh.compensation.bonus_k) : ""
    });
    setEditOpen(true);
  }

  async function saveEmployeeEdit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const updated = await api.updateEmployee(detail.id, {
        ...editForm,
        organization_unit_id: editForm.organization_unit_id || null,
        current_job_id: editForm.current_job_id || null
      });
      setDetail(updated);
      setAnalysis(updated.analyses?.[0] || null);
      onChanged(updated);
      setEditOpen(false);
      notify("success", "员工岗位、部门和薪资已更新");
    } finally {
      setBusy(false);
    }
  }

  async function uploadSingleResume(files: FileList | null) {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    try {
      const updated = await api.uploadEmployeeResume(detail.id, file);
      setDetail(updated);
      setAnalysis(updated.analyses?.[0] || null);
      setTransfer([]);
      setReplacement([]);
      onChanged(updated);
      notify("success", "员工简历已解析，标签和档案已更新");
    } finally {
      setBusy(false);
    }
  }

  async function runAnalysis() {
    setBusy(true);
    try {
      const data = await api.analyzeEmployeeCurrentJob(detail.id);
      setAnalysis(data);
      await reloadDetail();
    } finally {
      setBusy(false);
    }
  }

  async function loadTransfer() {
    setBusy(true);
    try {
      const data = await api.recommendEmployeeTransfer(detail.id);
      setTransfer(data.items);
    } finally {
      setBusy(false);
    }
  }

  async function loadReplacement() {
    setBusy(true);
    try {
      const data = await api.recommendEmployeeReplacement(detail.id);
      setReplacement(data.items);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="resume-page">
      <div className="resume-hero">
        <div className="resume-hero-top">
          <button className="secondary-button" onClick={onBack}>
            <ArrowLeft size={17} />
            {backLabel}
          </button>
          <button className="secondary-button" onClick={openEdit}>
            <UserCog size={17} />
            编辑岗位/薪资/部门
          </button>
          <label className={`secondary-button cursor-pointer ${busy ? "opacity-60" : ""}`}>
            <Upload size={17} />
            上传员工简历
            <input className="hidden" type="file" accept=".txt,.md,.docx,.pdf" disabled={busy} onChange={(event) => uploadSingleResume(event.target.files)} />
          </label>
          <button className="primary-button" onClick={runAnalysis} disabled={busy}>
            <Sparkles size={17} />
            当前岗位/薪资分析
          </button>
          <button className="secondary-button" onClick={loadTransfer} disabled={busy}>
            <BriefcaseBusiness size={17} />
            调岗推荐
          </button>
          <button className="secondary-button" onClick={loadReplacement} disabled={busy}>
            <Users size={17} />
            离职替补
          </button>
          <button className="secondary-button" onClick={() => api.employeeReport(detail.id)}>
            <Download size={17} />
            导出报告
          </button>
        </div>
        <div className="resume-profile">
          <div className="resume-avatar">
            <Building2 size={30} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2>{detail.name}</h2>
              <span className="badge">{detail.current_title}</span>
              <span className="badge muted">{employmentStatusLabel(detail.employment_status)}</span>
              {analysis && <span className="badge">岗位匹配 {analysis.match_score}/100</span>}
            </div>
            <p>{detail.organization_unit?.name || detail.department || "未分配部门"} · {detail.level || "职级未维护"} · {employeeSalary(detail)}</p>
            <div className="resume-contact-row">
              <span><Phone size={14} />{detail.phone || "手机未维护"}</span>
              <span><Mail size={14} />{detail.email || "邮箱未维护"}</span>
              <span><BriefcaseBusiness size={14} />{detail.current_job?.title || "未绑定岗位"}</span>
              <span><MapPin size={14} />{detail.city || "城市未维护"}</span>
            </div>
          </div>
        </div>
      </div>

      {editOpen && (
        <div className="modal-backdrop" onClick={() => setEditOpen(false)}>
          <form className="modal-panel max-w-3xl" onSubmit={saveEmployeeEdit} onClick={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h2 className="font-semibold">编辑员工档案</h2>
                <p>维护员工当前岗位、部门、薪资和基础信息；保存后会用于调岗匹配与薪资合理性分析。</p>
              </div>
              <button className="icon-button" type="button" onClick={() => setEditOpen(false)}>
                <X size={16} />
              </button>
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <input className="input" placeholder="姓名" value={editForm.name} onChange={(event) => setEditForm({ ...editForm, name: event.target.value })} />
              <input className="input" placeholder="员工编号" value={editForm.employee_no} onChange={(event) => setEditForm({ ...editForm, employee_no: event.target.value })} />
              <input className="input" placeholder="手机号" value={editForm.phone} onChange={(event) => setEditForm({ ...editForm, phone: event.target.value })} />
              <input className="input" placeholder="邮箱" value={editForm.email} onChange={(event) => setEditForm({ ...editForm, email: event.target.value })} />
              <select className="select w-full" value={editForm.organization_unit_id} onChange={(event) => setEditForm({ ...editForm, organization_unit_id: Number(event.target.value) })}>
                <option value={0}>未分配部门</option>
                {flatUnits.map((unit) => <option key={unit.id} value={unit.id}>{"　".repeat(unit.depth)}{unit.name}</option>)}
              </select>
              <select className="select w-full" value={editForm.current_job_id} onChange={(event) => setEditForm({ ...editForm, current_job_id: Number(event.target.value) })}>
                <option value={0}>不绑定岗位，仅填写岗位名称</option>
                {jobs.map((job) => <option key={job.id} value={job.id}>{job.title} · {job.department || "未填部门"}</option>)}
              </select>
              <input className="input" placeholder="当前岗位/职位" value={editForm.current_title} onChange={(event) => setEditForm({ ...editForm, current_title: event.target.value })} />
              <input className="input" placeholder="职级" value={editForm.level} onChange={(event) => setEditForm({ ...editForm, level: event.target.value })} />
              <input className="input" placeholder="城市" value={editForm.city} onChange={(event) => setEditForm({ ...editForm, city: event.target.value })} />
              <select className="select w-full" value={editForm.employment_status} onChange={(event) => setEditForm({ ...editForm, employment_status: event.target.value })}>
                <option value="active">在职</option>
                <option value="transfer">调岗中</option>
                <option value="leaving">待离职</option>
                <option value="departed">离职</option>
              </select>
              <input className="input" type="date" value={editForm.hire_date} onChange={(event) => setEditForm({ ...editForm, hire_date: event.target.value })} />
              <input className="input" type="date" value={editForm.birth_date} onChange={(event) => setEditForm({ ...editForm, birth_date: event.target.value })} />
              <input className="input" placeholder="学历" value={editForm.education} onChange={(event) => setEditForm({ ...editForm, education: event.target.value })} />
              <input className="input" placeholder="毕业院校" value={editForm.graduation_school} onChange={(event) => setEditForm({ ...editForm, graduation_school: event.target.value })} />
              <input className="input" type="date" value={editForm.graduation_date} onChange={(event) => setEditForm({ ...editForm, graduation_date: event.target.value })} />
              <input className="input" placeholder="直属主管" value={editForm.manager_name} onChange={(event) => setEditForm({ ...editForm, manager_name: event.target.value })} />
              <input className="input" placeholder="月薪 K" value={editForm.salary_monthly_k} onChange={(event) => setEditForm({ ...editForm, salary_monthly_k: event.target.value })} />
              <input className="input" placeholder="年包 K" value={editForm.salary_annual_k} onChange={(event) => setEditForm({ ...editForm, salary_annual_k: event.target.value })} />
              <input className="input" placeholder="薪资月数" value={editForm.salary_months} onChange={(event) => setEditForm({ ...editForm, salary_months: event.target.value })} />
              <input className="input" placeholder="奖金 K" value={editForm.bonus_k} onChange={(event) => setEditForm({ ...editForm, bonus_k: event.target.value })} />
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button className="secondary-button" type="button" onClick={() => setEditOpen(false)}>取消</button>
              <button className="primary-button" disabled={busy} type="submit">
                <Check size={17} />
                保存员工档案
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="resume-layout">
        <main className="resume-main">
          {analysis && (
            <div className="resume-card">
              <ResumeSectionTitle icon={<Sparkles size={18} />} title="AI 分析结论" />
              <p className="resume-summary">{analysis.analysis.summary || "暂无分析摘要"}</p>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                <KpiMini label="岗位匹配" value={`${analysis.match_score}/100`} hint={riskLabel(analysis.risk_level)} />
                <KpiMini label="薪资评分" value={`${analysis.salary_score}/100`} hint={salaryStatusLabel(analysis.salary_status)} />
                <KpiMini label="分析来源" value={analysis.source} hint="规则 + 标签证据" />
              </div>
              <div className="mt-4 grid gap-2">
                {(analysis.analysis.actions || []).map((action, index) => <div className="rounded-md bg-mint/10 px-3 py-2 text-sm text-ink" key={index}>{action}</div>)}
              </div>
              {analysis.analysis.ai_review?.source === "deepseek" && (
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <div className="rounded-md border border-line p-3">
                    <p className="text-xs font-semibold text-steel">AI 证据链</p>
                    <div className="mt-2 space-y-2">
                      {(analysis.analysis.ai_review.evidence || []).slice(0, 5).map((item, index) => (
                        <p className="text-sm text-ink" key={index}>• {item}</p>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-md border border-line p-3">
                    <p className="text-xs font-semibold text-steel">规则修正与风险</p>
                    <div className="mt-2 space-y-2">
                      {[...(analysis.analysis.ai_review.rule_corrections || []), ...(analysis.analysis.ai_review.risks || [])].slice(0, 5).map((item, index) => (
                        <p className="text-sm text-ink" key={index}>• {item}</p>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="resume-card">
            <ResumeSectionTitle icon={<FileText size={18} />} title="个人简介" />
            <p className="resume-summary">{String(resume.summary || detail.raw_text || "暂无简介")}</p>
          </div>
          <div className="resume-card">
            <ResumeSectionTitle icon={<GraduationCap size={18} />} title="教育经历" />
            <ResumeTimeline items={education} empty="暂无结构化教育经历" />
          </div>
          <div className="resume-card">
            <ResumeSectionTitle icon={<BriefcaseBusiness size={18} />} title="工作经历" />
            <ResumeTimeline items={experiences} empty="暂无结构化工作经历" />
          </div>
          <div className="resume-card">
            <ResumeSectionTitle icon={<Database size={18} />} title="项目经历" />
            <ResumeTimeline items={projects} empty="暂无结构化项目经历" />
          </div>
        </main>

        <aside className="resume-side">
          <div className="resume-card">
            <ResumeSectionTitle icon={<UserRound size={18} />} title="员工信息" />
            <div className="mt-4 grid gap-3">
              <InfoItem label="员工编号" value={detail.employee_no || "-"} />
              <InfoItem label="部门" value={detail.organization_unit?.name || detail.department || "-"} />
              <InfoItem label="岗位" value={detail.current_job?.title || detail.current_title || "-"} />
              <InfoItem label="入职时间" value={detail.hire_date || "-"} />
              <InfoItem label="司龄" value={detail.seniority_years != null ? `${detail.seniority_years} 年` : "-"} />
              <InfoItem label="出生日期" value={detail.birth_date || "-"} />
              <InfoItem label="年龄" value={detail.age != null ? `${detail.age} 岁` : "-"} />
              <InfoItem label="学历" value={detail.education || "-"} />
              <InfoItem label="毕业院校" value={detail.graduation_school || "-"} />
              <InfoItem label="毕业时间" value={detail.graduation_date || "-"} />
              <InfoItem label="薪资" value={employeeSalary(detail)} />
              <InfoItem label="来源候选人" value={detail.candidate ? `${detail.candidate.name_masked} #${detail.candidate.id}` : "无关联候选人"} />
            </div>
          </div>
          <SkillRadar tags={detail.tags} />
          <SkillCategoryList tags={detail.tags} />
          <RecommendationList title="调岗推荐" items={transfer} type="transfer" />
          <RecommendationList title="离职替补推荐" items={replacement} type="replacement" />
        </aside>
      </div>
    </section>
  );
}

function OrganizationNode({ unit, selectedId, onSelect, depth = 0 }: { unit: OrganizationUnit; selectedId: number; onSelect: (id: number) => void; depth?: number }) {
  return (
    <div>
      <button className={`w-full rounded-md px-3 py-2 text-left text-sm ${selectedId === unit.id ? "bg-mint text-white" : "hover:bg-slate-100"}`} type="button" onClick={() => onSelect(unit.id)}>
        <span style={{ paddingLeft: depth * 14 }}>{unit.name}</span>
        <span className="float-right text-xs opacity-75">{unit.employee_count || 0}</span>
      </button>
      {unit.children?.map((child) => <OrganizationNode key={child.id} unit={child} selectedId={selectedId} onSelect={onSelect} depth={depth + 1} />)}
    </div>
  );
}

function CompactOrganizationTree({
  units,
  selectedId,
  expandedIds,
  onToggle,
  onSelect,
  depth = 0
}: {
  units: OrganizationUnit[];
  selectedId: number;
  expandedIds: Set<number>;
  onToggle: (id: number) => void;
  onSelect: (id: number) => void;
  depth?: number;
}) {
  if (!units.length) return <div className="rounded-md border border-dashed border-line p-3 text-xs text-steel">暂无组织数据</div>;
  return (
    <div className="space-y-1">
      {units.map((unit) => {
        const children = unit.children || [];
        const hasChildren = children.length > 0;
        const expanded = expandedIds.has(unit.id);
        const active = selectedId === unit.id;
        return (
          <div key={unit.id}>
            <div className={`org-tree-row ${active ? "active" : ""}`} style={{ paddingLeft: depth * 12 }}>
              <button
                aria-label={expanded ? "收起组织" : "展开组织"}
                className="org-tree-toggle"
                disabled={!hasChildren}
                type="button"
                onClick={() => onToggle(unit.id)}
              >
                {hasChildren && <ChevronRight className={expanded ? "rotate-90" : ""} size={15} />}
              </button>
              <button className="org-tree-name" type="button" onClick={() => onSelect(unit.id)}>
                <span className="truncate">{unit.name}</span>
                <span className="badge muted">{unit.employee_count || 0}</span>
              </button>
            </div>
            {hasChildren && expanded && (
              <CompactOrganizationTree units={children} selectedId={selectedId} expandedIds={expandedIds} onToggle={onToggle} onSelect={onSelect} depth={depth + 1} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function RecommendationList({ title, items, type }: { title: string; items: EmployeeRecommendation[]; type: "transfer" | "replacement" }) {
  if (!items.length) return null;
  return (
    <div className="resume-card">
      <ResumeSectionTitle icon={type === "transfer" ? <BriefcaseBusiness size={18} /> : <Users size={18} />} title={title} />
      <div className="mt-4 grid gap-3">
        {items.slice(0, 5).map((item) => (
          <div className="rounded-md border border-line p-3" key={item.id}>
            <div className="flex items-center justify-between gap-3">
              <strong>{type === "transfer" ? item.target_job?.title : item.candidate?.name_masked}</strong>
              <span className="badge">{item.score}/100</span>
            </div>
            <p className="mt-1 text-xs text-steel">{String(item.reason.summary || "基于岗位 JD 与技能标签匹配。")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function flattenOrganizationUnits(units: OrganizationUnit[], depth = 0): (OrganizationUnit & { depth: number })[] {
  return units.flatMap((unit) => [{ ...unit, depth }, ...flattenOrganizationUnits(unit.children || [], depth + 1)]);
}

function organizationPath(units: (OrganizationUnit & { depth: number })[], selectedId: number) {
  const byId = new Map(units.map((unit) => [unit.id, unit]));
  const path: (OrganizationUnit & { depth: number })[] = [];
  let current = selectedId ? byId.get(selectedId) : undefined;
  while (current) {
    path.unshift(current);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return path;
}

function employeeSalary(employee: EmployeeProfile) {
  const compensation = employee.compensation;
  if (employee.salary_hidden) return "薪资已维护（无权限查看）";
  if (!compensation) return "薪资未维护";
  if (compensation.salary_monthly_k) return `${Number(compensation.salary_monthly_k).toFixed(1)}K · ${compensation.salary_months}薪`;
  if (compensation.salary_annual_k) return `年包 ${Number(compensation.salary_annual_k).toFixed(1)}K`;
  return "薪资未维护";
}

function employmentStatusLabel(status: string) {
  return { active: "在职", departed: "离职", leaving: "待离职", transfer: "调岗中" }[status] || status;
}

function salaryStatusLabel(status: string) {
  return { low: "薪资偏低", high: "薪资偏高", reasonable: "薪资合理", unknown: "数据不足" }[status] || status;
}

function riskLabel(risk: string) {
  return { normal: "正常", retention: "保留风险", job_mismatch: "岗位不匹配", cost_mismatch: "成本不匹配", unknown: "未分析" }[risk] || risk;
}

function UploadResumeModal({ onClose, onUploaded }: { onClose: () => void; onUploaded: () => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const supportedResumeFile = (file: File) => /\.(txt|md|docx|pdf|zip)$/i.test(file.name);

  function addFiles(nextFiles: File[]) {
    const accepted = nextFiles.filter(supportedResumeFile);
    setFiles(accepted);
    setMessage(accepted.length === nextFiles.length ? "" : "已自动忽略不支持的文件，仅支持 TXT / MD / DOCX / PDF / ZIP");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!files.length) return;
    setBusy(true);
    setMessage("");
    try {
      const data = await api.uploadResume(files);
      const failed = data.failed_count ? `，失败 ${data.failed_count} 份` : "";
      setMessage(`已解析 ${data.success_count} 份简历${failed}`);
      onUploaded();
      if (!data.failed_count) onClose();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/20 p-4" onClick={onClose}>
      <form className="upload-panel" data-testid="resume-upload-modal" onSubmit={submit} onClick={(event) => event.stopPropagation()}>
        <div className="upload-head">
          <div>
            <h2>简历上传</h2>
            <p>上传后会保存到简历库，AI 自动解析并提取技能标签。</p>
          </div>
          <span className="badge muted">来源：upload</span>
        </div>
        <label
          className="upload-drop"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            addFiles(Array.from(event.dataTransfer.files || []));
          }}
        >
          <FileText size={34} />
          <strong>{files.length ? `已选择 ${files.length} 个文件` : "拖拽简历文件到此处，或点击选择"}</strong>
          <span>支持 TXT / MD / DOCX / PDF / ZIP，可一次选择多个文件</span>
          <input type="file" multiple accept=".txt,.md,.docx,.pdf,.zip" onChange={(event) => addFiles(Array.from(event.target.files || []))} />
        </label>
        {files.length > 0 && (
          <div className="mt-3 flex max-h-28 flex-wrap gap-1.5 overflow-auto">
            {files.map((file) => <span className="chip" key={`${file.name}-${file.size}`}>{file.name}</span>)}
          </div>
        )}
        {message && <div className="mt-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</div>}
        <div className="mt-5 flex justify-end gap-3">
          <button className="secondary-button" data-testid="resume-upload-close" type="button" onClick={onClose}>关闭</button>
          <button className="primary-button" data-testid="resume-upload-submit" type="submit" disabled={!files.length || busy}>
            <Upload size={17} />
            {busy ? "解析中" : "上传并解析"}
          </button>
        </div>
      </form>
    </div>
  );
}

function CandidateDetailPage({ candidate, onBack, onDeleted, backLabel = "返回人才库" }: { candidate: Candidate; onBack: () => void; onDeleted: () => void; backLabel?: string }) {
  const [detail, setDetail] = useState<Candidate>(candidate);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [edit, setEdit] = useState(() => candidateEditFields(candidate));
  const [tagText, setTagText] = useState(formatTagText(candidate.tags || []));
  const [skillTags, setSkillTags] = useState<SkillTag[]>([]);
  const [tagQuery, setTagQuery] = useState("");
  const resume = detail.resume_json || {};
  const experiences = resumeArray(resume, "experience");
  const projects = resumeArray(resume, "projects");
  const education = resumeArray(resume, "education");
  const rawBlocks = cleanResumeBlocks(detail.raw_text || "");
  const tagSuggestions = useMemo(() => {
    const keyword = tagQuery.trim().toLowerCase();
    const items = keyword
      ? skillTags.filter((tag) => [tag.tag, tag.category, ...tag.aliases].join(" ").toLowerCase().includes(keyword))
      : skillTags;
    return items.slice(0, 18);
  }, [skillTags, tagQuery]);

  useEffect(() => {
    api.getCandidate(candidate.id).then((data) => {
      setDetail(data);
      setEdit(candidateEditFields(data));
      setTagText(formatTagText(data.tags));
    });
    api.tags().then((data) => setSkillTags(data.items));
  }, [candidate.id]);

  async function remove() {
    if (!window.confirm("确认删除该候选人及其匹配、流程、BOSS 草稿等关联数据？")) return;
    setBusy(true);
    try {
      await api.deleteCandidate(candidate.id);
      onDeleted();
    } finally {
      setBusy(false);
    }
  }

  async function retryParse() {
    setBusy(true);
    setMessage("正在重新解析简历...");
    try {
      const data = await api.retryParseResume(detail.id);
      setDetail(data.candidate);
      setEdit(candidateEditFields(data.candidate));
      setTagText(formatTagText(data.candidate.tags));
      setMessage(`简历已重新解析，识别到 ${data.candidate.tags.length} 个技能标签。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "简历重新解析失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveBasicInfo(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const data = await api.updateCandidate(detail.id, edit);
      setDetail(data);
      setEdit(candidateEditFields(data));
      setMessage("基础信息已保存");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveTags(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const data = await api.updateCandidateTags(detail.id, parseTagText(tagText));
      setDetail(data);
      setTagText(formatTagText(data.tags));
      setMessage(`技能标签已保存，共 ${data.tags.length} 个`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "标签保存失败");
    } finally {
      setBusy(false);
    }
  }

  function insertSkillTag(tag: SkillTag) {
    setTagText(upsertTagText(tagText, tag.tag, 4));
  }

  return (
    <section className="resume-page">
      <div className="resume-hero">
        <div className="resume-hero-top">
          <button className="secondary-button" onClick={onBack}>
            <ArrowLeft size={17} />
            {backLabel}
          </button>
          <button className="secondary-button" onClick={retryParse} disabled={busy}>
            <RefreshCw size={17} />
            {busy ? "解析中" : "重新解析"}
          </button>
          <button className="secondary-button" onClick={() => api.candidateResume(detail.id)}>
            <Download size={17} />
            导出简历
          </button>
          <button className="secondary-button text-red-700" onClick={remove} disabled={busy}>
            <Trash2 size={17} />
            删除候选人
          </button>
        </div>
        <div className="resume-profile">
          <div className="resume-avatar">
            <UserRound size={30} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2>{detail.name_masked}</h2>
              <span className="badge">{detail.title}</span>
              <span className="badge">简历评分 {resumeScore(detail.tags)}/100</span>
              <span className="badge muted">{detail.experience_analysis.label}</span>
            </div>
            <p>{detail.city || "城市未识别"} · {detail.source} · 负责人 {detail.owner_name}</p>
            <div className="resume-contact-row">
              <span><Phone size={14} />{detail.phone_masked || "手机号未识别"}</span>
              <span><Mail size={14} />{detail.email_masked || "邮箱未识别"}</span>
              <span><UserRound size={14} />{detail.gender || "性别未识别"}</span>
              <span><MapPin size={14} />{detail.city || "城市未识别"}</span>
            </div>
          </div>
        </div>
        {message && <div className="mt-4 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-700">{message}</div>}
      </div>

      <div className="resume-layout">
        <main className="resume-main">
          <div className="resume-card">
            <ResumeSectionTitle icon={<FileText size={18} />} title="个人简介" />
            <p className="resume-summary">{String(resume.summary || rawBlocks.slice(0, 3).join("\n") || "暂无摘要")}</p>
          </div>

          <div className="resume-card">
            <ResumeSectionTitle icon={<GraduationCap size={18} />} title="教育经历" />
            <ResumeTimeline items={education} empty="暂无结构化教育经历" />
          </div>

          <div className="resume-card">
            <ResumeSectionTitle icon={<BriefcaseBusiness size={18} />} title="工作经历" />
            <ResumeTimeline items={experiences} empty="暂无结构化工作经历" />
          </div>

          <div className="resume-card">
            <ResumeSectionTitle icon={<Database size={18} />} title="项目经历" />
            <ResumeTimeline items={projects} empty="暂无结构化项目经历" />
          </div>
        </main>

        <aside className="resume-side">
          <form className="resume-card" onSubmit={saveBasicInfo}>
            <ResumeSectionTitle icon={<UserRound size={18} />} title="基础信息" />
            <div className="mt-4 grid gap-3">
              <input className="input" value={edit.name_masked} onChange={(event) => setEdit({ ...edit, name_masked: event.target.value })} placeholder="姓名" />
              <input className="input" value={edit.title} onChange={(event) => setEdit({ ...edit, title: event.target.value })} placeholder="当前岗位/求职意向" />
              <div className="grid grid-cols-2 gap-2">
                <input className="input" value={edit.gender} onChange={(event) => setEdit({ ...edit, gender: event.target.value })} placeholder="性别" />
                <input className="input" value={edit.city} onChange={(event) => setEdit({ ...edit, city: event.target.value })} placeholder="城市" />
              </div>
              <input className="input" value={edit.phone_masked} onChange={(event) => setEdit({ ...edit, phone_masked: event.target.value })} placeholder="手机号" />
              <input className="input" value={edit.email_masked} onChange={(event) => setEdit({ ...edit, email_masked: event.target.value })} placeholder="邮箱" />
              <textarea className="input min-h-24" value={edit.summary} onChange={(event) => setEdit({ ...edit, summary: event.target.value })} placeholder="个人简介" />
              <button className="primary-button w-full" type="submit" disabled={busy}>
                <Check size={17} />
                保存基础信息
              </button>
              <div className="text-xs text-steel">来源：{detail.source}</div>
            </div>
          </form>

          <div className="resume-card">
            <ResumeSectionTitle icon={<Clock3 size={18} />} title="经验识别" />
            <p className="resume-summary">{detail.experience_analysis.label} · {detail.experience_analysis.basis}</p>
          </div>

          <SkillRadar tags={detail.tags} />
          <form className="resume-card" onSubmit={saveTags}>
            <ResumeSectionTitle icon={<Database size={18} />} title="标签校正" />
            <div className="relative mt-4">
              <Search className="pointer-events-none absolute left-3 top-2.5 text-steel" size={15} />
              <input className="input pl-9" value={tagQuery} onChange={(event) => setTagQuery(event.target.value)} placeholder="搜索标签库" />
            </div>
            <div className="mt-3 flex max-h-28 flex-wrap gap-1.5 overflow-auto">
              {tagSuggestions.map((tag) => (
                <button className="chip" type="button" key={tag.tag} onClick={() => insertSkillTag(tag)}>
                  {tag.tag} · {tag.category}
                </button>
              ))}
            </div>
            <textarea className="input mt-4 min-h-40 font-mono text-xs" value={tagText} onChange={(event) => setTagText(event.target.value)} placeholder={"Java 5\nMySQL 4"} />
            <button className="primary-button mt-3 w-full" type="submit" disabled={busy}>
              <Check size={17} />
              保存技能标签
            </button>
            <p className="mt-2 text-xs text-steel">每行一个标签和 1-5 分；标签必须存在于标签库。</p>
          </form>
          <SkillCategoryList tags={detail.tags} />
        </aside>
      </div>
    </section>
  );
}

function ResumeSectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="resume-section-title">
      <span>{icon}</span>
      <h3>{title}</h3>
    </div>
  );
}

function ResumeTimeline({ items, empty }: { items: Record<string, unknown>[]; empty: string }) {
  if (!items.length) {
    return <div className="resume-empty">{empty}</div>;
  }
  return (
    <div className="resume-timeline">
      {items.map((item, index) => (
        <div className="resume-timeline-item" key={index}>
          <div className="resume-timeline-dot" />
          <div className="min-w-0">
            <div className="resume-timeline-head">
              <h4>{resumeItemTitle(item)}</h4>
              <span>{resumeItemPeriod(item)}</span>
            </div>
            <p>{resumeItemDescription(item)}</p>
            <div className="resume-kv-list">
              {Object.entries(item)
                .filter(([key, value]) => !["title", "company", "school", "name", "description", "period", "start", "end", "date", "time"].includes(key) && value)
                .slice(0, 6)
                .map(([key, value]) => (
                  <span key={key}>{key}: {stringifyResumeValue(value)}</span>
                ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SkillRadar({ tags }: { tags: Candidate["tags"] }) {
  const data = radarData(tags);
  const size = 320;
  const center = size / 2;
  const maxRadius = 112;
  const levels = [0.25, 0.5, 0.75, 1];
  const axes = data.map((item, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / data.length;
    return { ...item, angle, x: center + Math.cos(angle) * maxRadius, y: center + Math.sin(angle) * maxRadius };
  });
  const polygon = axes.map((item) => {
    const radius = maxRadius * (item.value / 5);
    return `${center + Math.cos(item.angle) * radius},${center + Math.sin(item.angle) * radius}`;
  }).join(" ");

  return (
    <div className="resume-card">
      <ResumeSectionTitle icon={<Sparkles size={18} />} title="技能雷达" />
      <svg className="mt-4 h-auto w-full" viewBox={`0 0 ${size} ${size}`} role="img" aria-label="技能标签雷达图">
        {levels.map((level) => (
          <polygon
            key={level}
            points={axes.map((item) => `${center + Math.cos(item.angle) * maxRadius * level},${center + Math.sin(item.angle) * maxRadius * level}`).join(" ")}
            fill="none"
            stroke="#D8DEE6"
            strokeWidth="1"
          />
        ))}
        {axes.map((item) => (
          <line key={item.category} x1={center} y1={center} x2={item.x} y2={item.y} stroke="#D8DEE6" strokeWidth="1" />
        ))}
        <polygon points={polygon} fill="rgba(46,139,125,0.22)" stroke="#2E8B7D" strokeWidth="2" />
        {axes.map((item) => {
          const labelRadius = maxRadius + 26;
          const x = center + Math.cos(item.angle) * labelRadius;
          const y = center + Math.sin(item.angle) * labelRadius;
          return (
            <g key={item.category}>
              <circle cx={center + Math.cos(item.angle) * maxRadius * (item.value / 5)} cy={center + Math.sin(item.angle) * maxRadius * (item.value / 5)} r="4" fill="#2E8B7D" />
              <text x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="fill-steel text-[10px] font-semibold">
                {item.category}
              </text>
              <text x={x} y={y + 12} textAnchor="middle" dominantBaseline="middle" className="fill-ink text-[10px]">
                {item.value.toFixed(1)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function SkillCategoryList({ tags }: { tags: Candidate["tags"] }) {
  const [expanded, setExpanded] = useState(false);
  const sorted = [...tags].sort((a, b) => b.score - a.score || a.tag.localeCompare(b.tag));
  const highScore = sorted.filter((tag) => tag.score >= 4);
  const visible = expanded ? sorted : (highScore.length ? highScore.slice(0, 16) : sorted.slice(0, 8));
  const hiddenCount = Math.max(sorted.length - visible.length, 0);
  return (
    <div className="resume-card">
      <ResumeSectionTitle icon={<Database size={18} />} title="标签明细" />
      <p className="mt-2 text-xs text-steel">数字为熟练度评分，范围 1-5；5/5 表示简历中有较强实践证据。</p>
      <div className="mt-4 flex max-h-40 flex-wrap gap-2 overflow-auto pr-1">
        {visible.map((tag) => (
          <span className="skill-chip" title={tag.category} key={`${tag.category}-${tag.tag}`}>
            <span>{tag.tag}</span>
            <strong>{tag.score}/5</strong>
          </span>
        ))}
      </div>
      {hiddenCount > 0 && (
        <button className="secondary-button mt-4 w-full" type="button" onClick={() => setExpanded(!expanded)}>
          {expanded ? "收起低分标签" : `展开其余 ${hiddenCount} 个标签`}
        </button>
      )}
    </div>
  );
}

function radarData(tags: Candidate["tags"]) {
  const grouped = tags.reduce<Record<string, { total: number; count: number }>>((acc, tag) => {
    const current = acc[tag.category] || { total: 0, count: 0 };
    acc[tag.category] = { total: current.total + tag.score, count: current.count + 1 };
    return acc;
  }, {});
  const items = Object.entries(grouped)
    .map(([category, item]) => ({ category, value: item.total / item.count }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
  while (items.length < 3) {
    items.push({ category: ["通用能力", "专业技能", "工具"][items.length], value: 0 });
  }
  return items;
}

function resumeScore(tags: Candidate["tags"]) {
  if (!tags.length) return 0;
  const top = [...tags].sort((a, b) => b.score - a.score).slice(0, 12);
  return Math.round((top.reduce((sum, tag) => sum + tag.score, 0) / top.length) * 20);
}

function formatTagText(tags: Candidate["tags"]) {
  return tags.map((tag) => `${tag.tag} ${tag.score}`).join("\n");
}

function candidateEditFields(candidate: Candidate) {
  return {
    name_masked: candidate.name_masked || "",
    title: candidate.title || "",
    city: candidate.city || "",
    phone_masked: candidate.phone_masked || "",
    email_masked: candidate.email_masked || "",
    gender: candidate.gender || "",
    summary: String(candidate.resume_json?.summary || "")
  };
}

function parseTagText(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(.+?)[\s,，:：]+([1-5])$/);
      if (!match) throw new Error(`标签格式错误：${line}`);
      return { tag: match[1].trim(), score: Number(match[2]) };
    });
}

function upsertTagText(text: string, tag: string, score: number) {
  const nextLine = `${tag} ${score}`;
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const index = lines.findIndex((line) => line.replace(/[\s,，:：]+[1-5]$/, "") === tag);
  if (index >= 0) {
    lines[index] = nextLine;
  } else {
    lines.push(nextLine);
  }
  return lines.join("\n");
}

function resumeArray(resume: Record<string, unknown>, key: string) {
  const value = resume[key];
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item));
}

function cleanResumeBlocks(text: string) {
  const seen = new Map<string, number>();
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => {
      if (!line) return true;
      const compact = line.replace(/\s/g, "");
      if (/^[A-Za-z0-9+/=_-]{32,}$/.test(compact)) return false;
      const count = seen.get(compact) || 0;
      seen.set(compact, count + 1);
      return count < 1;
    });
  const blocks: string[] = [];
  let current: string[] = [];
  for (const line of lines) {
    if (!line) {
      if (current.length) blocks.push(current.join("\n"));
      current = [];
    } else {
      current.push(line);
    }
  }
  if (current.length) blocks.push(current.join("\n"));
  return blocks.length ? blocks : ["原文包含较多解析噪声，已隐藏。"];
}

function resumeItemTitle(item: Record<string, unknown>) {
  return stringifyResumeValue(item.title || item.company || item.school || item.name || "未命名条目");
}

function resumeItemPeriod(item: Record<string, unknown>) {
  return stringifyResumeValue(item.period || item.date || item.time || [item.start, item.end].filter(Boolean).join(" - "));
}

function resumeItemDescription(item: Record<string, unknown>) {
  const value = item.description || item.summary || item.content || item.detail;
  return stringifyResumeValue(value || "暂无描述");
}

function stringifyResumeValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return value.map(stringifyResumeValue).filter(Boolean).join("、");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${stringifyResumeValue(item)}`)
      .join("；");
  }
  return String(value);
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-steel">{label}</div>
      <div className="mt-1 break-all font-medium text-ink">{value}</div>
    </div>
  );
}

function formatDateTime(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(value?: number) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

function defaultDateTimeLocal() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(10, 0, 0, 0);
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function defaultDate() {
  const date = new Date();
  date.setDate(date.getDate() + 30);
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 10);
}

function formatSalary(offer: OfferRecord) {
  if (offer.salary_min_k && offer.salary_max_k) {
    return `${offer.salary_min_k}-${offer.salary_max_k}K · ${offer.salary_months} 薪`;
  }
  if (offer.salary_min_k || offer.salary_max_k) {
    return `${offer.salary_min_k || offer.salary_max_k}K · ${offer.salary_months} 薪`;
  }
  return "薪资待定";
}

function parseInterviewDimensions(comment: string) {
  const labels = new Set(["岗位匹配", "专业能力", "表达结构", "真实性", "风险控制"]);
  return comment.split(/\r?\n/).flatMap((line) => {
    const match = line.match(/^(.+?)：(\d+)\/100$/);
    return match && labels.has(match[1]) ? [{ label: match[1], value: Number(match[2]) }] : [];
  });
}

function SettingsPage() {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [aiForm, setAiForm] = useState<Partial<AiSettings> & { api_key?: string }>({});
  const [weights, setWeights] = useState<MatchingWeights>({
    skill_match: 75,
    capability: 25,
    skill_overall: 85,
    experience: 15,
    rule: 35,
    ai: 65,
    pending_rule: 35
  });
  const [message, setMessage] = useState("");

  useEffect(() => {
    api.settings().then((data) => {
      setSettings(data);
      setAiForm(data.ai);
      setWeights(data.matching_weights);
    });
  }, []);

  function setWeight(key: keyof MatchingWeights, value: string) {
    setWeights({ ...weights, [key]: Number(value || 0) });
  }

  async function saveAi(event: React.FormEvent) {
    event.preventDefault();
    const data = await api.updateAiSettings(aiForm);
    setAiForm({ ...data, api_key: "" });
    setSettings(settings ? { ...settings, ai: data } : settings);
    setMessage("AI配置已保存");
  }

  async function testAi() {
    await api.testAiSettings();
    setMessage("AI连接正常");
  }

  async function saveWeights(event?: React.FormEvent) {
    event?.preventDefault();
    const data = await api.updateMatchingWeights(weights);
    setWeights(data);
    setSettings(settings ? { ...settings, matching_weights: data } : settings);
    setMessage("匹配权重已保存，下一次岗位匹配会按新权重计算");
  }

  async function autoWeights(profile: "strict" | "balanced" | "growth") {
    const data = await api.autoMatchingWeights(profile);
    setWeights(data);
    setSettings(settings ? { ...settings, matching_weights: data } : settings);
    setMessage("匹配权重已自动配置");
  }

  if (!settings) {
    return <section className="design-page"><div className="empty-state">正在加载系统设置</div></section>;
  }

  return (
    <section className="design-page settings-page space-y-4">
      <div className="toolbar">
        <div>
          <h2>系统设置</h2>
          <p>AI配置、匹配权重和自动配置策略。</p>
        </div>
        {message && <span className="badge good">{message}</span>}
      </div>
      <div className="settings-grid">
        <form className="design-card" onSubmit={saveAi}>
          <h2>AI配置</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <Field label="AI模式">
              <select className="select w-full" value={aiForm.mode || "ai"} onChange={(event) => setAiForm({ ...aiForm, mode: event.target.value })}>
                <option value="ai">真实AI模式</option>
                <option value="local_rules">本地规则模式</option>
              </select>
            </Field>
            <Field label="服务商">
              <select className="select w-full" value={aiForm.provider || "deepseek"} onChange={(event) => setAiForm({ ...aiForm, provider: event.target.value })}>
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI兼容</option>
                <option value="local">本地模型</option>
              </select>
            </Field>
            <Field label="Base URL">
              <input className="input" value={aiForm.base_url || ""} onChange={(event) => setAiForm({ ...aiForm, base_url: event.target.value })} />
            </Field>
            <Field label="模型名称">
              <input className="input" value={aiForm.model || ""} onChange={(event) => setAiForm({ ...aiForm, model: event.target.value })} />
            </Field>
            <Field label={`API Key${aiForm.api_key_configured ? ` · ${aiForm.api_key_masked}` : ""}`}>
              <input className="input" type="password" placeholder={aiForm.api_key_configured ? "已配置，留空则不修改" : "请输入 API Key"} value={aiForm.api_key || ""} onChange={(event) => setAiForm({ ...aiForm, api_key: event.target.value })} />
            </Field>
            <Field label="Temperature">
              <input className="input" type="number" min="0" max="2" step="0.1" value={aiForm.temperature ?? 0.1} onChange={(event) => setAiForm({ ...aiForm, temperature: Number(event.target.value) })} />
            </Field>
          </div>
          <div className="settings-note mt-4">真实AI模式会把 JD 和简历摘要发送到配置的模型服务；调用失败时系统会自动回退到本地规则。</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="primary-button" type="submit">保存AI配置</button>
            <button className="secondary-button" type="button" onClick={testAi}>测试连接</button>
          </div>
        </form>

        <form className="design-card" onSubmit={saveWeights}>
          <h2>匹配权重</h2>
          <div className="mt-4 grid gap-3">
            <WeightInput label="技能命中" value={weights.skill_match} onChange={(value) => setWeight("skill_match", value)} />
            <WeightInput label="熟练度" value={weights.capability} onChange={(value) => setWeight("capability", value)} />
            <WeightInput label="技能综合" value={weights.skill_overall} onChange={(value) => setWeight("skill_overall", value)} />
            <WeightInput label="年限经验" value={weights.experience} onChange={(value) => setWeight("experience", value)} />
            <WeightInput label="规则分" value={weights.rule} onChange={(value) => setWeight("rule", value)} />
            <WeightInput label="AI复核分" value={weights.ai} onChange={(value) => setWeight("ai", value)} />
            <WeightInput label="未复核展示折算" value={weights.pending_rule} onChange={(value) => setWeight("pending_rule", value)} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="primary-button" type="submit">保存权重</button>
            <button className="secondary-button" type="button" onClick={() => autoWeights("strict")}>严格岗位型</button>
            <button className="secondary-button" type="button" onClick={() => autoWeights("balanced")}>平衡默认</button>
            <button className="secondary-button" type="button" onClick={() => autoWeights("growth")}>潜力成长型</button>
          </div>
          <div className="settings-note mt-4">
            当前规则：技能命中 {weights.skill_match}% + 熟练度 {weights.capability}%；有年限时技能综合 {weights.skill_overall}% + 年限经验 {weights.experience}%；AI复核后规则 {weights.rule}% + AI {weights.ai}%。
          </div>
        </form>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label>
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function WeightInput({ label, value, onChange }: { label: string; value: number; onChange: (value: string) => void }) {
  return (
    <label className="settings-weight-row">
      <span>{label}</span>
      <input className="input" type="number" min="0" max="100" value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function MobileTabs({ view, setView, isAdmin, canUseTasks }: { view: View; setView: (view: View) => void; isAdmin: boolean; canUseTasks: boolean }) {
  const tabs: [View, string][] = [["candidates", "人才"], ["organization", "组织与内部人才"], ["jobs", "岗位"], ["pipeline", "流程"], ["interviews", "面试"], ["offers", "Offer"], ["boss", "BOSS"], ["bi", "BI"], ["agent", "AI"], ["settings", "系统设置"]];
  if (canUseTasks) tabs.push(["tasks", "任务"]);
  if (isAdmin) {
    tabs.push(["audit", "日志"]);
    tabs.push(["users", "用户"]);
  }
  return (
    <div className="mobile-module-select mb-4 lg:hidden">
      <select className="select w-full" value={view} onChange={(event) => setView(event.target.value as View)}>
        {tabs.map(([key, label]) => <option value={key} key={key}>{label}</option>)}
      </select>
    </div>
  );
}

function TagList({ tags, limit = 8, compact = false }: { tags: { tag: string; score: number; category: string }[]; limit?: number; compact?: boolean }) {
  const sorted = [...tags].sort((a, b) => b.score - a.score || a.tag.localeCompare(b.tag));
  const visible = sorted.slice(0, limit);
  const hiddenCount = Math.max(0, sorted.length - visible.length);
  return (
    <div className={`${compact ? "tag-list-compact" : "mt-3 flex flex-wrap gap-1.5"}`}>
      {visible.map((tag) => <span className="chip" key={tag.tag}>{tag.tag} · {tag.score}/5</span>)}
      {hiddenCount > 0 && <span className="chip muted">+{hiddenCount}</span>}
    </div>
  );
}

function StatusLine({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between border-b border-line py-2"><span className="text-steel">{label}</span><strong>{value}</strong></div>;
}

function EmptyState({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <AntEmpty className="empty-state" image={AntEmpty.PRESENTED_IMAGE_SIMPLE} description={<span>{icon} {text}</span>} />;
}

function titleFor(view: View) {
  return {
    candidates: "人才库",
    organization: "组织与内部人才",
    internal: "组织与内部人才",
    jobs: "岗位匹配",
    pipeline: "流程看板",
    interviews: "面试管理",
    offers: "Offer 管理",
    boss: "BOSS 半自动闭环",
    bi: "BI 看板",
    agent: "AI 助手",
    settings: "系统设置",
    tasks: "后台任务",
    audit: "操作日志",
    users: "用户管理"
  }[view];
}

function auditActionLabel(action: string) {
  if (action === "view") return "查看";
  return {
    create: "创建",
    update: "更新",
    update_tags: "更新标签",
    delete: "删除",
    close: "关闭",
    restore: "恢复",
    cancel: "取消",
    feedback: "提交反馈",
    enqueue: "加入队列",
    retry: "重新排队",
    agent_tool: "Agent 工具调用"
  }[action] || action;
}

function taskStatusLabel(status: string) {
  return {
    all: "全部",
    queued: "排队中",
    running: "执行中",
    succeeded: "已完成",
    failed: "失败"
  }[status] || status;
}

function taskTypeLabel(type: string) {
  if (type === "backup_export") return "全量备份导出";
  return {
    resume_retry_parse: "简历重新解析"
  }[type] || type;
}

function auditTargetLabel(target: string) {
  return {
    user: "用户",
    candidate: "候选人",
    job: "岗位",
    interview: "面试",
    offer: "Offer",
    background_task: "后台任务",
    agent: "AI Agent"
  }[target] || target;
}

export default App;
