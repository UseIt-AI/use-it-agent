import DevIpcHandle from './devIpcHandle';
import AppConfigHandle from './appConfigIpcHandle';
import WindowControlIpcHandle from './windowControlIpcHandle';
import projectIpcHandle from './projectIpcHandle';
import ApiKeyIpcHandle from './apiKeyIpcHandle';

const handles = [
    DevIpcHandle,
    AppConfigHandle,
    WindowControlIpcHandle,
    projectIpcHandle,
    ApiKeyIpcHandle,
];

export const initIpcHandles = () => handles.forEach(h => h.init());
