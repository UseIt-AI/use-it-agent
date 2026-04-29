/**
 * CompletionCard - 工作流完成卡片
 * 显示完成状态和反馈按钮
 */

import React, { useState } from 'react';
import { Check, ThumbsUp, ThumbsDown } from 'lucide-react';
import type { CompletionBlock } from '../handlers/types';

interface CompletionCardProps {
  block: CompletionBlock;
  onFeedback?: (feedback: 'like' | 'dislike') => void;
}

export const CompletionCard: React.FC<CompletionCardProps> = ({ block, onFeedback }) => {
  const [feedback, setFeedback] = useState<'like' | 'dislike' | null>(block.feedback || null);

  const handleFeedback = (type: 'like' | 'dislike') => {
    // Toggle if clicking the same button
    const newFeedback = feedback === type ? null : type;
    setFeedback(newFeedback);
    if (newFeedback && onFeedback) {
      onFeedback(newFeedback);
    }
  };

  return (
    <div className="flex items-center justify-between pt-0 pb-2 mt-0 border-t border-gray-100">
      {/* Left: Checkmark + Done */}
      <div className="flex items-center gap-1.5 text-gray-500">
        <Check className="w-4 h-4" strokeWidth={2.5} />
        <span className="text-[13px] font-medium">Done</span>
      </div>

      {/* Right: Feedback buttons */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => handleFeedback('like')}
          className={`p-1.5 rounded-md transition-all ${
            feedback === 'like'
              ? 'bg-emerald-50 text-emerald-600'
              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
          }`}
          title="Good response"
        >
          <ThumbsUp className="w-4 h-4" />
        </button>
        <button
          onClick={() => handleFeedback('dislike')}
          className={`p-1.5 rounded-md transition-all ${
            feedback === 'dislike'
              ? 'bg-red-50 text-red-500'
              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
          }`}
          title="Bad response"
        >
          <ThumbsDown className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

