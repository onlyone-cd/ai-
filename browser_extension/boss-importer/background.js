const TASK_STATUS_KEY = "bossImportTaskStatus";

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

async function runBackgroundImport(task) {
  setTaskStatus({ ...task, status: "running", message: "后台任务已启动，可关闭插件窗口" });
  try {
    if (task.operation === "obtained_resume") {
      setTaskStatus({ ...task, status: "running", message: "正在采集已获得简历..." });
      const collected = await sendTabMessage(task.tabId, { type: "collect-obtained-resumes" });
      const sourceTabs = collected?.source_tabs?.length ? `，来源：${collected.source_tabs.join("、")}` : "";
      setTaskStatus({ ...task, status: "running", message: `已采集 ${collected?.chunk_count || 1} 段${sourceTabs}，正在导入系统...` });
      const message = await importResume(task.baseUrl, task.token, collected, "已获得简历导入成功");
      setTaskStatus({ ...task, status: "succeeded", message });
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
  return false;
});
