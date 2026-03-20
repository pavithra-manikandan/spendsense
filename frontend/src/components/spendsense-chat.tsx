import { useEffect, useRef, useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import {
  SendIcon,
  LoaderIcon,
  TrendingDown,
  DollarSign,
  AlertTriangle,
  BarChart3,
} from "lucide-react";
import { motion } from "framer-motion";
import { askAgent } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  warning?: string;
}

const SUGGESTIONS = [
  { icon: <TrendingDown className="w-4 h-4" />, label: "Overspending", question: "Where am I overspending?" },
  { icon: <DollarSign className="w-4 h-4" />, label: "Save $200", question: "How can I save $200 next month?" },
  { icon: <AlertTriangle className="w-4 h-4" />, label: "Unusual charges", question: "Any unusual charges?" },
  { icon: <BarChart3 className="w-4 h-4" />, label: "Subscriptions", question: "What are my subscriptions costing me?" },
];

export function SpendSenseChat({ hasData }: { hasData: boolean }) {
  const [value, setValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "assistant", text: hasData
      ? "Your data is loaded. Ask me anything — where you're overspending, how to save, unusual charges, subscription costs."
      : "Hey! Upload a bank CSV or PDF first, then ask me anything about your spending. I'll give you specific advice with dollar amounts."
    }
  ]);
  const [isThinking, setIsThinking] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "60px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const handleSend = async (question?: string) => {
    const q = (question || value).trim();
    if (!q || isThinking) return;
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "60px";
    setIsThinking(true);

    try {
      const data = await askAgent(q);
      setMessages(prev => [...prev, {
        role: "assistant",
        text: data.answer,
        warning: data.api_warning,
      }]);
    } catch {
      setMessages(prev => [...prev, {
        role: "assistant",
        text: "Couldn't reach the server. Is it running on port 8000?",
      }]);
    }
    setIsThinking(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full relative overflow-hidden">
      {/* Ambient glow — gold/amber to match dashboard */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-primary/8 rounded-full filter blur-[128px] animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-chart-2/8 rounded-full filter blur-[128px] animate-pulse" style={{ animationDelay: "700ms" }} />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 relative z-10">
        {messages.length === 1 && (
          <motion.div
            className="text-center mb-8 mt-12"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <div className="text-5xl mb-4">💸</div>
            <h2 className="text-2xl font-medium tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white/90 to-white/40 pb-1">
              What's on your mind?
            </h2>
            <motion.div
              className="h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent mx-auto max-w-xs mt-3"
              initial={{ width: 0 }}
              animate={{ width: "100%" }}
              transition={{ delay: 0.5, duration: 0.8 }}
            />
            <p className="text-sm text-muted-foreground mt-3">Ask about your spending patterns</p>
          </motion.div>
        )}

        {messages.map((msg, i) => (
          <motion.div
            key={i}
            className={cn("flex mb-4", msg.role === "user" ? "justify-end" : "justify-start")}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className={cn(
              "max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap",
              msg.role === "user"
                ? "bg-primary text-primary-foreground font-medium"
                : "bg-card border border-border text-foreground"
            )}>
              {msg.text}
              {msg.warning && (
                <div className="mt-2 pt-2 border-t border-border text-xs text-primary/70 flex items-center gap-1.5">
                  <AlertTriangle className="w-3 h-3" />
                  {msg.warning}
                </div>
              )}
            </div>
          </motion.div>
        ))}

        {isThinking && (
          <motion.div className="flex mb-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="bg-card border border-border rounded-2xl px-4 py-3 flex items-center gap-3">
              <span className="text-sm text-muted-foreground">Analyzing</span>
              <div className="flex items-center">
                {[1, 2, 3].map((dot) => (
                  <motion.div
                    key={dot}
                    className="w-1.5 h-1.5 bg-primary rounded-full mx-0.5"
                    animate={{ opacity: [0.3, 0.9, 0.3], scale: [0.85, 1.1, 0.85] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: dot * 0.15 }}
                  />
                ))}
              </div>
            </div>
          </motion.div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 2 && (
        <div className="flex flex-wrap items-center justify-center gap-2 px-4 pb-3 relative z-10">
          {SUGGESTIONS.map((s, i) => (
            <motion.button
              key={s.label}
              onClick={() => handleSend(s.question)}
              className="flex items-center gap-2 px-3 py-2 bg-card hover:bg-secondary rounded-lg text-sm text-muted-foreground hover:text-primary transition-all border border-border"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08 }}
            >
              {s.icon}
              <span>{s.label}</span>
            </motion.button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="relative z-10 px-4 pb-4">
        <div className="bg-card rounded-2xl border border-border shadow-2xl">
          <div className="p-3">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => { setValue(e.target.value); adjustHeight(); }}
              onKeyDown={handleKeyDown}
              placeholder="Ask spendsense a question..."
              className="w-full px-3 py-2 resize-none bg-transparent border-none text-foreground text-sm focus:outline-none placeholder:text-muted-foreground"
              style={{ minHeight: 60, maxHeight: 200, overflow: "hidden" }}
            />
          </div>
          <div className="px-3 pb-3 flex items-center justify-end">
            <motion.button
              onClick={() => handleSend()}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              disabled={isThinking || !value.trim()}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-2",
                value.trim()
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/20"
                  : "bg-secondary text-muted-foreground"
              )}
            >
              {isThinking ? <LoaderIcon className="w-4 h-4 animate-spin" /> : <SendIcon className="w-4 h-4" />}
              <span>Send</span>
            </motion.button>
          </div>
        </div>
      </div>
    </div>
  );
}