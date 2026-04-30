/**
 * Screenshot 压缩工具
 * 将 base64 截图压缩为指定分辨率的 JPEG 格式
 */

export interface CompressionOptions {
  maxWidth?: number;
  maxHeight?: number;
  quality?: number; // 0-1
  format?: 'jpeg' | 'webp';
}

/**
 * 压缩 base64 格式的截图
 * @param base64Image - base64 格式的图片数据
 * @param options - 压缩选项
 * @returns 压缩后的 Blob 对象
 */
/**
 * 确保 base64 字符串有正确的 data URL 前缀
 */
function ensureDataUrl(base64Image: string): string {
  // 如果已经有 data: 前缀，直接返回
  if (base64Image.startsWith('data:')) {
    return base64Image;
  }
  
  // 检测图片格式（通过 base64 头部特征）
  // PNG: iVBORw0KGgo
  // JPEG: /9j/
  // GIF: R0lGOD
  // WebP: UklGR
  
  let mimeType = 'image/png'; // 默认 PNG
  
  if (base64Image.startsWith('/9j/')) {
    mimeType = 'image/jpeg';
  } else if (base64Image.startsWith('R0lGOD')) {
    mimeType = 'image/gif';
  } else if (base64Image.startsWith('UklGR')) {
    mimeType = 'image/webp';
  } else if (base64Image.startsWith('iVBORw0KGgo')) {
    mimeType = 'image/png';
  }
  
  console.log('[Compressor] 🔧 Adding data URL prefix, detected type:', mimeType);
  return `data:${mimeType};base64,${base64Image}`;
}

export async function compressScreenshot(
  base64Image: string,
  options: CompressionOptions = {}
): Promise<Blob> {
  const {
    maxWidth = 1920,
    maxHeight = 1080,
    quality = 0.8,
    format = 'jpeg'
  } = options;

  console.log('[Compressor] 🗜️ Starting compression...', {
    maxWidth,
    maxHeight,
    quality,
    format,
    inputLength: base64Image.length,
    hasDataPrefix: base64Image.startsWith('data:'),
    preview: base64Image.substring(0, 30)
  });

  // 确保有正确的 data URL 前缀
  const imageDataUrl = ensureDataUrl(base64Image);
  console.log('[Compressor] 🔧 Data URL ready, length:', imageDataUrl.length);

  return new Promise((resolve, reject) => {
    // 创建 Image 对象
    const img = new Image();
    
    img.onload = () => {
      try {
        console.log('[Compressor] ✅ Image loaded:', {
          originalWidth: img.width,
          originalHeight: img.height
        });
        
        // 计算压缩后的尺寸（保持宽高比）
        let { width, height } = img;
        
        if (width > maxWidth || height > maxHeight) {
          const ratio = Math.min(maxWidth / width, maxHeight / height);
          width = Math.floor(width * ratio);
          height = Math.floor(height * ratio);
          console.log('[Compressor] 📐 Resizing to:', { width, height, ratio });
        } else {
          console.log('[Compressor] ℹ️ No resize needed');
        }
        
        // 创建 canvas 进行压缩
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          console.error('[Compressor] ❌ Failed to get canvas context');
          reject(new Error('Failed to get canvas context'));
          return;
        }
        
        // 绘制图片
        ctx.drawImage(img, 0, 0, width, height);
        console.log('[Compressor] ✅ Image drawn to canvas');
        
        // 转换为 Blob
        canvas.toBlob(
          (blob) => {
            if (blob) {
              console.log('[Compressor] ✅ Blob created:', {
                size: blob.size,
                type: blob.type
              });
              resolve(blob);
            } else {
              console.error('[Compressor] ❌ Failed to create blob');
              reject(new Error('Failed to create blob'));
            }
          },
          `image/${format}`,
          quality
        );
      } catch (error) {
        console.error('[Compressor] ❌ Error during compression:', error);
        reject(error);
      }
    };
    
    img.onerror = (error) => {
      console.error('[Compressor] ❌ Failed to load image:', error);
      console.error('[Compressor] ❌ Image src preview:', imageDataUrl.substring(0, 100));
      reject(new Error('Failed to load image'));
    };
    
    // 设置图片源（使用处理后的 data URL）
    img.src = imageDataUrl;
    console.log('[Compressor] 🖼️ Image source set, waiting for load...');
  });
}

/**
 * 批量压缩截图
 * @param base64Images - base64 格式的图片数组
 * @param options - 压缩选项
 * @returns 压缩后的 Blob 数组
 */
export async function compressScreenshots(
  base64Images: string[],
  options?: CompressionOptions
): Promise<Blob[]> {
  const promises = base64Images.map(img => compressScreenshot(img, options));
  return Promise.all(promises);
}

/**
 * 获取压缩后的文件大小（KB）
 */
export function getBlobSizeKB(blob: Blob): number {
  return Math.round(blob.size / 1024);
}

/**
 * 计算压缩率
 */
export function calculateCompressionRatio(originalBase64: string, compressedBlob: Blob): number {
  // base64 大小估算：(length * 3) / 4
  const originalSize = (originalBase64.length * 3) / 4;
  const compressedSize = compressedBlob.size;
  return Math.round((1 - compressedSize / originalSize) * 100);
}

/**
 * 将 Blob 转换为 base64 字符串（不含 data URL 前缀）
 */
export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      // 移除 "data:image/jpeg;base64," 前缀
      const base64 = dataUrl.split(',')[1] || '';
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

/**
 * 压缩 base64 图片并返回压缩后的 base64 字符串
 * 用于回调发送前压缩截图，减少网络传输量
 * 
 * @param base64Image - 原始 base64 图片
 * @param options - 压缩选项
 * @returns 压缩后的 base64 字符串（不含 data URL 前缀）
 */
export async function compressScreenshotToBase64(
  base64Image: string,
  options: CompressionOptions = {}
): Promise<string> {
  const blob = await compressScreenshot(base64Image, options);
  return blobToBase64(blob);
}
