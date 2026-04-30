export interface TextSegment {
  type: 'text';
  value: string;
}

export interface FileSegment {
  type: 'file';
  path: string;
  name: string;
}

export type QuickStartSegment = TextSegment | FileSegment;

// Matches @path/to/file.ext or @"path with spaces/file.ext"
const FILE_REF_REGEX = /@"([^"]+\.\w+)"|@([\w.\/\\-]+\.\w+)/g;

function extractPathFromMatch(match: RegExpMatchArray): string {
  return match[1] ?? match[2];
}

export function parseQuickStartMessage(text: string): QuickStartSegment[] {
  const segments: QuickStartSegment[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(FILE_REF_REGEX)) {
    const matchStart = match.index!;
    if (matchStart > lastIndex) {
      segments.push({ type: 'text', value: text.slice(lastIndex, matchStart) });
    }
    const filePath = extractPathFromMatch(match);
    const name = filePath.split(/[/\\]/).pop() || filePath;
    segments.push({ type: 'file', path: filePath, name });
    lastIndex = matchStart + match[0].length;
  }

  if (lastIndex < text.length) {
    segments.push({ type: 'text', value: text.slice(lastIndex) });
  }

  if (segments.length === 0 && text.length > 0) {
    segments.push({ type: 'text', value: text });
  }

  return segments;
}

export function stripFileReferences(text: string): string {
  return text.replace(FILE_REF_REGEX, '').replace(/\s{2,}/g, ' ').trim();
}

export function extractFilePaths(text: string): string[] {
  const paths: string[] = [];
  for (const match of text.matchAll(FILE_REF_REGEX)) {
    paths.push(extractPathFromMatch(match));
  }
  return paths;
}
