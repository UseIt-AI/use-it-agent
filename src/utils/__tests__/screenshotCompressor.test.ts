/**
 * Screenshot Compressor 单元测试
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { compressScreenshot, getBlobSizeKB, calculateCompressionRatio } from '../screenshotCompressor';

// 创建一个简单的测试用 base64 图片（1x1 红色像素）
const TEST_BASE64_IMAGE = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==';

describe('screenshotCompressor', () => {
  describe('compressScreenshot', () => {
    it('should compress image to JPEG format', async () => {
      const blob = await compressScreenshot(TEST_BASE64_IMAGE, {
        maxWidth: 1920,
        maxHeight: 1080,
        quality: 0.8,
        format: 'jpeg'
      });

      expect(blob).toBeInstanceOf(Blob);
      expect(blob.type).toBe('image/jpeg');
    });

    it('should respect quality setting', async () => {
      const highQuality = await compressScreenshot(TEST_BASE64_IMAGE, {
        quality: 0.9,
        format: 'jpeg'
      });

      const lowQuality = await compressScreenshot(TEST_BASE64_IMAGE, {
        quality: 0.5,
        format: 'jpeg'
      });

      // 低质量应该产生更小的文件
      expect(lowQuality.size).toBeLessThanOrEqual(highQuality.size);
    });

    it('should handle invalid base64 gracefully', async () => {
      await expect(
        compressScreenshot('invalid-base64', {})
      ).rejects.toThrow();
    });
  });

  describe('getBlobSizeKB', () => {
    it('should return size in KB', async () => {
      const blob = await compressScreenshot(TEST_BASE64_IMAGE);
      const sizeKB = getBlobSizeKB(blob);

      expect(sizeKB).toBeGreaterThan(0);
      expect(Number.isInteger(sizeKB)).toBe(true);
    });
  });

  describe('calculateCompressionRatio', () => {
    it('should calculate compression ratio', async () => {
      const blob = await compressScreenshot(TEST_BASE64_IMAGE);
      const ratio = calculateCompressionRatio(TEST_BASE64_IMAGE, blob);

      expect(ratio).toBeGreaterThanOrEqual(0);
      expect(ratio).toBeLessThanOrEqual(100);
    });
  });
});

