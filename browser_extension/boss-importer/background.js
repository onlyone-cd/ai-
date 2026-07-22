const TASK_STATUS_KEY = "bossImportTaskStatus";
const REQUIRED_BOSS_COOKIES = ["wt2", "wbg", "zp_at", "__zp_stoken__"];
const ZHIPIN_FILTER = { urls: ["https://zhipin.com/*", "https://*.zhipin.com/*"] };
let lastBossCookieHeader = "";
let lastBossCookieCapturedAt = 0;

function parseCookieHeader(header) {
  const cookies = {};
  String(header || "").split(";").forEach((part) => {
    const index = part.indexOf("=");
    if (index <= 0) return;
    const key = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    if (key && value) cookies[key] = value;
  });
  return cookies;
}

function buildCookieStatus(header) {
  const cookies = parseCookieHeader(header);
  const names = Object.keys(cookies);
  return {
    cookie_header: header || "",
    captured_at: lastBossCookieCapturedAt,
    count: names.length,
    missing_required: REQUIRED_BOSS_COOKIES.filter((name) => !cookies[name]),
    has_stoken: Boolean(cookies.__zp_stoken__),
    names
  };
}

try {
  chrome.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
      const cookie = (details.requestHeaders || []).find((header) => header.name.toLowerCase() === "cookie")?.value || "";
      if (cookie && (cookie.includes("zp_at=") || cookie.includes("wt2=") || cookie.includes("wbg="))) {
        lastBossCookieHeader = cookie;
        lastBossCookieCapturedAt = Date.now();
      }
    },
    ZHIPIN_FILTER,
    ["requestHeaders", "extraHeaders"]
  );
} catch (error) {
  console.warn("BOSS Cookie request listener unavailable", error);
}

function setTaskStatus(patch) {
  const status = {
    task_id: patch.task_id || `task-${Date.now()}`,
    status: patch.status || "running",
    operation: patch.operation || "",
    message: patch.message || "",
    updated_at: new Date().toISOString(),
    ...patch
  };
  chrome.storage.local.set({ [TASK_STATUS_KEY]: status });
  return status;
}

async function sendTabMessage(tabId, message) {
  return chrome.tabs.sendMessage(tabId, message);
}

async function postJson(baseUrl, token, path, payload) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(payload)
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "请求失败");
  return body;
}

async function importResume(baseUrl, token, collected, successPrefix) {
  if (!collected?.raw_text || collected.raw_text.length < 30) throw new Error("未采集到足够的简历正文");
  const body = await postJson(baseUrl, token, "/api/boss/screen-resume/import", collected);
  const name = body.data?.candidate?.name_masked || "候选人";
  return `${successPrefix}：${name}，文本长度 ${body.data?.text_length || collected.raw_text.length}`;
}

async function importCandidateItems(baseUrl, token, items, source) {
  if (!items?.length) return { imported: 0, failed: 0 };
  const body = await postJson(baseUrl, token, "/api/boss/candidates/batch-import", { items, source });
  return {
    imported: body.data?.items?.length || 0,
    failed: body.data?.errors?.length || 0
  };
}

