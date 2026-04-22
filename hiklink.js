#!/usr/bin/env node
/**
 * Hiklink 消息发送 CLI（与 Postman/截图流程一致：OAuth → 业务 POST）
 *
 * 用法:
 *   node hiklink_card.js --content "消息正文"
 *   node hiklink_card.js -c "消息正文"
 *
 * 必填环境变量:
 *   HICODE_OAUTH_X_HI_CODE_AUTH  获取 token 时请求头 X-HiCode-Authorization 的完整值
 *   OAUTH_CLIENT_ID              截图中的 client_id（如: 智能设计效能组【30615】）
 *   OAUTH_CLIENT_SECRET          截图中的 client_secret（请自行配置，勿提交仓库）
 *   HIKLINK_PUSH_URL             业务接口完整 URL（截图中 https://itapi-tst.hikvision.com/api/ 若被截断，请填平台给出的完整 path）
 *   HIKLINK_BIZ_TYPE             与开放平台 APPID 一致
 *   HIKLINK_OFFICIAL_ACCOUNT_ID  服务号/官方号 ID
 *   HIKLINK_RECEIVER_UID         接收人 shortName（小写），多人逗号分隔
 *
 * 选填:
 *   HICODE_AUTH_URL              默认 https://hicode-auth-hz-tst.hikvision.com/oauth/token
 *   HIKLINK_MSG_TYPE             默认 CARD（与文件名一致；可选 TEXT、SINGLE_IMAGE_TEXT、CARD）
 *   HIKLINK_DIGEST, HIKLINK_TITLE, HIKLINK_LOGO  与截图说明一致
 *   X_CLOUDAPI_CLIENTID          默认 30615
 *   X_CLOUDAPI_APIKEY            如 251008028
 */

const { randomUUID } = require('node:crypto');

function parseArgs(argv) {
  const out = { content: null, help: false };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--help' || a === '-h') {
      out.help = true;
    } else if (a === '--content' || a === '-c') {
      out.content = argv[i + 1] ?? null;
      i += 1;
    } else if (a.startsWith('--content=')) {
      out.content = a.slice('--content='.length);
    } else if (a.startsWith('-c=')) {
      out.content = a.slice('-c='.length);
    }
  }
  return out;
}

function readEnv(name, required) {
  const v = process.env[name];
  if (required && (v == null || String(v).trim() === '')) {
    throw new Error(`缺少环境变量: ${name}`);
  }
  return v;
}

function formEncode(params) {
  const sp = new URLSearchParams();
  for (const [k, val] of Object.entries(params)) {
    if (val === undefined || val === null) continue;
    sp.append(k, String(val));
  }
  return sp;
}

async function fetchOAuthToken() {
  const url = 'https://hicode-auth-hz.hikvision.com/oauth/token';
  const clientId = '30615';
  const clientSecret = 'SXt5wJfV4pTAARkMeA4jcm1faKYbZciFUF8Vmr1zfW50Lo9aryDFgjfrTcvgodT1';

  const body = formEncode({
    grant_type: 'client_credentials',
    client_id: clientId,
    client_secret: clientSecret,
  });

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: body.toString(),
  });

  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { _raw: text };
  }

  if (!res.ok) {
    const err = new Error(`OAuth 失败 HTTP ${res.status}: ${text.slice(0, 500)}`);
    err.status = res.status;
    err.body = data;
    throw err;
  }

  const token = data.access_token;
  if (!token) {
    const err = new Error('OAuth 响应中无 access_token');
    err.body = data;
    throw err;
  }
  return { token, tokenType: data.token_type || 'Bearer', raw: data };
}

async function sendMessage(accessToken, content) {
  const pushUrl = 'https://itapi.hikvision.com/api/';
  const clientId = '30615';
  const apiKey = '251008028';

  const bizType = 251;
  const officialAccountId = '5ec08063-2ea1-4d41-b7c8-c4782faf9301';
  const receiverUid = 'yebo'
  const msgType = 'TEXT'

  const body = formEncode({
    bizType,
    bizNo: randomUUID(),
    officialAccountId,
    receiverUid,
    msgType,
    content
    // digest: readEnv('HIKLINK_DIGEST', false),
    // title: readEnv('HIKLINK_TITLE', false),
    // logo: readEnv('HIKLINK_LOGO', false),
  });

  const res = await fetch(pushUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-HiCode-Authorization': `Bearer ${accessToken}`,
      'X-CloudApi-ClientId': clientId,
      'X-CloudApi-ApiKey': apiKey,
    },
    body: body.toString(),
  });

  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { _raw: text };
  }

  return { ok: res.ok, status: res.status, data, text };
}

async function main() {
  const { content, help } = parseArgs(process.argv);
  if (help) {
    console.log(`用法: node hiklink_card.js --content "消息内容"

敏感配置请用环境变量提供，勿写入命令行历史。
详见文件顶部注释。`);
    process.exit(0);
  }
  if (content == null || content === '') {
    console.error('请提供 --content 或 -c，例如: node hiklink_card.js -c "hello"');
    process.exit(1);
  }

  try {
    const { token, raw: oauthJson } = await fetchOAuthToken();
    console.log('OAuth 成功，已获取 access_token。');
    if (process.env.HIKLINK_DEBUG_OAUTH === '1') {
      console.log(JSON.stringify({ ...oauthJson, access_token: token ? '***' : undefined }, null, 2));
    }

    const result = await sendMessage(
      token,
      content
    );
    if (result.ok) {
      console.log('业务请求成功:');
    } else {
      console.error(`业务请求失败 HTTP ${result.status}:`);
    }
    console.log(
      typeof result.data === 'object' && result.data && '_raw' in result.data
        ? result.data._raw
        : JSON.stringify(result.data, null, 2)
    );
    if (!result.ok) process.exit(1);
  } catch (e) {
    console.error(e.message || e);
    if (e.body) console.error(JSON.stringify(e.body, null, 2));
    process.exit(1);
  }
}

main();
