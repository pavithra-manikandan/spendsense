import { useEffect, useRef, useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import {
  ArrowUpIcon,
  SendIcon,
  LoaderIcon,
  Sparkles,
  TrendingDown,
  DollarSign,
  AlertTriangle,
  BarChart3,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
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
      : "Hey! Upload a bank CSV first, then ask me anything about your spending. I'll give you specific advice with dollar amounts."
    }
  ]);
  const [isThinking, setIsThinking] = useState(false);
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [inputFocused, setInputFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => setMousePosition({ x: e.clientX, y: e.clientY });
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

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
      {/* Ambient glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-violet-500/10 rounded-full mix-blend-normal filter blur-[128px] animate-pulse" />
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-indigo-500/10 rounded-full mix-blend-normal filter blur-[128px] animate-pulse" style={{ animationDelay: "700ms" }} />
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
            <h2 className="text-2xl font-medium tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white/90 to-white/40 pb-1">
              What's on your mind?
            </h2>
            <motion.div
              className="h-px bg-gradient-to-r from-transparent via-white/20 to-transparent mx-auto max-w-xs mt-2"
              initial={{ width: 0 }}
              animate={{ width: "100%" }}
              transition={{ delay: 0.5, duration: 0.8 }}
            />
            <p className="text-sm text-white/40 mt-3">Ask about your spending patterns</p>
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
                ? "bg-white text-[#0A0A0B] font-medium"
                : "backdrop-blur-xl bg-white/[0.03] border border-white/[0.08] text-white/90"
            )}>
              {msg.text}
              {msg.warning && (
                <div className="mt-2 pt-2 border-t border-white/10 text-xs text-amber-400/70 flex items-center gap-1.5">
                  <AlertTriangle className="w-3 h-3" />
                  {msg.warning}
                </div>
              )}
            </div>
          </motion.div>
        ))}

        {isThinking && (
          <motion.div className="flex mb-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="backdrop-blur-xl bg-white/[0.03] border border-white/[0.08] rounded-2xl px-4 py-3 flex items-center gap-3">
              <span className="text-sm text-white/50">Analyzing</span>
              <div className="flex items-center">
                {[1, 2, 3].map((dot) => (
                  <motion.div
                    key={dot}
                    className="w-1.5 h-1.5 bg-white/80 rounded-full mx-0.5"
                    animate={{ opacity: [0.3, 0.9, 0.3], scale: [0.85, 1.1, 0.85] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: dot * 0.15 }}
                    style={{ boxShadow: "0 0 4px rgba(255,255,255,0.3)" }}
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
              className="flex items-center gap-2 px-3 py-2 bg-white/[0.02] hover:bg-white/[0.06] rounded-lg text-sm text-white/50 hover:text-white/90 transition-all border border-white/[0.05]"
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
        <motion.div
          className="backdrop-blur-2xl bg-white/[0.02] rounded-2xl border border-white/[0.05] shadow-2xl"
          initial={{ scale: 0.98 }}
          animate={{ scale: 1 }}
        >
          <div className="p-3">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => { setValue(e.target.value); adjustHeight(); }}
              onKeyDown={handleKeyDown}
              onFocus={() => setInputFocused(true)}
              onBlur={() => setInputFocused(false)}
              placeholder="Ask spendsense a question..."
              className="w-full px-3 py-2 resize-none bg-transparent border-none text-white/90 text-sm focus:outline-none placeholder:text-white/20"
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
                  ? "bg-white text-[#0A0A0B] shadow-lg shadow-white/10"
                  : "bg-white/[0.05] text-white/40"
              )}
            >
              {isThinking ? <LoaderIcon className="w-4 h-4 animate-spin" /> : <SendIcon className="w-4 h-4" />}
              <span>Send</span>
            </motion.button>
          </div>
        </motion.div>
      </div>

      {/* Mouse follow glow */}
      {inputFocused && (
        <motion.div
          className="fixed w-[50rem] h-[50rem] rounded-full pointer-events-none z-0 opacity-[0.02] bg-gradient-to-r from-violet-500 via-fuchsia-500 to-indigo-500 blur-[96px]"
          animate={{ x: mousePosition.x - 400, y: mousePosition.y - 400 }}
          transition={{ type: "spring", damping: 25, stiffness: 150, mass: 0.5 }}
        />
      )}
    </div>
  );
}
