export interface VmClassifiedError {
  isPermissionError: boolean;
  isVmNotFoundError: boolean;
  userMessage: string;
  rawMessage: string;
}

const PERMISSION_PATTERNS = [
  'required permission',
  'permission to complete this task',
  'authorization policy',
  'hyper-v administrators',
  'access is denied',
  'virtualizationexception',
  'unauthorized',
];

const RAW_COMMAND_PATTERN = /powershell\s+-command/i;
const VM_NOT_FOUND_PATTERN = /virtual machine .* not found|unable to find a virtual machine|could not find.*virtual machine/i;

const extractMessage = (error: unknown): string => {
  if (error instanceof Error) return error.message || '';
  if (typeof error === 'string') return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error ?? '');
  }
};

const isPermissionError = (rawMessage: string): boolean => {
  const normalized = rawMessage.toLowerCase();
  return PERMISSION_PATTERNS.some(pattern => normalized.includes(pattern));
};

export function classifyVmError(error: unknown, fallbackMessage: string): VmClassifiedError {
  const rawMessage = extractMessage(error);
  const vmNotFound = VM_NOT_FOUND_PATTERN.test(rawMessage);

  if (isPermissionError(rawMessage)) {
    return {
      isPermissionError: true,
      isVmNotFoundError: false,
      userMessage: 'Virtual machine administrator permission is required. Click "Fix Permission", then sign out and sign back in to Windows.',
      rawMessage,
    };
  }

  if (vmNotFound) {
    return {
      isPermissionError: false,
      isVmNotFoundError: true,
      userMessage: 'Virtual machine not found. Please reinstall or restore this environment.',
      rawMessage,
    };
  }

  if (RAW_COMMAND_PATTERN.test(rawMessage)) {
    return {
      isPermissionError: false,
      isVmNotFoundError: false,
      userMessage: fallbackMessage,
      rawMessage,
    };
  }

  return {
    isPermissionError: false,
    isVmNotFoundError: false,
    userMessage: rawMessage || fallbackMessage,
    rawMessage,
  };
}
