import React from 'react';
import { Folder } from 'lucide-react';
import { generateManifest } from 'material-icon-theme';

const materialIconModules = import.meta.glob('../../../../../node_modules/material-icon-theme/icons/*.svg', {
  eager: true,
  import: 'default',
}) as Record<string, string>;

const materialIconByFilename = Object.fromEntries(
  Object.entries(materialIconModules).map(([modulePath, assetUrl]) => [modulePath.split('/').pop() ?? modulePath, assetUrl])
);

const materialManifest = generateManifest({
  files: {
    associations: {
      prproj: 'video',
      aep: 'video',
      drp: 'video',
      fcpxml: 'video',
      blend: 'video',
    },
  },
});

const fileNameIconIdMap = Object.fromEntries(
  Object.entries(materialManifest.fileNames ?? {}).map(([fileName, iconId]) => [fileName.toLowerCase(), iconId])
);
const extensionIconIdMap = Object.fromEntries(
  Object.entries(materialManifest.fileExtensions ?? {}).map(([ext, iconId]) => [ext.toLowerCase(), iconId])
);

const resolveIconSrcByIconId = (iconId: string | undefined): string | undefined => {
  if (!iconId) return undefined;
  const iconPath = materialManifest.iconDefinitions?.[iconId]?.iconPath;
  if (!iconPath) return undefined;
  const fileName = iconPath.split('/').pop();
  if (!fileName) return undefined;
  return materialIconByFilename[fileName];
};

const defaultFileIconSrc =
  resolveIconSrcByIconId(materialManifest.file) ??
  materialIconByFilename['file.svg'] ??
  '';

const getExtensionCandidates = (fileName: string): string[] => {
  const parts = fileName.toLowerCase().split('.');
  if (parts.length <= 1) return [];
  const candidates: string[] = [];
  for (let i = 1; i < parts.length; i += 1) {
    candidates.push(parts.slice(i).join('.'));
  }
  return candidates;
};

/**
 * Returns a React element for the file/folder icon matching `material-icon-theme`.
 * @param name  File or folder name (e.g. "readme.md")
 * @param isFolder  Whether the item is a directory
 * @param size  CSS pixel size (default 14)
 */
export function getFileIcon(name: string, isFolder: boolean, size = 14): React.ReactNode {
  if (isFolder) {
    return <Folder style={{ width: size, height: size }} className="text-[#6F8F63]" strokeWidth={2} />;
  }

  const normalizedName = name.toLowerCase();
  const fileNameIconId = fileNameIconIdMap[normalizedName];
  const extensionIconId = getExtensionCandidates(normalizedName)
    .map(ext => extensionIconIdMap[ext])
    .find(Boolean);
  const iconSrc = resolveIconSrcByIconId(fileNameIconId ?? extensionIconId) ?? defaultFileIconSrc;
  const ext = name.split('.').pop()?.toLowerCase() || '';

  return (
    <span
      className="inline-flex items-center justify-center flex-shrink-0"
      style={{ width: size, height: size }}
      title={ext ? `.${ext}` : 'file'}
    >
      <img
        src={iconSrc}
        alt={ext || 'file'}
        style={{ width: size, height: size }}
        className="object-contain"
        draggable={false}
      />
    </span>
  );
}
