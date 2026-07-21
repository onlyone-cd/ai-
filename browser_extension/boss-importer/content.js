const RESUME_MARKERS = [
  "\u5de5\u4f5c\u7ecf\u5386",
  "\u9879\u76ee\u7ecf\u5386",
  "\u6559\u80b2\u7ecf\u5386",
  "\u671f\u671b\u804c\u4f4d",
  "\u6c42\u804c\u671f\u671b",
  "\u4e2a\u4eba\u4f18\u52bf",
  "\u8d44\u683c\u8bc1\u4e66",
  "\u81ea\u6211\u8bc4\u4ef7",
  "\u6c42\u804c\u72b6\u6001",
  "\u4e13\u4e1a\u6280\u80fd"
];

const JOB_LIST_MARKERS = [
  "\u804c\u4f4d\u7ba1\u7406",
  "\u5c97\u4f4d\u7ba1\u7406",
  "\u6211\u7684\u804c\u4f4d",
  "\u62db\u8058\u804c\u4f4d",
  "\u804c\u4f4d\u5217\u8868",
  "\u5c97\u4f4d\u5217\u8868",
  "\u53d1\u5e03\u804c\u4f4d",
  "\u5728\u62db\u804c\u4f4d",
  "\u62db\u8058\u4e2d"
];

const NAV_EXACT_WORDS = [
  "BOSS\u76f4\u8058",
  "\u804c\u4f4d\u7ba1\u7406",
  "\u63a8\u8350\u725b\u4eba",
  "\u641c\u7d22",
  "\u6c9f\u901a",
  "\u610f\u5411\u6c9f\u901a",
  "\u4e92\u52a8",
  "\u725b\u4eba\u7ba1\u7406",
  "\u9053\u5177",
  "\u5de5\u5177\u7ba1\u7406",
  "\u66f4\u591a",
  "\u9644\u4ef6\u7b80\u5386",
  "\u4e0d\u5408\u9002",
  "\u53d1\u6d88\u606f",
  "\u6536\u85cf",
  "\u8f6c\u53d1",
  "\u4e3e\u62a5"
];

const NAV_PREFIX_WORDS = [
  "\u672a\u5904\u7406",
  "\u5df2\u5904\u7406",
  "\u5f85\u6c9f\u901a",
  "\u5df2\u6c9f\u901a",
  "\u65b0\u62db\u547c",
  "\u770b\u8fc7\u6211",
  "\u5bf9\u6211\u611f\u5174\u8da3",
  "\u6211\u7684\u5ba2\u670d",
  "\u62db\u8058\u6570\u636e",
  "\u8d26\u53f7\u6743\u76ca",
  "\u7eed\u8d39VIP",
  "\u7ee7\u7eed\u6c9f\u901a"
];

const NAV_CONTAINS_WORDS = [
  "\u62db\u8058\u89c4\u8303",
  "\u9690\u79c1\u4fdd\u62a4",
  "\u5e73\u53f0\u76f8\u5173\u63d0\u4ea4",
  "\u5728\u7ebf\u6d4f\u89c8\u725b\u4eba\u7b80\u5386",
  "\u4e0b\u8f7dAPP",
  "\u626b\u7801\u767b\u5f55",
  "\u5f00\u804a",
  "\u6362\u4e00\u6279",
  "\u7b5b\u9009",
  "\u6392\u5e8f",
  "\u5237\u65b0"
];

const ACTION_ONLY_WORDS = [
  "\u67e5\u770b\u8054\u7cfb\u65b9\u5f0f",
  "\u83b7\u53d6\u8054\u7cfb\u65b9\u5f0f",
  "\u7acb\u5373\u6c9f\u901a",
  "\u7ee7\u7eed\u6c9f\u901a",
  "\u6253\u62db\u547c",
  "\u4ea4\u6362\u5fae\u4fe1",
  "\u7ea6\u9762\u8bd5",
  "\u53d1\u9762\u8bd5\u9080\u8bf7",
  "\u53d1\u9001",
  "\u5f00\u804a",
  "\u6536\u85cf",
  "\u8f6c\u53d1",
  "\u4e3e\u62a5",
  "\u4e0d\u5408\u9002",
  "\u5907\u6ce8",
  "\u6807\u8bb0"
];

