import type { ButtonHTMLAttributes, ReactNode } from "react";
import { NoKeyRegisteredError, resolveProviderForDescriptor } from "@/lib/actions/dispatch";
import { createActionDescriptor } from "@/lib/actions/registry";
import type { ActionContext } from "@/lib/actions/types";
import { routeAction } from "@/state/actionDispatchStore";

type Props = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> & {
  actionId: string;
  context: ActionContext;
  children: ReactNode;
  onToast?: (message: string, durationMs?: number) => void;
  onMissingProvider?: (provider: string) => void;
};

export function ActionButton({
  actionId,
  context,
  children,
  onToast,
  onMissingProvider,
  ...buttonProps
}: Props) {
  async function handleClick(event: React.MouseEvent<HTMLButtonElement>) {
    const descriptor = createActionDescriptor(actionId, context);
    if (!descriptor) {
      // eslint-disable-next-line no-console
      console.error(`Action not implemented: ${actionId}`);
      onToast?.(`Action not implemented: ${actionId}`, 2600);
      return;
    }
    try {
      const provider = await resolveProviderForDescriptor(descriptor);
      routeAction({ ...descriptor, provider }, event.currentTarget);
    } catch (error) {
      if (error instanceof NoKeyRegisteredError) {
        onMissingProvider?.(error.provider);
        onToast?.(`Add your ${error.provider} key to use this action`, 3200);
        return;
      }
      onToast?.(error instanceof Error ? error.message : "Action failed", 3200);
    }
  }

  return (
    <button type="button" {...buttonProps} onClick={(event) => void handleClick(event)}>
      {children}
    </button>
  );
}
