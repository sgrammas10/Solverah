import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Send, MessageSquare } from 'lucide-react';
import { useAuth } from '../../auth';
import { parseApiError } from '../../../shared/api/apiError';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

function AgentChat() {
  const { streamFetch } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: Message = { role: 'user', content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput('');
    setIsLoading(true);
    setError(null);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await streamFetch('/agent/messages', {
        method: 'POST',
        body: JSON.stringify({ messages: nextMessages }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw parseApiError(response, errData, 'Request failed');
      }

      if (!response.body) throw new Error('No response body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let assistantContent = '';
      let started = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          const payload = part.slice(6).trim();
          if (!payload) continue;
          let event: any;
          try { event = JSON.parse(payload); } catch { continue; }
          if (event.error) throw new Error(event.error);
          if (event.chunk) {
            assistantContent += event.chunk;
            if (!started) {
              setMessages([...nextMessages, { role: 'assistant', content: assistantContent }]);
              started = true;
            } else {
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: assistantContent };
                return updated;
              });
            }
            await new Promise(resolve => setTimeout(resolve, 40));
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      const message = err instanceof Error ? err.message : 'Something went wrong. Please try again.';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  const showDots = isLoading && (messages.length === 0 || messages[messages.length - 1]?.role !== 'assistant');

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col h-[calc(100vh-4rem)]">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-ink-primary">Solverah AI</h1>
          <p className="text-sm text-ink-secondary mt-1">Your personal career assistant</p>
          {/* AI-use disclosure (GAP-09, 2026-08-20): plain statement that this is
              an AI, what it can see, and that it can be wrong. */}
          <p className="text-xs text-ink-tertiary mt-1">
            You're chatting with an AI. It uses your profile and resume to personalize
            answers, and it can make mistakes — verify anything important.
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => { abortControllerRef.current?.abort(); setMessages([]); setError(null); }}
            className="text-sm text-ink-tertiary hover:text-ink-secondary transition-colors"
          >
            Clear chat
          </button>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3 text-ink-tertiary">
            <MessageSquare className="h-12 w-12 opacity-30" />
            <p className="text-sm">Ask me anything about your career, job search, or skill development.</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-forest-dark text-white whitespace-pre-wrap'
                  : 'bg-cream-subtle border border-cream-muted text-ink-primary'
              }`}
            >
              {msg.role === 'user' ? msg.content : (
                <ReactMarkdown
                  components={{
                    p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                    ol: ({ children }) => <ol className="list-decimal list-outside ml-4 space-y-1 mb-2">{children}</ol>,
                    ul: ({ children }) => <ul className="list-disc list-outside ml-4 space-y-1 mb-2">{children}</ul>,
                    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                  }}
                >
                  {msg.content}
                </ReactMarkdown>
              )}
            </div>
          </div>
        ))}

        {showDots && (
          <div className="flex justify-start">
            <div className="bg-cream-subtle border border-cream-muted rounded-xl px-4 py-3">
              <span className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-ink-tertiary animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 rounded-full bg-ink-tertiary animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 rounded-full bg-ink-tertiary animate-bounce [animation-delay:300ms]" />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-3 flex items-center justify-between rounded-lg bg-red-50 border border-red-200 px-4 py-2 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="ml-4 text-red-500 hover:text-red-700 font-medium"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Input form */}
      <form onSubmit={handleSubmit} className="flex gap-3 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message Solverah AI… (Enter to send, Shift+Enter for new line)"
          rows={2}
          disabled={isLoading}
          className="flex-1 resize-none rounded-xl border border-cream-muted bg-cream-base px-4 py-3 text-sm text-ink-primary placeholder-ink-tertiary focus:outline-none focus:ring-2 focus:ring-forest-mid disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          className="flex-shrink-0 p-3 rounded-xl bg-forest-dark text-white hover:bg-forest-mid transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Send message"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}

export default AgentChat;
