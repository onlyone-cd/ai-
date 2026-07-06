const $ = (id) => document.getElementById(id);

chrome.storage.local.get(["baseUrl", "token", "jobId"], (saved) => {
  if (saved.baseUrl) $("baseUrl").value = saved.baseUrl;
  if (saved.token) $("token").value = saved.token;
  if (saved.jobId) $("jobId").value = saved.jobId;
});

function saveConfig() {
  const baseUrl = $("baseUrl").value.replace(/\/$/, "");
  const token = $("token").value.trim();
  chrome.storage.local.set({ baseUrl, token, jobId: $("jobId").value });
  return { baseUrl, token };
}

$("bindCookieBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在读取当前 BOSS 登录态...";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url || !tab.url.includes("zhipin.com")) throw new Error("请先打开 BOSS 直聘页面");
    const cookies = await chrome.cookies.getAll({ url: tab.url });
    const cookieText = cookies.map((item) => `${item.name}=${item.value}`).join("; ");
    if (cookieText.length < 20) throw new Error("未读取到有效 Cookie，请确认已登录 BOSS");

    const response = await fetch(`${baseUrl}/api/boss/login/browser-cookie`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ account: new URL(tab.url).hostname, cookie: cookieText })
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "绑定失败");

    $("status").textContent = `登录态已绑定：${body.data.account.account}\n系统只保存 Cookie 指纹，不保存明文 Cookie。`;
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("importBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在采集当前 BOSS 页面...";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const collected = await chrome.tabs.sendMessage(tab.id, { type: "collect-resume" });
    if (!collected?.raw_text || collected.raw_text.length < 30) throw new Error("未采集到足够的简历文本");

    $("status").textContent = `已采集 ${collected.chunk_count} 段，正在上传解析...`;
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
    $("status").textContent = `导入成功：${name}\n文本长度：${body.data.text_length}`;
  } catch (error) {
    $("status").textContent = `失败：${error.message}`;
  }
});

$("syncJobsBtn").addEventListener("click", async () => {
  const { baseUrl, token } = saveConfig();
  $("status").textContent = "正在采集当前 BOSS 岗位列表...";

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const collected = await chrome.tabs.sendMessage(tab.id, { type: "collect-boss-jobs" });
    const items = collected?.items || [];
    if (!items.length) throw new Error("未采集到岗位，请先打开 BOSS 职位管理或岗位列表页面");

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
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const collected = await chrome.tabs.sendMessage(tab.id, { type: "collect-boss-candidates" });
    const items = collected?.items || [];
    if (!items.length) throw new Error("未采集到候选人，请先打开 BOSS 沟通列表或简历列表");

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
