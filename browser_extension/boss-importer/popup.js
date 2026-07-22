const $ = (id) => document.getElementById(id);
let currentPageState = null;

chrome.storage.local.get(["baseUrl", "token", "jobId", "bossImportTaskStatus"], (saved) => {
  if (saved.baseUrl) $("baseUrl").value = saved.baseUrl;
  if (saved.token) $("token").value = saved.token;
  if (saved.jobId) $("jobId").value = saved.jobId;
  if (saved.bossImportTaskStatus?.message) renderTaskStatus(saved.bossImportTaskStatus);
});

document.addEventListener("DOMContentLoaded", refreshPageState);
chrome.tabs?.onActivated?.addListener(refreshPageState);
chrome.tabs?.onUpdated?.addListener((_tabId, changeInfo) => {
  if (changeInfo.status === "complete") refreshPageState();
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.bossImportTaskStatus?.newValue) {
    renderTaskStatus(changes.bossImportTaskStatus.newValue);
  }
});

function saveConfig() {
  const baseUrl = $("baseUrl").value.replace(/\/$/, "");
  const token = $("token").value.trim();
  chrome.storage.local.set({ baseUrl, token, jobId: $("jobId").value });
  return { baseUrl, token };
}

async function getActiveBossTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url || !tab.url.includes("zhipin.com")) {
    throw new Error("请先打开 BOSS 直聘页面");
  }
  return tab;
}

async function inspectActivePage() {
  const tab = await getActiveBossTab();
  return chrome.tabs.sendMessage(tab.id, { type: "inspect-page" });
}

async function refreshPageState() {
  setActionButtons(false);
  renderPageState({ label: "正在识别当前页面", message: "请稍等", page_type: "loading" });
  try {
    currentPageState = await inspectActivePage();
    renderPageState(currentPageState);
    setActionButtons(true, currentPageState);
  } catch (error) {
    currentPageState = null;
    renderPageState({ label: "未连接到 BOSS 页面", message: error.message || "请刷新 BOSS 页面后重试", page_type: "invalid" });
    setActionButtons(true, null);
  }
}

function renderPageState(state) {
  const box = $("pageState");
  box.className = `page-state ${stateClass(state)}`;
  box.querySelector("strong").textContent = state.label || "未识别页面";
  box.querySelector("span").textContent = state.message || "";
}

function stateClass(state) {
  if (state?.can_import_resume || state?.can_import_obtained_resume || state?.can_sync_jobs || state?.can_batch_import_candidates) return "ok";
  if (state?.page_type === "resume" || state?.page_type === "job_list" || state?.page_type === "candidate_list") return "ok";
  if (state?.page_type === "invalid" || state?.is_boss_page === false) return "bad";
  return "warn";
}

function setActionButtons(enabled, state = currentPageState) {
  $("bindCookieBtn").disabled = !enabled || !state?.is_boss_page;
  $("importBtn").disabled = !enabled || !state?.can_import_resume;
  $("obtainedImportBtn").disabled = !enabled || !state?.is_boss_page;
  $("autoListImportBtn").disabled = !enabled || !(state?.can_batch_import_candidates || state?.page_type === "candidate_list");
  $("syncJobsBtn").disabled = !enabled || !state?.can_sync_jobs;
  $("batchImportBtn").disabled = !enabled || !state?.can_batch_import_candidates;
  $("importBtn").title = state?.can_import_resume ? "" : "请打开 BOSS 在线简历详情";
  $("obtainedImportBtn").title = state?.is_boss_page ? "确认已登录 BOSS 后，从 BOSS 接口导入已获取简历" : "请先打开 BOSS 直聘页面";
  $("autoListImportBtn").title = state?.can_batch_import_candidates ? "" : "请打开 BOSS 沟通列表";
  $("syncJobsBtn").title = state?.can_sync_jobs ? "" : "请打开 BOSS 职位管理/岗位列表页";
  $("batchImportBtn").title = state?.can_batch_import_candidates ? "" : "请打开 BOSS 沟通列表或候选人列表";
}

function requirePageCapability(capability, message) {
  if (!currentPageState?.[capability]) throw new Error(message);
}

function renderTaskStatus(task) {
  if (!task?.message) return;
  $("status").textContent = task.message;
}

