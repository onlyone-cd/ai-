async function collectResumeText() {
  const chunks = new Set();
  const resumeRoot = findResumeRoot();
  const target = findScrollTarget(resumeRoot);
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor(target.clientHeight * 0.75), 420);

  for (let top = 0; top <= maxScroll + step; top += step) {
    target.scrollTop = Math.min(top, maxScroll);
    window.scrollTo(0, Math.min(top, document.documentElement.scrollHeight));
    await new Promise((resolve) => setTimeout(resolve, 260));
    const text = normalizeResumeText(resumeRoot.innerText || "");
    if (text) chunks.add(text);
  }

  const rawText = normalizeResumeText([...chunks].join("\n\n"));
  return {
    raw_text: rawText,
    chunk_count: chunks.size,
    text_length: rawText.length,
    page_url: location.href,
    title: document.title
  };
}

function findResumeRoot() {
  const selectors = [
    "[class*='resume']",
    "[class*='geek']",
    "[class*='detail']",
    "[class*='dialog']",
    "[class*='modal']",
    "main",
    "section",
    "article",
    "div"
  ];
  const nodes = [...document.querySelectorAll(selectors.join(","))];
  let best = null;
  let bestScore = -Infinity;

  for (const node of nodes) {
    if (!isVisibleNode(node)) continue;
    const rect = node.getBoundingClientRect();
    if (rect.width < 360 || rect.height < 220) continue;
    const text = (node.innerText || "").trim();
    if (text.length < 120) continue;
    const score = scoreResumeRoot(text, rect);
    if (score > bestScore) {
      best = node;
      bestScore = score;
    }
  }
  return best || document.body;
}

function scoreResumeRoot(text, rect) {
  const includeHits = countMatches(text, /(工作经历|项目经历|教育经历|期望职位|个人优势|资格证书|自我评价|求职状态|学历|经验|负责|熟悉|本科|大专|硕士|博士|会计|开发|运营|销售|设计|测试)/g);
  const noiseHits = countMatches(text, /(BOSS直聘|职位管理|推荐牛人|账号权益|续费VIP|我的客服|招聘规范|招聘数据|道具|工具箱|意向沟通|互动|收藏|转发|举报|不合适|发送|继续沟通)/g);
  const dateHits = countMatches(text, /\d{4}[./-]\d{1,2}\s*[-至]\s*(\d{4}[./-]\d{1,2}|至今|今)/g);
  const contactHits = countMatches(text, /(1[3-9]\d{9}|[\w.+-]+@[\w.-]+)/g);
  const centerPenalty = rect.left < 120 ? 8 : 0;
  const rightPanelPenalty = rect.width > Math.min(window.innerWidth * 0.78, 980) ? 4 : 0;
  return includeHits * 8 + dateHits * 6 + contactHits * 4 + Math.min(text.length / 220, 10) - noiseHits * 5 - centerPenalty - rightPanelPenalty;
}

function countMatches(text, pattern) {
  return ((text || "").match(pattern) || []).length;
}

function isVisibleNode(node) {
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
}

