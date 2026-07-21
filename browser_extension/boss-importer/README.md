# HireInsight BOSS 简历导入扩展

安装：

1. 打开 Chrome `chrome://extensions/`
2. 开启“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择本目录：`browser_extension/boss-importer`

使用：

1. 在系统 BOSS 页面复制插件 Token
2. 打开 BOSS 直聘岗位列表、沟通列表或候选人简历详情页
3. 点击扩展图标，粘贴 Token
4. 点击“绑定 BOSS 登录态”：扩展会优先使用 `webRequest` 捕获的真实请求 Cookie，并用 `chrome.cookies` 与页面 `__zp_stoken__` 兜底补齐
5. 在岗位列表页点击“同步当前 BOSS 岗位列表”
6. 在简历详情页点击“采集当前页并导入”，或在沟通列表页点击“批量采集沟通列表并导入”

说明：

- 登录态只发送到你在插件中配置的 HireInsight 地址，用于系统侧 BOSS 账号绑定。
- 系统只保存 Cookie 指纹，不保存明文 Cookie。
- 简历/岗位采集会优先使用 BOSS 页面接口响应缓存，采不到结构化内容时再回退到当前页面可见文本。
- 后台导入依赖 BOSS 标签页保持打开。
- 扩展不自动发送 BOSS 消息。