function sendRuntimeMessage(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(err.message));
      else resolve(response);
    });
  });
}

function mergeCookieHeader(map, header) {
  String(header || "").split(";").forEach((part) => {
    const index = part.indexOf("=");
    if (index <= 0) return;
    const key = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    if (key && value && !map.has(key)) map.set(key, value);
  });
}

function formatCookieHeader(map) {
  const preferred = ["wt2", "wbg", "zp_at", "__zp_stoken__"];
  const keys = [...preferred.filter((key) => map.has(key)), ...[...map.keys()].filter((key) => !preferred.includes(key)).sort()];
  return keys.map((key) => `${key}=${map.get(key)}`).join("; ");
}

async function collectBossLoginCookie(tab) {
  const cookieMap = new Map();
  const sources = [];

  const captured = await sendRuntimeMessage({ type: "get-captured-boss-cookie" }).catch(() => null);
  if (captured?.cookie_header) {
    mergeCookieHeader(cookieMap, captured.cookie_header);
    sources.push("请求头");
  }

  const cookieQueries = [
    { url: tab.url },
    { url: "https://www.zhipin.com/" },
    { url: "https://zhipin.com/" },
    { domain: "zhipin.com" }
  ];
  for (const query of cookieQueries) {
    try {
      const cookies = await chrome.cookies.getAll(query);
      for (const item of cookies) {
        if (item.name && item.value && !cookieMap.has(item.name)) cookieMap.set(item.name, item.value);
      }
      if (cookies.length) sources.push(query.domain ? "Cookie 域" : "Cookie API");
    } catch (_error) {
      // Ignore a failed fallback source and keep the stronger sources.
    }
  }

  if (!cookieMap.has("__zp_stoken__")) {
    try {
      const response = await chrome.tabs.sendMessage(tab.id, { type: "get-boss-stoken" });
      if (response?.stoken) {
        cookieMap.set("__zp_stoken__", response.stoken);
        sources.push("页面 token");
      }
    } catch (_error) {
      // The token is optional for current backend login binding.
    }
  }

  const required = ["wt2", "wbg", "zp_at", "__zp_stoken__"];
  const missing = required.filter((key) => !cookieMap.has(key));
  const cookieText = formatCookieHeader(cookieMap);
  if (cookieText.length < 20 || missing.length === required.length) {
    throw new Error("未读取到有效 BOSS 登录态，请确认已登录招聘端，并刷新 BOSS 页面或点开沟通/推荐后重试");
  }
  return {
    cookieText,
    count: cookieMap.size,
    missing,
    hasStoken: cookieMap.has("__zp_stoken__"),
    sources: [...new Set(sources)]
  };
}

async function startBackgroundImport(operation, options = {}) {
  const { baseUrl, token } = saveConfig();
  const tab = await getActiveBossTab();
  const response = await sendRuntimeMessage({
    type: "start-background-import",
    operation,
    tabId: tab.id,
    baseUrl,
    token,
    options
  });
  if (!response?.ok) throw new Error("后台任务启动失败");
  $("status").textContent = "后台任务已启动，可关闭插件窗口，任务会继续执行。";
}

async function uploadResumePayload(baseUrl, token, collected, successPrefix) {
  if (!collected?.raw_text || collected.raw_text.length < 30) throw new Error("未采集到足够的简历正文");
  const response = await fetch(`${baseUrl}/api/boss/screen-resume/import`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(collected)
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "导入失败");
  const name = body.data.candidate?.name_masked || "候选人";
  $("status").textContent = `${successPrefix}：${name}\n文本长度：${body.data.text_length}`;
}

