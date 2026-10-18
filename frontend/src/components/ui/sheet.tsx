"use client";

import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { IconButton } from "./button";

/**
 * Mobile drawer/bottom sheet built on <dialog>: modal focus trapping, Escape to
 * close and inert background come from the browser.
 */
export function Sheet({
  open,
  onClose,
  side,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  side: "left" | "bottom";
  title: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const position =
    side === "left"
      ? "m-0 h-dvh max-h-dvh w-[86vw] max-w-[320px] motion-safe:animate-[slide-in-left_200ms_ease-out]"
      : "mx-0 mb-0 mt-auto h-[88dvh] max-h-[88dvh] w-full max-w-full rounded-t-2xl motion-safe:animate-[slide-in-up_220ms_ease-out]";

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className={`bg-surface p-0 text-ink shadow-2xl lg:hidden ${position}`}
    >
      {open && (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-line px-4 py-2">
            <h2 className="text-sm font-semibold">{title}</h2>
            <IconButton label="Close" onClick={onClose}>
              <X className="size-5" aria-hidden />
            </IconButton>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        </div>
      )}
    </dialog>
  );
}