function normalizeResumeText(text) {
  const seen = new Set();
  return String(text || "")
    .replace(/\r/g, "\n")
    .split(/\n+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .filter((line) => !isBossNavigationLine(line))
    .filter((line) => {
      const key = line.replace(/\s+/g, "");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join("\n");
}

function isBossNavigationLine(line) {
  const compact = line.replace(/\s+/g, "");
  if (/^(BOSS直聘|职位管理|推荐牛人|搜索|沟通|意向沟通|互动|牛人管理|道具|工具箱|更多|附件简历|不合适|发送|收藏|转发|举报)$/.test(compact)) return true;
  if (/^(未处理|已处理).*(沟通|会计|开发|岗位)/.test(compact)) return true;
  if (/(招聘规范|账号权益|续费VIP|我的客服|招聘数据|首充礼|隐私保护|平台相关提交|在线浏览牛人简历)/.test(compact)) return true;
  if (/^继续沟通$/.test(compact)) return true;
  return false;
}

async function collectBossCandidates() {
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor(target.clientHeight * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    target.scrollTop = Math.min(top, maxScroll);
    window.scrollTo(0, Math.min(top, document.documentElement.scrollHeight));
    await new Promise((resolve) => setTimeout(resolve, 300));
    for (const text of collectCandidateBlocks()) {
      const key = text.replace(/\s+/g, " ").slice(0, 80);
      if (!seen.has(key)) seen.set(key, text);
    }
  }

  const items = [...seen.values()].slice(0, 80).map((text, index) => ({
    external_id: `boss-${Date.now()}-${index}`,
    name: guessName(text),
    title: guessTitle(text),
    summary: text.slice(0, 260),
    raw_text: text,
    page_url: location.href
  }));
  return { items, count: items.length, page_url: location.href, title: document.title };
}

async function collectBossJobs() {
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor(target.clientHeight * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    target.scrollTop = Math.min(top, maxScroll);
    window.scrollTo(0, Math.min(top, document.documentElement.scrollHeight));
    await new Promise((resolve) => setTimeout(resolve, 300));
    for (const text of collectJobBlocks()) {
      const key = text.replace(/\s+/g, " ").slice(0, 100);
      if (!seen.has(key)) seen.set(key, text);
    }
  }

  const items = [...seen.values()].slice(0, 80).map((text, index) => ({
    external_id: `boss-job-${Date.now()}-${index}`,
    title: guessJobTitle(text),
    city: guessCity(text),
    summary: text.slice(0, 500),
    jd_text: text,
    page_url: location.href
  }));
  return { items, count: items.length, page_url: location.href, title: document.title };
}

function collectCandidateBlocks() {
  const selectors = [
    "[class*='geek']",
    "[class*='card']",
    "[class*='item']",
    "[class*='resume']",
    "li"
  ];
  const nodes = [...document.querySelectorAll(selectors.join(","))];
  const blocks = nodes
    .map((node) => (node.innerText || "").trim())
    .filter((text) => text.length >= 30 && text.length <= 4000)
    .filter((text) => /(简历|求职|经验|本科|专科|硕士|博士|年|岁|沟通|在职|离职|应届|电话|邮箱|@)/.test(text));
  if (blocks.length) return blocks;
  return (document.body.innerText || "")
    .split(/\n{2,}/)
    .map((text) => text.trim())
    .filter((text) => text.length >= 30);
}

function collectJobBlocks() {
  const selectors = [
    "[class*='job']",
    "[class*='position']",
    "[class*='card']",
    "[class*='item']",
    "li"
  ];
  return [...document.querySelectorAll(selectors.join(","))]
    .map((node) => (node.innerText || "").trim())
    .filter((text) => text.length >= 12 && text.length <= 3000)
    .filter((text) => /(招聘|岗位|职位|薪资|经验|学历|本科|大专|Java|前端|后端|产品|运营|会计|销售|工程师|经理|主管|分析师)/.test(text))
    .filter((text) => !/(招聘规范|账号权益|续费VIP|我的客服|推荐牛人|道具|工具箱)/.test(text));
}

function guessName(text) {
  const firstLine = text.split(/\n/).map((line) => line.trim()).find(Boolean) || "BOSS 候选人";
  return firstLine.replace(/[|｜].*$/, "").slice(0, 16) || "BOSS 候选人";
}

function guessTitle(text) {
  const line = text.split(/\n/).find((item) => /(开发|工程师|产品|运营|会计|财务|销售|设计|测试|人事|行政|经理|主管|分析师)/.test(item));
  return (line || "BOSS 候选人").trim().slice(0, 32);
}

function guessJobTitle(text) {
  const line = text.split(/\n/).map((item) => item.trim()).find((item) => /(开发|工程师|产品|运营|会计|财务|销售|设计|测试|人事|行政|经理|主管|分析师|客服)/.test(item));
  return (line || text.split(/\n/)[0] || "BOSS 岗位").replace(/[|｜].*$/, "").slice(0, 32);
}

function guessCity(text) {
  const match = text.match(/(北京|上海|广州|深圳|杭州|南京|苏州|成都|重庆|武汉|西安|郑州|长沙|合肥|厦门|青岛|天津|宁波|无锡|佛山|东莞)/);
  return match?.[1] || "";
}

function findScrollTarget(root = document.body) {
  const rootAncestors = [];
  let current = root;
  while (current && current !== document.body) {
    rootAncestors.push(current);
    current = current.parentElement;
  }
  if (root && root !== document.body) {
    const localScrollable = [root, ...rootAncestors].find((el) => el.scrollHeight - el.clientHeight > 100);
    if (localScrollable) return localScrollable;
  }
  const elements = [root, ...rootAncestors, document.scrollingElement, document.documentElement, document.body, ...document.querySelectorAll("main, section, div")].filter(Boolean);
  return elements.reduce((best, el) => {
    const score = (el.scrollHeight - el.clientHeight) + ((el.innerText || "").length / 20);
    const bestScore = (best.scrollHeight - best.clientHeight) + ((best.innerText || "").length / 20);
    return score > bestScore ? el : best;
  }, document.scrollingElement || document.documentElement);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "collect-resume") {
    collectResumeText().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  if (message?.type === "collect-boss-candidates") {
    collectBossCandidates().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  if (message?.type === "collect-boss-jobs") {
    collectBossJobs().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  return false;
});
