#!/usr/bin/env node
/**
 * 发送本文件内嵌早报正文，或指定文件的完整内容到 Hiklink（调用 hiklink.js）。
 *
 * 用法:
 *   node message.js              # 发送下方 MESSAGE 常量内容
 *   node message.js ./其它.txt   # 发送该文件全文
 */

const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

/** 默认推送的正文（原 message.js 文件中的早报内容） */
const MESSAGE = `📰 AI 早报速递 | 2026-04-16
============================

📌 原文：2026-04-16

🤖 AI 总结：

2026年4月16日

1.  Google发布Gemini 3.1 Flash TTS模型，优化文本转语音性能。
2.  Google推出macOS版Gemini原生桌面应用，新增屏幕共享功能。
3.  Anthropic为Claude平台启用身份验证机制，以增强安全性。
4.  NVIDIA发布Lyra 2.0模型，支持从单张图像生成可探索的3D世界。
5.  World Labs开源Spark 2.0，实现网页端对亿级多边形3D场景的渲染。
6.  Nucleus AI开源17B参数的Nucleus-Image模型，据称仅激活20亿参数。
7.  Claude Code更新，允许开发者自主配置提示缓存的存活时间。

============================
🔗 原文链接：https://imjuya.github.io/juya-ai-daily/issue-61/
💡 发送 /ainews 随时获取最新资讯`;

function main() {
  const argPath = process.argv[2];
  let content;
  if (argPath) {
    const abs = path.isAbsolute(argPath) ? argPath : path.join(process.cwd(), argPath);
    content = fs.readFileSync(abs, 'utf8');
  } else {
    content = MESSAGE;
  }

  const hiklink = path.join(__dirname, 'hiklink.js');
  execFileSync(process.execPath, [hiklink, '--content', content], {
    stdio: 'inherit',
    maxBuffer: 50 * 1024 * 1024,
  });
}

main();