$("bindCookieBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在读取当前 BOSS 登录态...";

  try {
    const tab = await getActiveBossTab();
    const collected = await collectBossLoginCookie(tab);

    const response = await fetch(`${baseUrl}/api/boss/login/browser-cookie`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        account: new URL(tab.url).hostname,
        label: `浏览器导入 ${new Date().toLocaleString()}`,
        cookie: collected.cookieText,
        cookies: collected.cookieText
      })
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "绑定失败");

    const warning = collected.missing.length ? `\n提醒：缺少 ${collected.missing.join("、")}，如后续 BOSS 接口不可用请刷新 BOSS 后重新绑定。` : "";
    const stokenWarning = collected.hasStoken ? "" : "\n提醒：未检测到 __zp_stoken__，已按会话 Cookie 绑定。";
    $("status").textContent = `登录态已绑定：${body.data.account.account}\n采集来源：${collected.sources.join("、") || "Cookie"}，Cookie ${collected.count} 个。${warning}${stokenWarning}\n系统只保存 Cookie 指纹，不保存明文 Cookie。`;
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("obtainedImportBtn").addEventListener("click", async () => {
  $("status").textContent = "正在读取 BOSS Cookie 并激活账号...";

  try {
    const { baseUrl, token } = saveConfig();
    const tab = await getActiveBossTab();
    const collected = await collectBossLoginCookie(tab);
    if (collected.missing.length) {
      throw new Error(`BOSS Cookie 不完整，缺少 ${collected.missing.join("、")}，请刷新 BOSS 页面后重试`);
    }

    const bindResponse = await fetch(`${baseUrl}/api/boss/login/browser-cookie`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({
        account: new URL(tab.url).hostname,
        label: `浏览器导入 ${new Date().toLocaleString()}`,
        cookies: collected.cookieText
      })
    });
    const bindBody = await bindResponse.json();
    if (!bindResponse.ok) throw new Error(bindBody.error || "BOSS 登录态绑定失败");

    $("status").textContent = `BOSS 账号已激活，正在后台优先采集附件简历...\nCookie 来源：${collected.sources.join("、") || "Cookie"}，共 ${collected.count} 个。`;
    await startBackgroundImport("obtained_resume", { prefer_page_collection: true, use_active_account: true, limit: 20, labels: [4], interval_sec: 1.5 });
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("importBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在采集当前 BOSS 在线简历...";

  try {
    requirePageCapability("can_import_resume", "当前不是在线简历详情，不能采集简历");
    const tab = await getActiveBossTab();
    const collected = await chrome.tabs.sendMessage(tab.id, { type: "collect-resume" });
    $("status").textContent = `已采集 ${collected.chunk_count || 1} 段，正在上传解析...`;
    await uploadResumePayload(baseUrl, token, collected, "在线简历导入成功");
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("autoListImportBtn").addEventListener("click", async () => {
  $("status").textContent = "正在启动后台自动导入沟通列表...";

  try {
    if (!currentPageState?.can_batch_import_candidates && currentPageState?.page_type !== "candidate_list") {
      throw new Error("请先打开 BOSS 沟通列表，再执行自动导入");
    }
    await startBackgroundImport("auto_communication_resumes", { limit: 20 });
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("syncJobsBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在采集当前 BOSS 岗位列表...";

  try {
    requirePageCapability("can_sync_jobs", "当前不是 BOSS 岗位列表页，不能同步岗位");
    const tab = await getActiveBossTab();
    const collected = await chrome.tabs.sendMessage(tab.id, { type: "collect-boss-jobs" });
    const items = collected?.items || [];
    if (!items.length) throw new Error("未采集到岗位，请打开 BOSS 职位管理或岗位列表页面");

    $("status").textContent = `已采集 ${items.length} 个岗位，正在同步...`;
    const response = await fetch(`${baseUrl}/api/boss/jobs/batch-import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ items })
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "岗位同步失败");

    const imported = body.data.items?.length || 0;
    const failed = body.data.errors?.length || 0;
    $("status").textContent = `岗位同步完成：成功 ${imported} 个，失败 ${failed} 个。`;
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("batchImportBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在批量采集当前沟通列表...";

  try {
    requirePageCapability("can_batch_import_candidates", "当前不是沟通/候选人列表页，不能批量导入");
    const tab = await getActiveBossTab();
    const collected = await chrome.tabs.sendMessage(tab.id, { type: "collect-boss-candidates" });
    const items = collected?.items || [];
    if (!items.length) throw new Error("未采集到候选人，请打开 BOSS 沟通列表或简历列表");

    $("status").textContent = `已采集 ${items.length} 人，正在批量导入...`;
    const response = await fetch(`${baseUrl}/api/boss/candidates/batch-import`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ items })
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "批量导入失败");

    const imported = body.data.items?.length || 0;
    const failed = body.data.errors?.length || 0;
    $("status").textContent = `批量导入完成：成功 ${imported} 人，失败 ${failed} 人。`;
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});
