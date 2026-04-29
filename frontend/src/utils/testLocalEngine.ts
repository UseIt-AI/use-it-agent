/**
 * Local Engine 性能测试脚本
 * 
 * 使用方法：
 * 1. 在浏览器控制台中导入并运行：
 *    import { testLocalEngine } from '@/utils/testLocalEngine';
 *    testLocalEngine();
 * 
 * 2. 或者在组件中调用
 */

const LOCAL_ENGINE_URL = 'http://localhost:8324';

interface TestResult {
  name: string;
  success: boolean;
  duration: number;
  error?: string;
  dataSize?: number;
}

/**
 * 测试截图 API
 */
async function testScreenshot(): Promise<TestResult> {
  const start = performance.now();
  
  try {
    const response = await fetch(`${LOCAL_ENGINE_URL}/api/v1/computer/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        actions: [{ type: 'screenshot' }] 
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const duration = performance.now() - start;
    
    // 检查截图数据
    const actionResults = data.data?.action_results || [];
    const screenshotResult = actionResults.find(
      (r: any) => r.ok && r.result?.type === 'screenshot'
    );
    
    const imageBase64 = screenshotResult?.result?.image_base64 || '';
    
    return {
      name: 'screenshot',
      success: true,
      duration,
      dataSize: imageBase64.length,
    };
  } catch (error: any) {
    return {
      name: 'screenshot',
      success: false,
      duration: performance.now() - start,
      error: error.message,
    };
  }
}

/**
 * 测试屏幕信息 API
 */
async function testScreenInfo(): Promise<TestResult> {
  const start = performance.now();
  
  try {
    const response = await fetch(`${LOCAL_ENGINE_URL}/api/v1/computer/screen`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const duration = performance.now() - start;
    
    return {
      name: 'screen_info',
      success: true,
      duration,
      dataSize: JSON.stringify(data).length,
    };
  } catch (error: any) {
    return {
      name: 'screen_info',
      success: false,
      duration: performance.now() - start,
      error: error.message,
    };
  }
}

/**
 * 测试组合操作（screen_info + screenshot）
 */
async function testCombined(): Promise<TestResult> {
  const start = performance.now();
  
  try {
    const response = await fetch(`${LOCAL_ENGINE_URL}/api/v1/computer/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        actions: [
          { type: 'screen_info' },
          { type: 'screenshot' }
        ] 
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const duration = performance.now() - start;
    
    return {
      name: 'screen_info + screenshot',
      success: true,
      duration,
      dataSize: JSON.stringify(data).length,
    };
  } catch (error: any) {
    return {
      name: 'screen_info + screenshot',
      success: false,
      duration: performance.now() - start,
      error: error.message,
    };
  }
}

/**
 * 测试 Word API（如果可用）
 */
async function testWordSnapshot(): Promise<TestResult> {
  const start = performance.now();
  
  try {
    const response = await fetch(`${LOCAL_ENGINE_URL}/api/v1/word/step`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: 'Write-Host "Hello from PowerShell"',
        language: 'PowerShell',
        timeout: 30,
        return_screenshot: true,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const duration = performance.now() - start;
    
    return {
      name: 'word_simple_code',
      success: data.success !== false,
      duration,
      dataSize: JSON.stringify(data).length,
      error: data.error,
    };
  } catch (error: any) {
    return {
      name: 'word_simple_code',
      success: false,
      duration: performance.now() - start,
      error: error.message,
    };
  }
}

/**
 * 格式化耗时
 */
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms.toFixed(0)}ms`;
  }
  return `${(ms / 1000).toFixed(2)}s`;
}

/**
 * 格式化数据大小
 */
function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes}B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)}KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)}MB`;
}

/**
 * 运行所有测试
 */
export async function testLocalEngine(options?: { 
  url?: string; 
  repeat?: number;
  includeWord?: boolean;
}) {
  const url = options?.url || LOCAL_ENGINE_URL;
  const repeat = options?.repeat || 3;
  const includeWord = options?.includeWord ?? false;
  
  console.log('🧪 ========================================');
  console.log('🧪 Local Engine 性能测试');
  console.log('🧪 ========================================');
  console.log(`📍 URL: ${url}`);
  console.log(`🔄 重复次数: ${repeat}`);
  console.log('');

  const tests = [
    { name: 'screenshot', fn: testScreenshot },
    { name: 'screen_info', fn: testScreenInfo },
    { name: 'combined', fn: testCombined },
  ];
  
  if (includeWord) {
    tests.push({ name: 'word', fn: testWordSnapshot });
  }

  for (const test of tests) {
    console.log(`\n📊 测试: ${test.name}`);
    console.log('─'.repeat(40));
    
    const results: TestResult[] = [];
    
    for (let i = 0; i < repeat; i++) {
      const result = await test.fn();
      results.push(result);
      
      const status = result.success ? '✅' : '❌';
      const sizeInfo = result.dataSize ? ` | 数据: ${formatSize(result.dataSize)}` : '';
      const errorInfo = result.error ? ` | 错误: ${result.error}` : '';
      
      console.log(`  ${status} 第 ${i + 1} 次: ${formatDuration(result.duration)}${sizeInfo}${errorInfo}`);
    }
    
    // 计算统计
    const successResults = results.filter(r => r.success);
    if (successResults.length > 0) {
      const durations = successResults.map(r => r.duration);
      const avg = durations.reduce((a, b) => a + b, 0) / durations.length;
      const min = Math.min(...durations);
      const max = Math.max(...durations);
      
      console.log('─'.repeat(40));
      console.log(`  📈 平均: ${formatDuration(avg)} | 最小: ${formatDuration(min)} | 最大: ${formatDuration(max)}`);
    }
  }

  console.log('\n🧪 ========================================');
  console.log('🧪 测试完成');
  console.log('🧪 ========================================');
}

/**
 * 快速测试（只测一次截图）
 */
export async function quickTest() {
  console.log('⚡ 快速测试 - 单次截图');
  const result = await testScreenshot();
  
  if (result.success) {
    console.log(`✅ 成功! 耗时: ${formatDuration(result.duration)} | 数据: ${formatSize(result.dataSize || 0)}`);
  } else {
    console.log(`❌ 失败! 错误: ${result.error}`);
  }
  
  return result;
}

// 导出到全局，方便在控制台使用
if (typeof window !== 'undefined') {
  (window as any).testLocalEngine = testLocalEngine;
  (window as any).quickTest = quickTest;
  console.log('💡 Local Engine 测试工具已加载');
  console.log('   运行: testLocalEngine() 或 quickTest()');
}
