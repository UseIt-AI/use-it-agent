/**
 * App Actions Entry Point
 * 
 * Importing this module registers all app actions in the registry.
 * Import once at app startup (e.g. from the router or useChat).
 */

import './actions/panelActions';
import './actions/workflowActions';
import './actions/environmentActions';
import './actions/systemActions';

export { default as appAction } from './registry';
export type { ActionResult, AppActionSchema } from './registry';