async function uploadResumeFiles(baseUrl, token, files) {
  const unique = [];
  const seen = new Set();
  for (const file of files || []) {
    if (!file?.url || seen.has(file.url)) continue;
    seen.add(file.url);
    unique.push(file);
  }
  if (!unique.length) return { imported: 0, failed: 0, errors: [] };

  const form = new FormData();
  const errors = [];
  for (const file of unique.slice(0, 20)) {
    try {
      const response = await fetch(file.url, { credentials: "include" });
      if (!response.ok) throw new Error(`下载失败 HTTP ${response.status}`);
      const blob = await response.blob();
      if (!blob.size) throw new Error("下载文件为空");
      const filename = file.filename || `boss-resume-${Date.now()}.pdf`;
      form.append("files", blob, filename);
    } catch (error) {
      errors.push({ filename: file.filename || file.url, error: error.message });
    }
  }
  if (![...form.keys()].length) return { imported: 0, failed: errors.length, errors };

  const response = await fetch(`${baseUrl}/api/resume/upload`, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}` },
    body: form
  });
  const body = await response.json();
  if (!response.ok) {
    const uploadErrors = body.details?.errors || body.data?.errors || [{ error: body.error || "上传解析失败" }];
    return { imported: 0, failed: errors.length + uploadErrors.length, errors: [...errors, ...uploadErrors] };
  }
  return {
    imported: body.data?.success_count || body.data?.candidates?.length || 0,
    failed: errors.length + (body.data?.failed_count || body.data?.errors?.length || 0),
    errors: [...errors, ...(body.data?.errors || [])]
  };
}

async function runBackgroundImport(task) {
  setTaskStatus({ ...task, status: "running", message: "后台任务已启动，可关闭插件窗口" });
  try {
    if (task.operation === "obtained_resume") {
      if (task.options?.cookies) {
        setTaskStatus({ ...task, status: "running", message: "已确认 BOSS 登录态，正在通过 BOSS 接口导入已获取简历..." });
        const body = await postJson(task.baseUrl, task.token, "/api/boss/obtained-resumes/import", {
          cookies: task.options.cookies,
          save_account: task.options.save_account !== false,
          limit: task.options.limit || 20,
          labels: task.options.labels || [0],
          interval_sec: task.options.interval_sec || 1.5
        });
        const imported = body.data?.items?.length || 0;
        const failed = body.data?.errors?.length || 0;
        const firstError = body.data?.errors?.[0];
        const errorText = typeof firstError === "string"
          ? firstError
          : (firstError?.error?.message || firstError?.error || firstError?.message || "");
        const suffix = errorText ? `\n失败原因：${String(errorText).slice(0, 180)}` : "";
        setTaskStatus({ ...task, status: imported ? "succeeded" : "failed", message: `BOSS 已获取简历导入完成：成功 ${imported} 份，失败 ${failed} 份${suffix}` });
        return;
      }
      if (task.options?.use_active_account) {
        setTaskStatus({ ...task, status: "running", message: "正在使用已激活 BOSS 账号导入已获取简历..." });
        const body = await postJson(task.baseUrl, task.token, "/api/boss/obtained-resumes/import", {
          limit: task.options.limit || 20,
          labels: task.options.labels || [0],
          interval_sec: task.options.interval_sec || 1.5
        });
        const imported = body.data?.items?.length || 0;
        const failed = body.data?.errors?.length || 0;
        const firstError = body.data?.errors?.[0];
        const errorText = typeof firstError === "string"
          ? firstError
          : (firstError?.error?.message || firstError?.error || firstError?.message || "");
        const suffix = errorText ? `\n失败原因：${String(errorText).slice(0, 180)}` : "";
        setTaskStatus({ ...task, status: imported ? "succeeded" : "failed", message: `BOSS 已获取简历导入完成：成功 ${imported} 份，失败 ${failed} 份${suffix}` });
        return;
      }

      setTaskStatus({ ...task, status: "running", message: "正在采集当前页面已获得简历..." });
      const collected = await sendTabMessage(task.tabId, { type: "collect-obtained-resumes" });
      const sourceTabs = collected?.source_tabs?.length ? `，来源：${collected.source_tabs.join("、")}` : "";
      const items = collected?.items || [];
      const files = collected?.files || [];
      if (items.length || files.length) {
        setTaskStatus({ ...task, status: "running", message: `已采集 ${items.length} 条简历文本、${files.length} 个附件${sourceTabs}，正在导入系统...` });
        const itemResult = await importCandidateItems(task.baseUrl, task.token, items, "extension_obtained_resume");
        const fileResult = await uploadResumeFiles(task.baseUrl, task.token, files);
        const imported = itemResult.imported + fileResult.imported;
        const failed = itemResult.failed + fileResult.failed + (collected?.errors?.length || 0);
        if (!imported) throw new Error(fileResult.errors?.[0]?.error || collected?.errors?.[0]?.error || "未成功导入已获取简历");
        setTaskStatus({ ...task, status: "succeeded", message: `已获取简历导入完成：成功 ${imported} 份，失败 ${failed} 份` });
      } else {
        setTaskStatus({ ...task, status: "running", message: `已采集 ${collected?.chunk_count || 1} 段${sourceTabs}，正在导入系统...` });
        const message = await importResume(task.baseUrl, task.token, collected, "已获得简历导入成功");
        setTaskStatus({ ...task, status: "succeeded", message });
      }
      return;
    }

    if (task.operation === "auto_communication_resumes") {
      setTaskStatus({ ...task, status: "running", message: "正在自动打开沟通列表候选人并采集在线简历..." });
      const collected = await sendTabMessage(task.tabId, {
        type: "auto-collect-communication-resumes",
        options: task.options || { limit: 20 }
      });
      const items = collected?.items || [];
      const errors = collected?.errors || [];
      if (!items.length) throw new Error(errors[0]?.error || "未自动采集到可导入简历");
      setTaskStatus({ ...task, status: "running", message: `已自动采集 ${items.length} 份，失败 ${errors.length} 份，正在导入系统...` });
      const body = await postJson(task.baseUrl, task.token, "/api/boss/candidates/batch-import", { items, source: "extension_auto_list" });
      const imported = body.data?.items?.length || 0;
      const failed = (body.data?.errors?.length || 0) + errors.length;
      setTaskStatus({ ...task, status: "succeeded", message: `自动导入完成：成功 ${imported} 份，失败 ${failed} 份` });
      return;
    }

    throw new Error("未知后台任务");
  } catch (error) {
    setTaskStatus({ ...task, status: "failed", message: `失败：${error.message}` });
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "start-background-import") {
    const task = {
      task_id: `boss-task-${Date.now()}`,
      operation: message.operation,
      tabId: message.tabId,
      baseUrl: String(message.baseUrl || "").replace(/\/$/, ""),
      token: message.token || "",
      options: message.options || {}
    };
    runBackgroundImport(task);
    sendResponse({ ok: true, task_id: task.task_id });
    return true;
  }
  if (message?.type === "get-background-task-status") {
    chrome.storage.local.get([TASK_STATUS_KEY], (saved) => sendResponse(saved[TASK_STATUS_KEY] || null));
    return true;
  }
  if (message?.type === "get-captured-boss-cookie") {
    sendResponse(buildCookieStatus(lastBossCookieHeader));
    return true;
  }
  return false;
});
