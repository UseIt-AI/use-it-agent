/**
 * App Action Registry
 * 
 * Central registry for all in-app actions that AI can invoke via
 * tool_call events with target="app". Each action is self-describing
 * (name + description + JSON Schema parameters) so the schema can
 * be sent to AI_Run as available tools.
 */

import { z } from 'zod';
import { logRouter } from '@/utils/logger';

// ==================== Types ====================

export interface ActionResult {
  success: boolean;
  data?: any;
  error?: string;
}

export interface AppActionSchema {
  name: string;
  description: string;
  /** JSON Schema describing the parameters */
  parameters:  Record<string, any>;
}

export interface AppActionDefinition extends AppActionSchema {
  /** Handler function — TArgs describes the runtime shape of parameters */
  handler: (args: Record<string, any>) => Promise<ActionResult>;
}

class AppAction {

  private actionMap: Map<string, AppActionDefinition>;

  constructor() {
    this.actionMap = new Map();
  }

  /**
   * Register an app action. Overwrites any existing action with the same name.
   */
  public registerAction<T extends z.ZodType = z.ZodObject<{}>>(config: {
    name: string;
    description: string;
    parameters?: T;
    handler: (args: z.infer<T>) => Promise<ActionResult>;
  }): void {
    const schema = config.parameters ?? (z.object({}) as unknown as T);
    this.actionMap.set(config.name, {
      name: config.name,
      description: config.description,
      parameters: z.toJSONSchema(schema),
      handler: async (rawArgs: Record<string, any>) => {
        const args = schema.parse(rawArgs);
        return config.handler(args);
      },
    });
  }

  /**
   * Register an app action. Overwrites any existing action with the same name.
   */
  public async executeAction(name: string, args: Record<string, any>): Promise<ActionResult> {
    const action = this.actionMap.get(name);
    if (!action) {
      return { success: false, error: `Unknown app action: ${name}` };
    }
    try {
      logRouter('[AppAction] Executing %s with args: %O', name, args);
      const result = await action.handler(args);
      logRouter('[AppAction] %s completed: success=%s', name, result.success);
      return result;
    } catch (err: any) {
      if (err instanceof z.ZodError) {
        const issues = err.issues.map(i => `${i.path.join('.')}: ${i.message}`).join('; ');
        return { success: false, error: `Invalid parameters: ${issues}` };
      }
      console.error(`[AppAction] ${name} threw:`, err);
      return { success: false, error: err.message || String(err) };
    }
  }

  /**
   * Register an app action. Overwrites any existing action with the same name.
   */
  public getActionSchemas(): AppActionSchema[] {
    return Array.from(this.actionMap.values()).map(({ name, description, parameters }) => ({
      name,
      description,
      parameters,
    }));
  }

  /**
 * Check if an action is registered.
 */
  public hasAction(name: string): boolean {
    return this.actionMap.has(name);
  }

  /**
 * Get an action schema by name.
 */
  public getActionSchema(name: string): AppActionSchema | undefined {
    return this.actionMap.get(name);
  }
}

const appAction = new AppAction();
export default appAction;