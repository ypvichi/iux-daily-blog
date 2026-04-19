// deploy.js — 将 hugo public 输出同步到 ypvichi.github.io 仓库的 iux-daily-blog/ 子目录
// 说明：Git 只能推送「整个仓库某条分支上的提交」，不能不经本地工作区就推到远程子目录。
// 这里使用持久克隆目录：首次 clone，之后仅 pull，无需每次重新克隆。
const { execFileSync } = require('child_process');
const process = require('process');
const path = require('path');
const fs = require('fs');

const repoUrl = 'https://github.com/ypvichi/ypvichi.github.io';
const branch = 'main';
const subdir = 'iux-daily-blog';
/** 目标站仓库的本地克隆（勿提交到本博客仓库，已写入 .gitignore） */
const cloneDir = path.join(__dirname, '.deploy-ypvichi-github-io');

function runGit(args, cwd) {
    execFileSync('git', args, { stdio: 'inherit', cwd });
}

try {
    // `hugo server -D` 会常驻不退出，无法作为脚本前置步骤；`-D` 与 server -D 同样包含草稿并完成完整构建，失败则非零退出。
    console.log('=== Hugo 预检（hugo -D，与 server -D 一致的草稿与构建校验）===');
    execFileSync('hugo', ['-D'], { stdio: 'inherit', cwd: __dirname });

    const distPath = path.join(__dirname, 'public');
    if (!fs.existsSync(distPath)) {
        console.error('hugo 未生成 public 目录');
        process.exit(1);
    }

    const contentPath = path.join(__dirname, 'content');
    const backupPath = path.join(distPath, 'BACKUP');
    if (fs.existsSync(contentPath)) {
        fs.rmSync(backupPath, { recursive: true, force: true });
        fs.cpSync(contentPath, backupPath, { recursive: true });
        console.log('=== 已复制 content → public/BACKUP ===');
    }

    if (!fs.existsSync(cloneDir)) {
        console.log('=== 首次克隆目标仓库 ===');
        runGit(['clone', '--depth', '1', '--branch', branch, repoUrl, cloneDir]);
    } else {
        console.log('=== 拉取目标仓库最新提交 ===');
        runGit(['fetch', 'origin', branch], cloneDir);
        runGit(['checkout', branch], cloneDir);
        runGit(['pull', '--ff-only', 'origin', branch], cloneDir);
    }

    const targetDir = path.join(cloneDir, subdir);
    fs.mkdirSync(targetDir, { recursive: true });

    console.log(`=== 同步构建产物到 ${subdir}/ ===`);
    fs.cpSync(distPath, targetDir, { recursive: true, force: true });

    runGit(['add', '-A'], cloneDir);
    try {
        runGit(['commit', '-m', 'deploy: iux-daily-blog'], cloneDir);
    } catch {
        console.log('=== 无变更，跳过推送 ===');
        process.exit(0);
    }

    console.log('=== 强制推送到远程 ===');
    runGit(['push', '--force', 'origin', branch], cloneDir);
} catch (error) {
    console.error('部署失败:', error.message);
    process.exit(1);
}
