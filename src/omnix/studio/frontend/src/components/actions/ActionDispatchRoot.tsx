import { useEffect } from "react";
import { useActionDispatchStore, type ActionDispatchState } from "@/state/actionDispatchStore";
import { ModalSurface } from "./ModalSurface";

export function ActionDispatchRoot({
  onToast,
}: {
  onToast?: (message: string, durationMs?: number) => void;
}) {
  const activeModal = useActionDispatchStore((s: ActionDispatchState) => s.activeModal);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<string>).detail;
      if (typeof detail === "string") onToast?.(detail, 2600);
    };
    window.addEventListener("omnix:action-toast", handler);
    return () => window.removeEventListener("omnix:action-toast", handler);
  }, [onToast]);

  return activeModal ? <ModalSurface modal={activeModal} /> : null;
}
