"use client";

import { ArrowUp } from "lucide-react";
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

const MAX = 4000;

export function Composer({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const trimmed = text.trim();
  const tooLong = text.length > MAX;

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!trimmed || tooLong || disabled) return;
    onSend(trimmed);
    setText("");
    ref.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={submit} className="mx-auto w-full max-w-3xl">
      <div className="flex items-end gap-2 rounded-2xl bg-surface p-2 shadow-sm ring-1 ring-line-strong focus-within:ring-2 focus-within:ring-accent">
        <label htmlFor="composer" className="sr-only">
          Message
        </label>
        <textarea
          id="composer"
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask for a briefing, a forecast, a search…"
          aria-describedby="composer-hint"
          className="field-sizing-content max-h-48 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-faint focus-visible:outline-none"
        />
        <button
          type="submit"
          aria-label="Send message"
          disabled={!trimmed || tooLong || disabled}
          className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-ink transition-colors hover:bg-accent-hover disabled:bg-line disabled:text-faint"
        >
          <ArrowUp className="size-5" aria-hidden />
        </button>
      </div>
      <p id="composer-hint" className={`mt-1.5 px-2 text-[12px] ${tooLong ? "text-fail" : "text-faint"}`}>
        {tooLong
          ? `${text.length - MAX} characters over the ${MAX} limit`
          : "Enter to send, Shift+Enter for a new line. Responses are simulated."}
      </p>
    </form>
  );
}
