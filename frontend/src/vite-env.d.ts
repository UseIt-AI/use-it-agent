/// <reference types="vite/client" />
/// <reference path="../types/electron.d.ts" />

declare const __APP_VERSION__: string;

/** Augment Vite client env (merge with vite/client defaults) */
interface ImportMetaEnv {
  readonly VITE_ENABLE_REMOTE_CONTROL?: string;
}











