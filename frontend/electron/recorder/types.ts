export interface RecorderSource {
  id: string;
  name: string;
  thumbnail: string; // dataURL
}

export interface RecordingInfo {
  isRecording: boolean;
  duration: number; // seconds
  filePath?: string; // 有鼠标的视频路径（用于上传）
  filePathNoMouse?: string; // 无鼠标的视频路径（本地保留）
  startTime?: string; // ISO
  isStopping?: boolean;
  stopComplete?: boolean;
}

export interface RecordingStopCompletePayload {
  filePath?: string;
  success: boolean;
  error?: string;
}

export interface RecordingStopInitiatedPayload {
  filePath?: string;
  stopping: boolean;
}