const JOB_TITLE_WORDS = [
  "\u5de5\u7a0b\u5e08",
  "\u5f00\u53d1",
  "\u524d\u7aef",
  "\u540e\u7aef",
  "Java",
  "Python",
  "\u6d4b\u8bd5",
  "\u4ea7\u54c1",
  "\u8fd0\u8425",
  "\u4f1a\u8ba1",
  "\u8d22\u52a1",
  "\u9500\u552e",
  "\u5ba2\u670d",
  "\u4eba\u4e8b",
  "\u884c\u653f",
  "\u7ecf\u7406",
  "\u4e3b\u7ba1",
  "\u603b\u76d1",
  "\u67b6\u6784\u5e08",
  "\u5206\u6790\u5e08",
  "\u4e13\u5458"
];

const JOB_FIELD_WORDS = [
  "\u85aa\u8d44",
  "\u6708\u85aa",
  "\u5e74\u85aa",
  "\u7ecf\u9a8c",
  "\u5b66\u5386",
  "\u672c\u79d1",
  "\u5927\u4e13",
  "\u62db\u8058",
  "\u5c97\u4f4d",
  "\u804c\u4f4d",
  "\u804c\u8d23",
  "\u4efb\u804c\u8981\u6c42",
  "\u804c\u4f4d\u63cf\u8ff0",
  "JD",
  "\u5143/\u6708"
];

const CITY_WORDS = [
  "\u5317\u4eac",
  "\u4e0a\u6d77",
  "\u5e7f\u5dde",
  "\u6df1\u5733",
  "\u676d\u5dde",
  "\u5357\u4eac",
  "\u82cf\u5dde",
  "\u6210\u90fd",
  "\u91cd\u5e86",
  "\u6b66\u6c49",
  "\u897f\u5b89",
  "\u90d1\u5dde",
  "\u957f\u6c99",
  "\u5408\u80a5",
  "\u53a6\u95e8",
  "\u9752\u5c9b",
  "\u5929\u6d25",
  "\u5b81\u6ce2",
  "\u65e0\u9521",
  "\u4f5b\u5c71",
  "\u4e1c\u839e"
];

async function collectResumeText() {
  const resumeRoot = findResumeRoot();
  const target = findScrollTarget(resumeRoot);
  const bounds = findResumeColumnBounds(resumeRoot);
  const chunks = new Set();
  const originalTop = target.scrollTop || 0;
  const originalWindowTop = window.scrollY || 0;
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor((target.clientHeight || window.innerHeight) * 0.68), 360);

  try {
    for (let top = 0; top <= maxScroll + step; top += step) {
      scrollElement(target, Math.min(top, maxScroll));
      await sleep(240);
      const text = collectVisibleResumeLines(resumeRoot, bounds).join("\n");
      if (text) chunks.add(text);
    }
  } finally {
    scrollElement(target, originalTop);
    window.scrollTo(0, originalWindowTop);
  }

  const rawText = normalizeResumeText([...chunks].join("\n"));
  if (!hasResumeSignal(rawText)) {
    throw new Error("\u672a\u8bc6\u522b\u5230\u7b80\u5386\u6b63\u6587\uff0c\u8bf7\u6253\u5f00 BOSS \u5019\u9009\u4eba\u7b80\u5386\u8be6\u60c5\u9875\uff0c\u5e76\u786e\u4fdd\u4e2d\u95f4\u7b80\u5386\u533a\u57df\u53ef\u89c1");
  }
  return {
    raw_text: rawText,
    chunk_count: chunks.size,
    text_length: rawText.length,
    page_url: location.href,
    title: document.title
  };
}

