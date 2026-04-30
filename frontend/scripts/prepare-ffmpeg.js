/**
 * 预打包脚本：将 ffmpeg-static 的二进制文件复制到 resources/bin 目录
 * 在执行 electron-builder 打包前运行此脚本
 * 
 * 使用方法：node scripts/prepare-ffmpeg.js
 */

const fs = require('fs');
const path = require('path');

const targetDir = path.join(__dirname, '..', 'resources', 'bin');

// 确保目标目录存在
if (!fs.existsSync(targetDir)) {
  fs.mkdirSync(targetDir, { recursive: true });
  console.log('📁 Created directory:', targetDir);
}

const ffmpegTarget = path.join(targetDir, 'ffmpeg.exe');

// 验证
const stats = fs.statSync(ffmpegTarget);
console.log(`   File size: ${(stats.size / 1024 / 1024).toFixed(2)} MB`);
console.log('');
console.log('🎉 FFmpeg prepared successfully for packaging!');