async function collectObtainedResumeText() {
  const collected = [];
  const tabs = findResumeTabButtons();
  const originalActive = tabs.find((item) => isActiveTabButton(item.button));

  if (!tabs.length) {
    return collectResumeText();
  }

  for (const item of tabs) {
    if (!item.available) continue;
    item.button.click();
    await sleep(500);
    try {
      const result = await collectResumeText();
      if (result.raw_text) {
        collected.push({ label: item.label, text: result.raw_text, chunks: result.chunk_count || 1 });
      }
    } catch (_error) {
      // Some attachment resumes are image/PDF previews with no selectable text.
    }
  }

  if (originalActive?.button) {
    originalActive.button.click();
    await sleep(200);
  }

  if (!collected.length) {
    return collectResumeText();
  }

  const rawText = normalizeResumeText(collected.map((item) => `【${item.label}】\n${item.text}`).join("\n\n"));
  return {
    raw_text: rawText,
    chunk_count: collected.reduce((sum, item) => sum + item.chunks, 0),
    text_length: rawText.length,
    page_url: location.href,
    title: document.title,
    source_tabs: collected.map((item) => item.label)
  };
}

function findResumeTabButtons() {
  const keywords = ["\u5728\u7ebf\u7b80\u5386", "\u9644\u4ef6\u7b80\u5386", "\u5df2\u83b7\u5f97\u7b80\u5386"];
  const nodes = [...document.querySelectorAll("button,a,div,span")]
    .filter(isVisibleElement)
    .map((node) => {
      const button = node.closest?.("button,a,[role='tab'],[role='button']") || node;
      return { button, label: (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim() };
    })
    .filter((item) => item.label && keywords.some((word) => item.label.includes(word)));
  const seen = new Set();
  return nodes
    .filter((item) => {
      const key = `${item.label}|${Math.round(item.button.getBoundingClientRect().left)}|${Math.round(item.button.getBoundingClientRect().top)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((item) => ({
      ...item,
      available: !item.button.matches?.("[disabled],.disabled,[aria-disabled='true']") && !/\u672a\u83b7\u5f97|\u672a\u5f00\u901a|\u65e0/.test(item.label)
    }));
}

function isActiveTabButton(node) {
  const text = node?.innerText || node?.textContent || "";
  const cls = node?.className || "";
  return /active|selected|current/.test(String(cls)) || text.includes("\u5728\u7ebf\u7b80\u5386");
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
    if (!isVisibleElement(node)) continue;
    const rect = node.getBoundingClientRect();
    if (rect.width < 320 || rect.height < 180) continue;
    const text = (node.innerText || "").trim();
    if (text.length < 80) continue;
    const score = scoreResumeRoot(text, rect);
    if (score > bestScore) {
      best = node;
      bestScore = score;
    }
  }
  return best || document.body;
}

function scoreResumeRoot(text, rect) {
  const includeHits = countTextHits(text, RESUME_MARKERS);
  const noiseHits = countTextHits(text, [...NAV_EXACT_WORDS, ...NAV_PREFIX_WORDS, ...NAV_CONTAINS_WORDS, ...ACTION_ONLY_WORDS]);
  const dateHits = countMatches(text, /\d{4}[./-]\d{1,2}\s*[-\u81f3]\s*(\d{4}[./-]\d{1,2}|\u81f3\u4eca|\u4eca)/g);
  const contactHits = countMatches(text, /(1[3-9]\d{9}|[\w.+-]+@[\w.-]+)/g);
  const geometryPenalty = rect.left < 100 || rect.width > Math.min(window.innerWidth * 0.84, 1080) ? 8 : 0;
  return includeHits * 10 + dateHits * 5 + contactHits * 4 + Math.min(text.length / 240, 10) - noiseHits * 6 - geometryPenalty;
}

function findResumeColumnBounds(root) {
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
  let fallbackLeft = Math.max(170, viewportWidth * 0.13);
  let fallbackRight = Math.min(viewportWidth - 210, viewportWidth * 0.78);
  const rightActionLeft = findPanelBoundary((line) => includesAny(line, ACTION_ONLY_WORDS));
  if (rightActionLeft) fallbackRight = Math.min(fallbackRight, rightActionLeft - 16);

  const candidates = [...document.querySelectorAll("main,section,article,div")]
    .filter(isVisibleElement)
    .map((node) => ({ node, rect: node.getBoundingClientRect(), text: (node.innerText || "").trim() }))
    .filter((item) => item.text.length >= 120 && item.rect.width >= 360 && item.rect.height >= 160)
    .filter((item) => countTextHits(item.text, RESUME_MARKERS) >= 2)
    .filter((item) => item.rect.left >= 80 && item.rect.right <= viewportWidth - 80)
    .filter((item) => !includesAny(item.text.slice(0, 500), ["\u804c\u4f4d\u7ba1\u7406", "\u63a8\u8350\u725b\u4eba", "\u8d26\u53f7\u6743\u76ca", "\u7eed\u8d39VIP", "\u6211\u7684\u5ba2\u670d", "\u62db\u8058\u6570\u636e"]));

  if (candidates.length) {
    candidates.sort((a, b) => scoreResumeRoot(b.text, b.rect) - scoreResumeRoot(a.text, a.rect));
    const rect = candidates[0].rect;
    return {
      left: Math.max(0, rect.left - 12),
      right: Math.min(viewportWidth, rect.right + 12),
      top: Math.max(0, rect.top - 20),
      bottom: Math.min(window.innerHeight || 900, rect.bottom + 20)
    };
  }

  const rootRect = root?.getBoundingClientRect?.();
  if (rootRect && rootRect.width >= 360 && rootRect.left >= 80 && rootRect.right <= viewportWidth - 80) {
    return {
      left: Math.max(0, rootRect.left - 12),
      right: Math.min(viewportWidth, rootRect.right + 12),
      top: 0,
      bottom: window.innerHeight || 900
    };
  }

  return { left: fallbackLeft, right: fallbackRight, top: 0, bottom: window.innerHeight || 900 };
}

function findPanelBoundary(predicate) {
  const rects = collectVisibleTextRects(document.body, predicate);
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
  const rightRects = rects.filter((rect) => rect.left > viewportWidth * 0.58);
  if (!rightRects.length) return null;
  return Math.min(...rightRects.map((rect) => rect.left));
}

function collectVisibleResumeLines(root, bounds) {
  const lines = [];
  const seen = new Set();
  const walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const value = node.nodeValue.replace(/\s+/g, " ").trim();
      if (!value || value.length < 2) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent || !isVisibleElement(parent)) return NodeFilter.FILTER_REJECT;
      if (isInsideControl(parent)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const rects = getTextNodeRects(node);
    if (!rects.some((rect) => isRectInBounds(rect, bounds))) continue;
    for (const line of splitCleanLines(node.nodeValue)) {
      if (isBossNavigationLine(line) || isActionOnlyLine(line)) continue;
      const key = line.replace(/\s+/g, "");
      if (seen.has(key)) continue;
      seen.add(key);
      lines.push(line);
    }
  }
  return lines;
}

function collectVisibleTextRects(root, predicate) {
  const rects = [];
  const walker = document.createTreeWalker(root || document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const text = node.nodeValue.replace(/\s+/g, " ").trim();
    if (!text || !predicate(text)) continue;
    rects.push(...getTextNodeRects(node).filter(isVisibleRect));
  }
  return rects;
}

function getTextNodeRects(node) {
  try {
    const range = document.createRange();
    range.selectNodeContents(node);
    const rects = [...range.getClientRects()];
    range.detach();
    return rects;
  } catch (_error) {
    return [];
  }
}

function isRectInBounds(rect, bounds) {
  if (!isVisibleRect(rect)) return false;
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  return centerX >= bounds.left && centerX <= bounds.right && centerY >= bounds.top - 40 && centerY <= bounds.bottom + 40;
}

function splitCleanLines(text) {
  return String(text || "")
    .replace(/\r/g, "\n")
    .split(/\n| {2,}|\t+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function normalizeResumeText(text) {
  const seen = new Set();
  return splitCleanLines(text)
    .filter((line) => !isBossNavigationLine(line))
    .filter((line) => !isActionOnlyLine(line))
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
  if (NAV_EXACT_WORDS.includes(compact)) return true;
  if (startsWithAny(compact, NAV_PREFIX_WORDS)) return true;
  if (includesAny(compact, NAV_CONTAINS_WORDS)) return true;
  return false;
}

function isActionOnlyLine(line) {
  const compact = line.replace(/\s+/g, "");
  return ACTION_ONLY_WORDS.includes(compact);
}

async function collectBossCandidates() {
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor((target.clientHeight || window.innerHeight) * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    scrollElement(target, Math.min(top, maxScroll));
    await sleep(300);
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
  assertBossJobListPage();
  const target = findScrollTarget();
  const seen = new Map();
  const maxScroll = Math.max(target.scrollHeight - target.clientHeight, 0);
  const step = Math.max(Math.floor((target.clientHeight || window.innerHeight) * 0.8), 520);

  for (let top = 0; top <= maxScroll + step; top += step) {
    scrollElement(target, Math.min(top, maxScroll));
    await sleep(300);
    for (const text of collectJobBlocks()) {
      const key = normalizeJobKey(text);
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

function inspectBossPage() {
  const pageText = (document.body.innerText || "").slice(0, 6000);
  const pageSignal = `${location.href}\n${document.title}\n${pageText}`;
  const resumeRoot = findResumeRoot();
  const resumeRootText = (resumeRoot?.innerText || "").slice(0, 6000);
  const resumeRootSignals = countTextHits(resumeRootText, ["\u5de5\u4f5c\u7ecf\u5386", "\u6559\u80b2\u7ecf\u5386", "\u671f\u671b\u804c\u4f4d", "\u6c42\u804c\u671f\u671b", "\u4e2a\u4eba\u4f18\u52bf", "\u9879\u76ee\u7ecf\u5386"]);
  const resumeSignals = countTextHits(pageSignal, ["\u5de5\u4f5c\u7ecf\u5386", "\u6559\u80b2\u7ecf\u5386", "\u671f\u671b\u804c\u4f4d", "\u6c42\u804c\u671f\u671b", "\u4e2a\u4eba\u4f18\u52bf", "\u9879\u76ee\u7ecf\u5386"]);
  const jobSignals = countTextHits(pageSignal, JOB_LIST_MARKERS) + countTextHits(pageSignal, ["\u62db\u8058\u4e2d", "\u5f85\u5f00\u653e", "\u5df2\u5173\u95ed", "\u804c\u4f4d\u540d\u79f0", "\u62db\u8058\u4eba\u6570", "\u53d1\u5e03\u804c\u4f4d", "\u5237\u65b0\u804c\u4f4d", "\u7f16\u8f91\u804c\u4f4d"]);
  const candidateListSignals = countTextHits(pageSignal, ["\u6c9f\u901a\u5217\u8868", "\u725b\u4eba\u5217\u8868", "\u63a8\u8350\u725b\u4eba", "\u5019\u9009\u4eba", "\u5df2\u6c9f\u901a", "\u610f\u5411\u6c9f\u901a"]);
  const hasJobCards = collectJobBlocks().length > 0;
  const resumeTabs = findResumeTabButtons();
  const hasResumeTabs = resumeTabs.length > 0;
  const hasOnlineResumeModal = countTextHits(`${pageSignal}\n${resumeRootText}`, ["\u671f\u671b\u804c\u4f4d", "\u5de5\u4f5c\u7ecf\u5386"]) >= 2 || hasResumeTabs;
  const hasProfileHeader = /(\d+\s*\u5c81|\u5c81).*(\u5927\u4e13|\u672c\u79d1|\u7855\u58eb|\u535a\u58eb|\u5e74\u4ee5\u4e0a|\u79bb\u804c|\u6d3b\u8dc3)/s.test(`${pageSignal}\n${resumeRootText}`);
  const isBossPage = /(^|\.)zhipin\.com$/i.test(location.hostname);
  const isResumePage = isBossPage && (resumeRootSignals >= 2 || resumeSignals >= 3 || hasOnlineResumeModal || (resumeSignals >= 2 && hasProfileHeader));
  const isJobListPage = isBossPage && !isResumePage && (jobSignals >= 2 || ((/\/job|\/position|position|job/i.test(location.href)) && hasJobCards));
  const isCandidateListPage = isBossPage && !isResumePage && !isJobListPage && candidateListSignals >= 1;
  let pageType = "unknown";
  let label = "\u672a\u8bc6\u522b\u9875\u9762";
  let message = "\u8bf7\u6253\u5f00 BOSS \u5019\u9009\u4eba\u7b80\u5386\u8be6\u60c5\u3001\u6c9f\u901a\u5217\u8868\u6216\u804c\u4f4d\u7ba1\u7406\u9875";
  if (!isBossPage) {
    label = "\u975e BOSS \u9875\u9762";
    message = "\u8bf7\u5148\u6253\u5f00 BOSS \u76f4\u8058\u9875\u9762";
  } else if (isResumePage) {
    pageType = "resume";
    label = "\u5019\u9009\u4eba\u7b80\u5386\u9875";
    message = "\u53ef\u91c7\u96c6\u7b80\u5386\uff1b\u4e0d\u53ef\u540c\u6b65\u5c97\u4f4d\uff0c\u907f\u514d\u628a\u671f\u671b\u804c\u4f4d\u5f53\u6210\u5c97\u4f4d";
  } else if (isJobListPage) {
    pageType = "job_list";
    label = "BOSS \u5c97\u4f4d\u5217\u8868";
    message = "\u53ef\u540c\u6b65\u5c97\u4f4d\u5217\u8868\uff1b\u5f53\u524d\u4e0d\u662f\u7b80\u5386\u8be6\u60c5\u9875";
  } else if (isCandidateListPage) {
    pageType = "candidate_list";
    label = "\u6c9f\u901a/\u5019\u9009\u4eba\u5217\u8868";
    message = "\u53ef\u6279\u91cf\u91c7\u96c6\u5019\u9009\u4eba\uff1b\u5355\u4efd\u7b80\u5386\u8bf7\u6253\u5f00\u7b80\u5386\u8be6\u60c5";
  }
  return {
    is_boss_page: isBossPage,
    page_type: pageType,
    label,
    message,
    can_import_resume: isResumePage,
    can_import_obtained_resume: isResumePage || hasResumeTabs,
    can_sync_jobs: isJobListPage,
    can_batch_import_candidates: isCandidateListPage,
    resume_signals: resumeSignals,
    resume_root_signals: resumeRootSignals,
    job_signals: jobSignals,
    candidate_list_signals: candidateListSignals,
    resume_tabs: resumeTabs.map((item) => ({ label: item.label, available: item.available })),
    url: location.href,
    title: document.title
  };
}

function assertBossJobListPage() {
  const page = inspectBossPage();
  if (page.page_type === "resume") {
    throw new Error("\u5f53\u524d\u662f\u5019\u9009\u4eba\u7b80\u5386\u9875\u3002\u540c\u6b65\u5c97\u4f4d\u8bf7\u6253\u5f00 BOSS \u804c\u4f4d\u7ba1\u7406/\u5c97\u4f4d\u5217\u8868\u9875\uff0c\u4e0d\u80fd\u91c7\u96c6\u5019\u9009\u4eba\u7684\u671f\u671b\u804c\u4f4d");
  }
  if (!page.can_sync_jobs) {
    throw new Error("\u672a\u8bc6\u522b\u5230 BOSS \u5c97\u4f4d\u5217\u8868\u3002\u8bf7\u5148\u6253\u5f00 BOSS \u804c\u4f4d\u7ba1\u7406/\u5c97\u4f4d\u5217\u8868\u9875\u540e\u518d\u540c\u6b65\u5c97\u4f4d");
  }
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
    .map((node) => normalizeResumeText(node.innerText || ""))
    .filter((text) => text.length >= 30 && text.length <= 4000)
    .filter((text) => includesAny(text, ["\u7b80\u5386", "\u6c42\u804c", "\u7ecf\u9a8c", "\u672c\u79d1", "\u4e13\u79d1", "\u7855\u58eb", "\u535a\u58eb", "\u5c81", "\u79bb\u804c", "\u5e94\u5c4a", "\u7535\u8bdd", "\u90ae\u7bb1", "@"]))
    .filter((text) => !looksLikeJobBlock(text));
  if (blocks.length) return blocks;
  return normalizeResumeText(document.body.innerText || "")
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
    .map((node) => normalizeJobText(node.innerText || ""))
    .filter((text) => text.length >= 12 && text.length <= 3000)
    .filter((text) => looksLikeJobBlock(text))
    .filter((text) => !looksLikeResumeDetailBlock(text))
    .filter((text) => !includesAny(text, ["\u62db\u8058\u89c4\u8303", "\u8d26\u53f7\u6743\u76ca", "\u7eed\u8d39VIP", "\u6211\u7684\u5ba2\u670d", "\u63a8\u8350\u725b\u4eba", "\u9053\u5177", "\u5de5\u5177\u7ba1\u7406", "\u671f\u671b\u804c\u4f4d", "\u6c42\u804c\u671f\u671b"]));
}

function normalizeJobText(text) {
  const seen = new Set();
  return splitCleanLines(text)
    .filter((line) => !isBossNavigationLine(line))
    .filter((line) => !includesAny(line, ["\u671f\u671b\u804c\u4f4d", "\u6c42\u804c\u671f\u671b", "\u4e2a\u4eba\u4f18\u52bf", "\u5de5\u4f5c\u7ecf\u5386", "\u6559\u80b2\u7ecf\u5386", "\u9879\u76ee\u7ecf\u5386", "\u8d44\u683c\u8bc1\u4e66"]))
    .filter((line) => {
      const key = line.replace(/\s+/g, "");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .join("\n");
}

function looksLikeJobBlock(text) {
  const hasJobTitle = includesAny(text, JOB_TITLE_WORDS);
  const hasJobFields = includesAny(text, JOB_FIELD_WORDS) || /\d+\s*[kK]/.test(text);
  return hasJobTitle && hasJobFields;
}

function looksLikeResumeDetailBlock(text) {
  return countTextHits(text, ["\u5de5\u4f5c\u7ecf\u5386", "\u6559\u80b2\u7ecf\u5386", "\u671f\u671b\u804c\u4f4d", "\u6c42\u804c\u671f\u671b", "\u4e2a\u4eba\u4f18\u52bf", "\u9879\u76ee\u7ecf\u5386", "\u8d44\u683c\u8bc1\u4e66", "\u79bb\u804c", "\u968f\u65f6\u5230\u5c97"]) >= 2;
}

function normalizeJobKey(text) {
  return text
    .replace(/\s+/g, " ")
    .replace(/\d{4}[./-]\d{1,2}.*$/g, "")
    .slice(0, 120);
}

function guessName(text) {
  const firstLine = text.split(/\n/).map((line) => line.trim()).find(Boolean) || "BOSS \u5019\u9009\u4eba";
  return firstLine.replace(/[|\u00b7].*$/, "").slice(0, 16) || "BOSS \u5019\u9009\u4eba";
}

function guessTitle(text) {
  const line = text.split(/\n/).find((item) => includesAny(item, JOB_TITLE_WORDS));
  return (line || "BOSS \u5019\u9009\u4eba").trim().slice(0, 32);
}

function guessJobTitle(text) {
  const line = text
    .split(/\n/)
    .map((item) => item.trim())
    .find((item) => includesAny(item, JOB_TITLE_WORDS) && !includesAny(item, ["\u671f\u671b\u804c\u4f4d", "\u6c42\u804c\u671f\u671b"]));
  return (line || text.split(/\n/)[0] || "BOSS \u5c97\u4f4d").replace(/[|\u00b7].*$/, "").slice(0, 32);
}

function guessCity(text) {
  return CITY_WORDS.find((city) => text.includes(city)) || "";
}

function hasResumeSignal(text) {
  return countTextHits(text, RESUME_MARKERS) >= 1 && !looksLikeOnlyNavigation(text);
}

function looksLikeOnlyNavigation(text) {
  const lines = splitCleanLines(text);
  if (!lines.length) return true;
  const noise = lines.filter((line) => isBossNavigationLine(line) || isActionOnlyLine(line)).length;
  return noise / lines.length > 0.45;
}

function includesAny(text, words) {
  return words.some((word) => String(text || "").includes(word));
}

function startsWithAny(text, words) {
  return words.some((word) => String(text || "").startsWith(word));
}

function countTextHits(text, words) {
  return words.reduce((count, word) => count + (String(text || "").includes(word) ? 1 : 0), 0);
}

function countMatches(text, pattern) {
  return ((text || "").match(pattern) || []).length;
}

function isVisibleElement(node) {
  const rect = node.getBoundingClientRect();
  const style = window.getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
}

function isVisibleRect(rect) {
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 900;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1200;
  return rect.width > 0 && rect.height > 0 && rect.bottom >= 0 && rect.top <= viewportHeight && rect.right >= 0 && rect.left <= viewportWidth;
}

function isInsideControl(node) {
  return Boolean(node.closest("button,input,textarea,select,nav,aside,[role='button'],[role='navigation']"));
}

function findScrollTarget(root = document.body) {
  const candidates = [root, document.scrollingElement, document.documentElement, document.body, ...document.querySelectorAll("main, section, div")]
    .filter(Boolean)
    .filter((el, index, list) => list.indexOf(el) === index)
    .filter((el) => el.scrollHeight - el.clientHeight > 80);
  if (!candidates.length) return document.scrollingElement || document.documentElement;
  return candidates.reduce((best, el) => {
    const text = el.innerText || "";
    const score = (el.scrollHeight - el.clientHeight) + countTextHits(text, RESUME_MARKERS) * 600 + Math.min(text.length / 20, 500);
    const bestText = best.innerText || "";
    const bestScore = (best.scrollHeight - best.clientHeight) + countTextHits(bestText, RESUME_MARKERS) * 600 + Math.min(bestText.length / 20, 500);
    return score > bestScore ? el : best;
  }, candidates[0]);
}

function scrollElement(target, top) {
  if (target === document.scrollingElement || target === document.documentElement || target === document.body) {
    window.scrollTo(0, top);
    return;
  }
  target.scrollTop = top;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "collect-resume") {
    collectResumeText().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  if (message?.type === "collect-obtained-resumes") {
    collectObtainedResumeText().then(sendResponse).catch((error) => sendResponse({ error: error.message }));
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
  if (message?.type === "inspect-page") {
    Promise.resolve(inspectBossPage()).then(sendResponse).catch((error) => sendResponse({ error: error.message }));
    return true;
  }
  return false;
});
